"""Exercise actual command parsing, pre-write reads and wait boundaries offline."""

import json

import httpx
import pytest
from click.testing import CliRunner

from yicloud.cli import main
from yicloud.client import YicloudClient
from yicloud.errors import RemoteFailed, UnknownState, WaitTimeout, YicloudError
from yicloud.workflows import wait, wait_deleted


def use_transport(monkeypatch, account, handler):
    for module in ("workloads", "catalog_commands"):
        monkeypatch.setattr(
            f"yicloud.commands.{module}.client_for",
            lambda _: YicloudClient(account, transport=httpx.MockTransport(handler)),
        )


def invoke(*args, input=None):
    return CliRunner().invoke(main, ["--json", *args], input=input)


def response(data):
    return httpx.Response(200, json={"Code": 0, "Data": data})


@pytest.mark.parametrize(
    "value,option,target",
    [
        ("nan", "--timeout", "default"),
        ("inf", "--interval", "stopped"),
        ("-inf", "--timeout", "deleted"),
    ],
)
def test_nonfinite_wait_rejected_before_name_lookup(monkeypatch, value, option, target):
    monkeypatch.setattr("yicloud.commands.workloads.client_for", lambda _: pytest.fail("No I/O"))
    result = invoke(
        "job",
        "wait",
        "j",
        "--project",
        "p",
        "--zone",
        "z",
        "--target",
        target,
        option,
        value,
    )
    assert result.exit_code != 0


@pytest.mark.parametrize("value", ["nan"])
def test_nonfinite_log_interval_never_connects(monkeypatch, value):
    monkeypatch.setattr("yicloud.commands.workloads.client_for", lambda _: pytest.fail("No I/O"))
    result = CliRunner().invoke(
        main,
        ["job", "logs", "j", "--project", "p", "--zone", "z", "--follow", "--interval", value],
    )
    assert result.exit_code != 0


@pytest.mark.parametrize(
    "detail,error",
    [
        ({"Project": "other", "ZoneId": "z"}, "scope mismatch"),
        ({"Project": "p", "ZoneId": "other"}, "scope mismatch"),
        ({"Project": "p", "Namespace": "other", "ZoneId": "z"}, "scope mismatch"),
        ({"Project": "p", "ZoneId": "z", "JobId": "other"}, "ID mismatch"),
        ([], "Unrecognized resource detail"),
    ],
)
def test_wrong_or_unknown_scope_never_mutates(account, monkeypatch, detail, error):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        assert request.method == "GET"
        return response(detail)

    use_transport(monkeypatch, account, handler)
    result = invoke("job", "stop", "j", "--project", "p", "--zone", "z")
    assert result.exit_code == 1 and error in result.output
    assert calls == ["/job/v1alpha1/GetJob"]


@pytest.mark.parametrize("status,code", [(403, 101), (200, 105), (200, 101)])
def test_scope_read_errors_never_mutate(account, monkeypatch, status, code):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(status, json={"Code": code, "Msg": "read failed"})

    use_transport(monkeypatch, account, handler)
    result = invoke("job", "stop", "j", "--project", "p", "--zone", "z")
    assert result.exit_code == 1
    assert calls == ["/job/v1alpha1/GetJob"]


@pytest.mark.parametrize("missing", [False, True])
def test_scope_detail_or_list_verification_precedes_write(account, monkeypatch, missing):
    calls = []

    def handler(request):
        action = request.url.path.rsplit("/", 1)[1]
        calls.append(action)
        row = {"JobId": "j", "Project": "p", "ZoneId": "z"}
        if action == "GetJob":
            return response({"Phase": "Running"} if missing else row)
        if action == "ListJobs":
            assert request.url.params["JobIds"] == "j"
            return response({"Items": [row], "Total": 1})
        assert action == "StopJob"
        assert json.loads(request.content) == {"JobId": "j", "Project": "p", "ZoneId": "z"}
        return response({})

    use_transport(monkeypatch, account, handler)
    result = invoke("job", "stop", "j", "--project", "p", "--zone", "z")
    assert result.exit_code == 0, result.output
    assert calls == ["GetJob", *(["ListJobs"] if missing else []), "StopJob"]


@pytest.mark.parametrize("rows", [[], [{"JobId": "j", "Project": "p"}], [{"Phase": "Running"}]])
def test_missing_scope_evidence_refuses_write(account, monkeypatch, rows):
    def handler(request):
        assert request.method == "GET"
        return response(
            {"Phase": "Running"}
            if request.url.path.endswith("GetJob")
            else {
                "Items": rows,
                "Total": len(rows),
            }
        )

    use_transport(monkeypatch, account, handler)
    result = invoke("job", "stop", "j", "--project", "p", "--zone", "z")
    assert result.exit_code == 1
    assert "scope" in result.output or "cannot prove" in result.output


