"""Synthetic workflow responses; no live account is used."""

import json

import httpx
import pytest

from yicloud.client import YicloudClient
from yicloud.errors import InputError, YicloudError
from yicloud.workflows import follow_logs, log_params, paginated, resolve, wait


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
