"""Synthetic workflow responses; no live account is used."""

import json

import httpx
import pytest

from yicloud.client import YicloudClient
from yicloud.creation import create_params
from yicloud.errors import InputError, YicloudError
from yicloud.workflows import (
    follow_logs,
    items,
    log_params,
    paginated,
    resolve,
    wait,
    workload_params,
)


def test_pagination_and_ambiguous_names(account):
    def handler(req):
        offset = int(req.url.params.get("Offset", 0))
        limit = int(req.url.params.get("Limit", 20))
        rows = [
            {"JobId": f"job-{n}", "Name": "same", "Project": "p", "ZoneId": "z"}
            for n in range(offset, min(offset + limit, 21))
        ]
        return httpx.Response(200, json={"Code": 0, "Data": {"Items": rows, "Total": 21}})

    with YicloudClient(account, transport=httpx.MockTransport(handler)) as c:
        assert (
            len(paginated(c, "job", "ListJobs", {"Project": "p", "ZoneId": "z"}).data["Items"])
            == 20
        )
        assert (
            len(
                paginated(c, "job", "ListJobs", {"Project": "p", "ZoneId": "z"}, True).data["Items"]
            )
            == 21
        )
        with pytest.raises(InputError, match="21 matches"):
            resolve(c, "job", "same", "p", "z", True)
        with pytest.raises(InputError, match="0 matches"):
            resolve(c, "job", "missing", "p", "z", True)
        assert resolve(c, "job", "direct-id", "p", "z") == "direct-id"


def test_name_lookup_enforces_scope(account):
    rows = [
        {"Name": "dev", "WorkspaceId": "wrong", "Project": "other", "ZoneId": "z"},
        {"Name": "dev", "WorkspaceId": "good", "Project": "p", "ZoneId": "z"},
    ]
    with YicloudClient(
        account,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"Code": 0, "Data": {"Items": rows, "Total": 2}})
        ),
    ) as c:
        assert resolve(c, "workspace", "dev", "p", "z", True) == "good"


@pytest.mark.parametrize("phase", ["Failed", "Stopped", "Unknown", "new-future-state"])
def test_wait_never_accepts_failure_or_unknown(account, phase):
    with YicloudClient(
        account,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"Code": 0, "Data": {"Phase": phase}})
        ),
    ) as c:
        with pytest.raises(YicloudError):
            wait(c, "job", {"Project": "p", "JobId": "j"}, sleep=lambda _: None)


def test_create_wait_success_and_timeout(account):
    states = iter(["Pending", "Running", "Succeeded"])
    paths = []

    def handler(req):
        paths.append(req.url.path)
        if req.url.path.endswith("CreateJob"):
            return httpx.Response(200, json={"Code": 0, "Data": {"JobId": "j"}})
        return httpx.Response(200, json={"Code": 0, "Data": {"Phase": next(states)}})

    with YicloudClient(account, transport=httpx.MockTransport(handler)) as c:
        result = c.call(
            "job", "CreateJob", {"Name": "fixture", "Project": "p", "ZoneId": "z", "TaskSpecs": {}}
        )
        assert result.data["JobId"] == "j"
        assert (
            wait(c, "job", {"Project": "p", "JobId": "j"}, sleep=lambda _: None).data["Phase"]
            == "Succeeded"
        )
    assert paths.count("/job/v1alpha1/CreateJob") == 1
    with YicloudClient(
        account,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"Code": 0, "Data": {"Phase": "Running"}})
        ),
    ) as c:
        with pytest.raises(YicloudError, match="timed out"):
            wait(c, "job", {"Project": "p", "JobId": "j"}, timeout=0)


def test_follow_uses_ns_and_deduplicates_boundary(account):
    calls = []

    def handler(req):
        calls.append(dict(req.url.params))
        rows = [{"Timestamp": "1000000000000", "Line": "a"}]
        if len(calls) > 1:
            rows += [{"Timestamp": "1000000000001", "Line": "b"}]
        return httpx.Response(200, json={"Code": 0, "Data": {"Items": rows}})

    emitted = []
    count = 0

    def sleep(_):
        nonlocal count
        count += 1
        if count == 2:
            raise KeyboardInterrupt()

    params = log_params("job", {"Project": "p", "JobId": "j"}, start=0, end=2000000000000)
    with YicloudClient(account, transport=httpx.MockTransport(handler)) as c:
        with pytest.raises(KeyboardInterrupt):
            follow_logs(c, "job", params, emitted.append, sleep=sleep, clock=lambda: 2000000000000)
    assert [r["Line"] for r in emitted] == ["a", "b"]
    assert calls[1]["Start"] == "1000000000000"
    assert calls[0]["Direction"] == "forward"
    assert (
        json.loads(json.dumps(log_params("ray", {"Project": "p", "JobName": "j"})))["Method"]
        == "query_range"
    )


def test_serving_pagination_accepts_nested_data_list(account):
    def handler(request):
        offset = int(request.url.params.get("Offset", 0))
        rows = [
            {"ID": f"fixture-{n}", "Name": f"service-{n}", "Project": "p", "ZoneId": "z"}
            for n in range(offset, min(offset + 2, 3))
        ]
        return httpx.Response(200, json={"Code": 0, "Data": {"Data": rows, "Total": 3}})

    with YicloudClient(account, transport=httpx.MockTransport(handler)) as c:
        result = paginated(c, "inferset", "ListInferSet", {"Project": "p", "Limit": 2}, True)
        assert len(result.data["Items"]) == 3
        assert result.data["Items"][2]["ID"] == "fixture-2"