def test_generated_request_file_can_set_verification_zone(account, monkeypatch):
    calls = []

    def handler(request):
        calls.append(request.url.path.rsplit("/", 1)[1])
        if request.method == "GET":
            return response({"Namespace": "p", "ZoneId": "z"})
        assert json.loads(request.content) == {"Project": "p", "ID": "i", "Name": "new"}
        return response({})

    use_transport(monkeypatch, account, handler)
    result = invoke(
        "serving",
        "update",
        "--file",
        "-",
        "--zone",
        "z",
        input=('{"Project":"p","ID":"i","Name":"new"}'),
    )
    assert result.exit_code == 0, result.output
    assert calls == ["GetInferSet", "UpdateInferSet"]


def test_batch_verifies_all_targets_before_any_write(account, monkeypatch):
    calls = []

    def handler(request):
        assert request.method == "GET"
        rid = request.url.params["JobId"]
        calls.append(rid)
        return response({"Project": "p" if rid == "j1" else "other", "ZoneId": "z"})

    use_transport(monkeypatch, account, handler)
    result = invoke(
        "job",
        "batch-delete",
        "--resources",
        '[{"Project":"p","JobId":"j1"},{"Project":"p","JobId":"j2"}]',
        "--zone",
        "z",
    )
    assert result.exit_code == 1 and "scope mismatch" in result.output
    assert calls == ["j1", "j2"]


def test_stop_wait_follows_stopping_and_does_not_mutate(account, monkeypatch):
    states = iter(["Stopping", "Stopped"])
    calls = []

    def handler(request):
        calls.append(request.url.path)
        assert request.method == "GET"
        return response({"Phase": next(states)})

    use_transport(monkeypatch, account, handler)
    result = invoke(
        "job",
        "wait",
        "j",
        "--project",
        "p",
        "--zone",
        "z",
        "--target",
        "stopped",
        "--interval",
        "0.1",
    )
    assert result.exit_code == 0, result.output
    assert len(calls) == 2


@pytest.mark.parametrize("data", [None, {"Status": "Future"}])
def test_wait_unknown_shape_is_never_success(account, data):
    with YicloudClient(account, transport=httpx.MockTransport(lambda _: response(data))) as client:
        with pytest.raises(UnknownState):
            wait(client, "serving", {"Project": "p", "ID": "i"}, timeout=0)


def test_stop_wait_timeout_does_not_cancel_remote(account):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return response({"Phase": "Running"})

    with YicloudClient(account, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(WaitTimeout, match="remote workload was not stopped"):
            wait(client, "job", {"Project": "p", "JobId": "j"}, target="stopped", timeout=0)
    assert calls == ["/job/v1alpha1/GetJob"]


def test_deleted_wait_uses_complete_listing_and_reports_absence(account, monkeypatch):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        assert request.method == "GET" and request.url.path.endswith("ListJobs")
        rows = [{"JobId": "j", "Project": "p", "ZoneId": "z"}] if len(calls) == 1 else []
        return response({"Items": rows, "Total": len(rows)})

    use_transport(monkeypatch, account, handler)
    result = invoke(
        "job",
        "wait",
        "j",
        "--project",
        "p",
        "--zone",
        "z",
        "--target",
        "deleted",
        "--interval",
        "0.1",
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["data"]["evidence"] == "complete_scoped_list"
    assert json.loads(result.output)["data"]["state"] == "absent"
    assert len(calls) == 2


@pytest.mark.parametrize("status,code", [(404, 404), (403, 101), (200, 105)])
def test_deleted_wait_does_not_reclassify_errors_as_absence(account, status, code):
    with YicloudClient(
        account,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(status, json={"Code": code, "Msg": "lookup failed"})
        ),
    ) as client:
        with pytest.raises(YicloudError):
            wait_deleted(client, "job", "j", "p", "z", timeout=0)


@pytest.mark.parametrize("rows", [[{}], [{"JobId": "j", "Project": "p"}]])
def test_deleted_wait_invalid_rows_do_not_mean_absence(account, rows):
    with YicloudClient(
        account,
        transport=httpx.MockTransport(lambda _: response({"Items": rows, "Total": len(rows)})),
    ) as client:
        with pytest.raises(YicloudError):
            wait_deleted(client, "job", "j", "p", "z", timeout=0)


@pytest.mark.parametrize("kind", ["job"])
def test_deleted_wait_does_not_treat_invalid_total_as_absence(account, monkeypatch, kind):
    calls = []

    def handler(request):
        calls.append(request.method)
        return httpx.Response(
            200,
            json={"Code": 0, "Data": {"Items": [], "Total": None}},
            headers={"X-OGW-Request-Id": "fixture-invalid-total"},
        )

    use_transport(monkeypatch, account, handler)
    result = invoke(
        kind,
        "wait",
        "fixture-id",
        "--project",
        "p",
        "--zone",
        "z",
        "--target",
        "deleted",
        "--timeout",
        "0",
    )
    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["ok"] is False and payload["error"]["kind"] == "platform"
    assert payload["error"]["request_id"] == "fixture-invalid-total"
    assert "Total" in payload["error"]["message"]
    assert calls == ["GET"]


@pytest.mark.parametrize(
    "kind,row,dry_run",
    [
        ("job", {"JobId": "j", "Name": "friendly", "Project": "p", "ZoneId": "z"}, False),
        ("serving", {"ID": "i", "Name": "friendly", "Namespace": "p", "ZoneId": "z"}, True),
    ],
)
def test_name_lookup_inconsistent_total_never_resolves_or_writes(
    account, monkeypatch, kind, row, dry_run
):
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path))
        assert request.method == "GET"
        assert "List" in request.url.path
        container = "Data" if kind == "serving" else "Items"
        return httpx.Response(
            200,
            json={"Code": 0, "Data": {container: [row], "Total": 0}},
            headers={"X-OGW-Request-Id": "fixture-inconsistent-total"},
        )

    use_transport(monkeypatch, account, handler)
    result = invoke(
        kind,
        "stop",
        "friendly",
        "--by-name",
        "--project",
        "p",
        "--zone",
        "z",
        *(["--dry-run"] if dry_run else []),
    )
    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["ok"] is False and payload["error"]["kind"] == "platform"
    assert payload["error"]["request_id"] == "fixture-inconsistent-total"
    assert "exceeds Total" in payload["error"]["message"]
    assert len(calls) == 1 and calls[0][0] == "GET"


