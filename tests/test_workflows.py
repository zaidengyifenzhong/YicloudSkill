"""Synthetic workflow responses; no live account is used."""

import json

import httpx
import pytest

from yicloud.client import YicloudClient
from yicloud.errors import InputError, YicloudError
from yicloud.workflows import (
    follow_logs,
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


@pytest.mark.parametrize("invalid", [None, "unexpected-row"])
def test_name_lookup_rejects_malformed_rows_even_beside_a_match(account, invalid):
    rows = [{"Name": "dev", "WorkspaceId": "w", "Project": "p", "ZoneId": "z"}, invalid]
    with YicloudClient(
        account,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"Code": 0, "Data": {"Items": rows}})
        ),
    ) as client:
        with pytest.raises(YicloudError, match="name lookup is not verified"):
            resolve(client, "workspace", "dev", "p", "z", True)


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


def test_follow_does_not_skip_logs_indexed_after_an_empty_poll(account):
    calls = []
    emitted = []
    clocks = iter([10 * 10**9, 20 * 10**9, 30 * 10**9])
    timestamp = 10**9

    def handler(request):
        query = dict(request.url.params)
        calls.append(query)
        # This event becomes searchable after a delay exceeding the old 3s window.
        rows = []
        if len(calls) > 1 and int(query["Start"]) <= timestamp:
            rows = [{"Timestamp": str(timestamp), "Line": "late-indexed-marker"}]
        return httpx.Response(200, json={"Code": 0, "Data": {"Items": rows}})

    def sleep(_):
        if len(calls) == 2:
            raise KeyboardInterrupt()

    with YicloudClient(account, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(KeyboardInterrupt):
            follow_logs(
                client,
                "job",
                {"Project": "p", "JobId": "j", "Start": 0, "Limit": 200},
                emitted.append,
                sleep=sleep,
                clock=lambda: next(clocks),
            )
    assert [int(query["Start"]) for query in calls] == [0, 0]
    assert emitted == [{"Timestamp": str(timestamp), "Line": "late-indexed-marker"}]


@pytest.mark.parametrize("kind", ["job"])
def test_follow_stops_when_a_full_timestamp_boundary_cannot_advance(account, kind):
    calls = []
    rows = [{"Timestamp": "100", "Line": "a"}, {"Timestamp": "100", "Line": "b"}]

    def handler(request):
        calls.append(dict(request.url.params))
        assert len(calls) <= 2, "Full timestamp boundary must not poll indefinitely"
        return httpx.Response(200, json={"Code": 0, "Data": {"Items": rows}})

    emitted = []
    id_field = {"job": "JobId", "ray": "JobName", "serving": "ID"}[kind]
    params = log_params(kind, {"Project": "p", id_field: "resource"}, start=0, end=200, limit=2)
    with YicloudClient(account, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(YicloudError, match="full and cannot advance") as error:
            follow_logs(
                client, kind, params, emitted.append, sleep=lambda _: None, clock=lambda: 200
            )
    assert emitted == rows
    start_field = "StartTime" if kind == "ray" else "Start"
    assert [int(query[start_field]) for query in calls] == [0, 100]
    assert "--limit" in str(error.value) and "--instance" in str(error.value)


def test_follow_allows_full_windows_that_advance(account):
    starts = []
    emitted = []

    def handler(request):
        start = int(request.url.params["Start"])
        starts.append(start)
        return httpx.Response(
            200,
            json={"Code": 0, "Data": {"Items": [{"Timestamp": str(start + 1), "Line": "a"}]}},
        )

    def sleep(_):
        if len(starts) == 3:
            raise KeyboardInterrupt()

    with YicloudClient(account, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(KeyboardInterrupt):
            follow_logs(
                client,
                "job",
                {"Project": "p", "JobId": "j", "Limit": 1, "Start": 0},
                emitted.append,
                sleep=sleep,
                clock=lambda: 20,
            )
    assert starts == [0, 1, 2]
    assert [row["Timestamp"] for row in emitted] == ["1", "2", "3"]


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


@pytest.mark.parametrize("offset,expected_offsets", [(0, [0, 100]), (50, [50]), (150, [150])])
def test_pagination_respects_server_limit_and_initial_offset(account, offset, expected_offsets):
    calls = []

    def handler(request):
        start = int(request.url.params["Offset"])
        calls.append(start)
        rows = [{"ID": n} for n in range(start, min(start + 100, 150))]
        return httpx.Response(200, json={"Code": 0, "Data": {"Items": rows, "Total": 150}})

    with YicloudClient(account, transport=httpx.MockTransport(handler)) as client:
        result = paginated(
            client,
            "volume",
            "ListQuotaGroupVolumes",
            {
                "Project": "p",
                "QuotaGroup": "q",
                "Limit": 200,
                "Offset": offset,
            },
            True,
        )
    assert calls == expected_offsets
    assert result.data == {"Items": [{"ID": n} for n in range(offset, 150)], "Total": 150 - offset}


@pytest.mark.parametrize("page,total", [([{"ID": 1}], 2), ([], 2)])
def test_pagination_does_not_report_incomplete_or_repeated_results(account, page, total):
    def handler(request):
        return httpx.Response(200, json={"Code": 0, "Data": {"Items": page, "Total": total}})

    with YicloudClient(account, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(YicloudError, match="Pagination"):
            paginated(
                client,
                "volume",
                "ListQuotaGroupVolumes",
                {
                    "Project": "p",
                    "QuotaGroup": "q",
                    "Limit": 200,
                },
                True,
            )


@pytest.mark.parametrize("total,invalid_page", [(None, 0), (None, 1), (True, 0), (-1, 0)])
def test_complete_pagination_rejects_present_invalid_totals(account, total, invalid_page):
    offsets = []
    params = {"Project": "p", "ZoneId": "z", "Limit": 1}

    def handler(request):
        offset = int(request.url.params["Offset"])
        offsets.append(offset)
        data = (
            {"Items": [], "Total": total}
            if offset == invalid_page
            else {"Items": [{"JobId": "j"}], "Total": 2}
        )
        return httpx.Response(
            200,
            json={"Code": 0, "Data": data},
            headers={"X-OGW-Request-Id": f"fixture-page-{offset}"},
        )

    with YicloudClient(account, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(YicloudError, match="invalid Total") as error:
            paginated(client, "job", "ListJobs", params, True)
    assert offsets == list(range(invalid_page + 1))
    assert error.value.request_id == f"fixture-page-{invalid_page}"
    assert params == {"Project": "p", "ZoneId": "z", "Limit": 1}


@pytest.mark.parametrize("invalid_page", [0, 1], ids=["first-page", "later-page"])
def test_complete_pagination_rejects_rows_exceeding_total(account, invalid_page):
    offsets = []

    def handler(request):
        offset = int(request.url.params["Offset"])
        offsets.append(offset)
        return httpx.Response(
            200,
            json={
                "Code": 0,
                "Data": {
                    "Items": [{"JobId": f"j-{offset}"}],
                    "Total": offset if offset == invalid_page else 2,
                },
            },
            headers={"X-OGW-Request-Id": f"fixture-page-{offset}"},
        )

    with YicloudClient(account, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(YicloudError, match="exceeds Total") as error:
            paginated(client, "job", "ListJobs", {"Project": "p", "ZoneId": "z", "Limit": 1}, True)
    assert offsets == list(range(invalid_page + 1))
    assert error.value.request_id == f"fixture-page-{invalid_page}"


@pytest.mark.parametrize("native_list", [False, True], ids=["no-total", "native-list"])
def test_complete_pagination_keeps_omitted_total_compatibility(account, native_list):
    offsets = []
    rows = [{"JobId": f"j-{n}"} for n in range(3)]

    def handler(request):
        offset = int(request.url.params["Offset"])
        offsets.append(offset)
        page = rows[offset : offset + 2]
        return httpx.Response(
            200, json={"Code": 0, "Data": page if native_list else {"Items": page}}
        )

    with YicloudClient(account, transport=httpx.MockTransport(handler)) as client:
        result = paginated(
            client, "job", "ListJobs", {"Project": "p", "ZoneId": "z", "Limit": 2}, True
        )
    assert result.data == {"Items": rows, "Total": 3}
    assert offsets == [0, 2]


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