def test_lifecycle_requests_reuse_platform_rules_without_cli():
    assert workload_params("job", "delete", "j", "p", "z") == {
        "Resources": [{"Project": "p", "JobId": "j"}]
    }
    assert workload_params("serving", "scale", "i", "p", "z", replicas=0) == {
        "Project": "p",
        "ID": "i",
        "Replicas": 0,
    }
    extra = {"Force": False}
    request = workload_params("workspace", "stop", "w", "p", "z", extra=extra)
    assert request["Project"] == "p" and request["WorkspaceId"] == "w"
    assert request["Force"] is False and extra == {"Force": False}
    assert request is not extra


@pytest.mark.parametrize("replicas", [None, -1, True, "1"])
def test_lifecycle_scale_rejects_invalid_replica_counts(replicas):
    with pytest.raises(InputError, match="replica"):
        workload_params("serving", "scale", "i", "p", "z", replicas=replicas)


@pytest.mark.parametrize("field", ["Project", "ZoneId", "JobId", "Resources"])
def test_lifecycle_request_rejects_resource_scope_override(field):
    with pytest.raises(InputError, match="cannot override"):
        workload_params("job", "delete", "j", "p", "z", extra={field: "other"})


@pytest.mark.parametrize("kind", ["job", "ray", "serving"])
def test_lifecycle_logs_use_service_contracts(kind):
    request = workload_params(
        kind, "logs", "fixture", "p", "z", start=0, end=100, instance="replica"
    )
    if kind == "ray":
        assert request["StartTime"] == "0" and request["EndTime"] == "100"
        assert request["Method"] == "query_range"
    else:
        assert request["Start"] == 0 and request["End"] == 100
        assert request["Replicas"] == (["replica"] if kind == "serving" else "replica")


@pytest.mark.parametrize("kind", ["workspace", "job"])
def test_creation_rejects_invalid_scope_without_click(kind):
    with pytest.raises(InputError, match="SKU scope"):
        create_params(
            kind,
            name="n",
            project="p",
            zone="z",
            image="image",
            entrypoint="true",
            sku="sku",
            sku_scope="bogus",
        )


@pytest.mark.parametrize(
    "kind,id_field,name_field",
    [
        ("ray", "RayJobName", "DisplayName"),
        ("serving", "ID", "Name"),
    ],
)
def test_name_lookup_uses_fixed_sdk_response_fields(account, kind, id_field, name_field):
    good = {"Namespace": "p", "ZoneId": "z", name_field: "friendly", id_field: "operation-id"}
    rows = [dict(good, Namespace="other"), dict(good, ZoneId="other"), good]
    if kind == "ray":
        good["Id"] = "unrelated-uuid"
    wrapper = "Items" if kind == "ray" else "GetInferSetLogsQueryRangeData"
    with YicloudClient(
        account,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"Code": 0, "Data": {wrapper: rows, "Total": 3}})
        ),
    ) as c:
        rid = resolve(c, kind, "friendly", "p", "z", True)
    assert rid == "operation-id"
    request = workload_params(kind, "stop", rid, "p", "z")
    assert request["JobName" if kind == "ray" else "ID"] == "operation-id"
    assert request["Project"] == "p" and "Namespace" not in request


def test_ray_name_lookup_rejects_missing_operation_id_and_ambiguity(account):
    rows = [{"Namespace": "p", "ZoneId": "z", "DisplayName": "friendly", "Id": "uuid"}]
    with YicloudClient(
        account,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, json={"Code": 0, "Data": {"Items": rows, "Total": len(rows)}}
            )
        ),
    ) as c:
        with pytest.raises(YicloudError, match="no identifier"):
            resolve(c, "ray", "friendly", "p", "z", True)
        rows[0]["RayJobName"] = "first"
        rows.append(dict(rows[0], RayJobName="second"))
        with pytest.raises(InputError, match="2 matches") as caught:
            resolve(c, "ray", "friendly", "p", "z", True)
    assert "RayJobName" in str(caught.value) and "Namespace" in str(caught.value)


@pytest.mark.parametrize("key", ["Data", "GetInferSetLogsQueryRangeData"])
def test_deployment_known_list_containers(key):
    assert items({key: [{"ID": "fixture"}]}) == [{"ID": "fixture"}]


def test_lookup_preserves_filters_across_pages_and_rejects_ambiguity(account):
    calls = []

    def handler(request):
        params = request.url.params
        calls.append(dict(params))
        assert params["Creator"] == "user"
        offset = int(params["Offset"])
        rows = [
            {"Project": "p", "ZoneId": "z", "Name": "same", "WorkspaceId": str(n)}
            for n in range(offset, min(offset + 20, 21))
        ]
        return httpx.Response(200, json={"Code": 0, "Data": {"Items": rows, "Total": 21}})

    with YicloudClient(account, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(InputError, match="21 matches"):
            resolve(client, "workspace", "same", "p", "z", True, lookup={"Creator": "user"})
    assert [c["Offset"] for c in calls] == ["0", "20"]