def test_deleted_wait_name_rejected_and_preview_uses_list(account, monkeypatch):
    use_transport(monkeypatch, account, lambda _: pytest.fail("No network"))
    args = ["job", "wait", "j", "--project", "p", "--zone", "z", "--target", "deleted"]
    result = invoke(*args, "--by-name")
    assert result.exit_code == 1 and "saved resource ID" in result.output
    result = invoke(*args, "--dry-run")
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["data"]["url"].endswith("ListJobs")


def simple_serving(**changes):
    return {
        "Status": "Running",
        "Replicas": 2,
        "TotalReplicas": 2,
        "ReadyReplicas": 2,
        "Distributed": False,
        "PDSeparationEnabled": False,
        **changes,
    }


def test_serving_replica_wait_observes_documented_counts(account, monkeypatch):
    snapshots = iter([simple_serving(ReadyReplicas=1), simple_serving()])
    use_transport(monkeypatch, account, lambda _: response(next(snapshots)))
    result = invoke(
        "serving",
        "wait",
        "i",
        "--project",
        "p",
        "--zone",
        "z",
        "--replicas",
        "2",
        "--interval",
        "0.1",
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["data"]["ReadyReplicas"] == 2


@pytest.mark.parametrize("changes", [{"ReadyReplicas": 1}, {"Replicas": 3}, {"TotalReplicas": 3}])
def test_replica_wait_does_not_finish_until_all_counts_match(account, changes):
    with YicloudClient(
        account, transport=httpx.MockTransport(lambda _: response(simple_serving(**changes)))
    ) as client:
        with pytest.raises(WaitTimeout):
            wait(client, "serving", {"Project": "p", "ID": "i"}, replicas=2, timeout=0)


def test_zero_replicas_can_be_confirmed_stopped(account):
    with YicloudClient(
        account,
        transport=httpx.MockTransport(
            lambda _: response(
                simple_serving(
                    Status="Stopped",
                    Replicas=0,
                    TotalReplicas=0,
                    ReadyReplicas=0,
                )
            )
        ),
    ) as client:
        result = wait(client, "serving", {"Project": "p", "ID": "i"}, replicas=0, timeout=0)
    assert result.data["Status"] == "Stopped"


def test_default_wait_still_rejects_stopping(account):
    with YicloudClient(
        account, transport=httpx.MockTransport(lambda _: response({"Status": "Stopping"}))
    ) as client:
        with pytest.raises(RemoteFailed):
            wait(client, "serving", {"Project": "p", "ID": "i"}, timeout=0)


def test_deleted_wait_does_not_miss_resource_on_later_capped_page(account):
    offsets = []

    def handler(request):
        offset = int(request.url.params["Offset"])
        offsets.append(offset)
        row = {"JobId": "other" if offset == 0 else "j", "Project": "p", "ZoneId": "z"}
        return response({"Items": [row], "Total": 2})

    with YicloudClient(account, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(WaitTimeout):
            wait_deleted(client, "job", "j", "p", "z", timeout=0)
    assert offsets == [0, 1]


def test_stopped_wait_distinguishes_completed_from_stopped(account):
    with YicloudClient(
        account, transport=httpx.MockTransport(lambda _: response({"Phase": "Succeeded"}))
    ) as client:
        with pytest.raises(RemoteFailed, match="not stopped"):
            wait(client, "job", {"Project": "p", "JobId": "j"}, target="stopped", timeout=0)


def test_generated_write_without_scope_fails_before_read(account, monkeypatch):
    use_transport(monkeypatch, account, lambda _: pytest.fail("Missing scope must fail before I/O"))
    result = invoke("serving", "update", "i", "--project", "p", "--replicas", "2")
    assert result.exit_code == 1 and "require project and zone" in result.output
