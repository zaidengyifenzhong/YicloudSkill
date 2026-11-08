"""ListNodes live nil-slice compatibility stays scoped and fails closed."""

import json

import httpx
import pytest
from click.testing import CliRunner

from yicloud.cli import main
from yicloud.client import YicloudClient


def invoke_nodes(monkeypatch, account, data, *, all_pages=True, extra=(), code=0):
    calls = []

    def handler(request):
        calls.append(request)
        payload = data(request, len(calls)) if callable(data) else data
        return httpx.Response(
            200,
            json={"Code": code, "Msg": "鉴权失败" if code else "成功", "Data": payload},
            headers={"X-OGW-Request-Id": f"request-{len(calls)}"},
        )

    monkeypatch.setattr(
        "yicloud.commands.discovery.client_for",
        lambda _: YicloudClient(account, transport=httpx.MockTransport(handler)),
    )
    args = [
        "--json",
        "resources",
        "nodes",
        "--project",
        "p",
        "--zone",
        "z",
        "--set",
        'QuotaGroup="group-a"',
        "--set",
        'UsageType="workload"',
        "--set",
        'MachineType="GPU"',
        *extra,
    ]
    if all_pages:
        args.append("--all")
    result = CliRunner().invoke(main, args)
    return result, json.loads(result.output), calls


@pytest.mark.parametrize("all_pages", [False, True])
def test_null_nodes_with_explicit_zero_total_are_empty(monkeypatch, account, all_pages):
    data = {
        "Items": None,
        "Total": 0,
        "Limit": 20,
        "Offset": 0,
        "TotalNodeQuota": {"GPU": {"Usable": 0, "Total": 0}},
        "GpuOccupancyUsers": {},
    }
    result, payload, calls = invoke_nodes(monkeypatch, account, data, all_pages=all_pages)
    assert result.exit_code == 0, result.output
    assert payload["data"] == dict(data, Items=[])
    assert payload["meta"]["request_id"] == "request-1"
    assert len(calls) == 1
    assert calls[0].method == "GET"
    assert calls[0].url.path == "/mc/v1alpha1/ListNodes"
    assert dict(calls[0].url.params) == {
        "Project": "p",
        "ZoneId": "z",
        "QuotaGroup": "group-a",
        "UsageType": "workload",
        "MachineType": "GPU",
        "Offset": "0",
        "Limit": "20",
    }


@pytest.mark.parametrize("all_pages", [False, True])
@pytest.mark.parametrize(
    "patch,removed",
    [
        ({"Total": 1}, None),
        ({"Total": "0"}, None),
        ({"Total": False}, None),
        ({"Total": -1}, None),
        ({}, "Total"),
        ({}, "Items"),
        ({}, "Limit"),
        ({}, "Offset"),
        ({"Limit": 0}, None),
        ({"Limit": True}, None),
        ({"Offset": 1}, None),
        ({"Offset": False}, None),
        ({"Items": {}}, None),
    ],
)
def test_unverified_null_or_malformed_nodes_remain_errors(
    monkeypatch, account, all_pages, patch, removed
):
    data = dict(Items=None, Total=0, Limit=20, Offset=0)
    data.update(patch)
    if removed:
        data.pop(removed)
    result, payload, calls = invoke_nodes(monkeypatch, account, data, all_pages=all_pages)
    assert result.exit_code == 1
    assert payload["ok"] is False
    assert payload["error"]["request_id"] == "request-1"
    assert payload["error"]["http_status"] == 200
    assert payload["error"]["code"] is None
    assert len(calls) == 1


def test_all_nodes_preserves_metadata_and_advances_capped_pages(monkeypatch, account):
    def data(request, count):
        assert request.url.params["Offset"] == str(count - 1)
        return {
            "Items": [{"NodeName": f"node-{count}"}],
            "Total": 2,
            "Offset": count - 1,
            "Limit": 1,
            "TotalNodeQuota": {"GPU": {"Total": 16}},
            "GpuOccupancyUsers": {},
        }

    result, payload, calls = invoke_nodes(monkeypatch, account, data)
    assert result.exit_code == 0, result.output
    assert payload["data"]["Items"] == [{"NodeName": "node-1"}, {"NodeName": "node-2"}]
    assert payload["data"]["Total"] == 2
    assert payload["data"]["TotalNodeQuota"] == {"GPU": {"Total": 16}}
    assert payload["data"]["GpuOccupancyUsers"] == {}
    assert len(calls) == 2


def test_incomplete_nonnull_page_is_error_with_request_id(monkeypatch, account):
    data = {"Items": [], "Total": 1, "Limit": 20, "Offset": 0}
    result, payload, calls = invoke_nodes(monkeypatch, account, data)
    assert result.exit_code == 1
    assert "before the advertised total" in payload["error"]["message"]
    assert payload["error"]["request_id"] == "request-1"
    assert len(calls) == 1


def test_nonzero_offset_is_allowed_when_echoed_for_explicit_empty_scope(monkeypatch, account):
    data = {"Items": None, "Total": 0, "Limit": 20, "Offset": 20}
    result, payload, calls = invoke_nodes(monkeypatch, account, data, extra=("--set", "Offset=20"))
    assert result.exit_code == 0, result.output
    assert payload["data"] == dict(data, Items=[])
    assert len(calls) == 1


@pytest.mark.parametrize("all_pages", [False, True])
def test_platform_denial_is_not_retried_or_reclassified(monkeypatch, account, all_pages):
    result, payload, calls = invoke_nodes(monkeypatch, account, None, code=101, all_pages=all_pages)
    assert result.exit_code == 1
    assert payload["error"]["kind"] == "platform"
    assert payload["error"]["code"] == 101
    assert payload["error"]["message"] == "鉴权失败"
    assert payload["error"]["request_id"] == "request-1"
    assert len(calls) == 1


def test_other_resource_lists_do_not_accept_null_items(monkeypatch, account):
    def handler(request):
        return httpx.Response(200, json={"Code": 0, "Data": {"Items": None, "Total": 0}})

    monkeypatch.setattr(
        "yicloud.commands.discovery.client_for",
        lambda _: YicloudClient(account, transport=httpx.MockTransport(handler)),
    )
    result = CliRunner().invoke(
        main, ["--json", "resources", "quota-groups", "--project", "p", "--all"]
    )
    assert result.exit_code == 1
    assert "Unrecognized list response" in json.loads(result.output)["error"]["message"]


def test_later_null_zero_page_cannot_erase_advertised_nodes(monkeypatch, account):
    def data(request, count):
        if count == 1:
            return {"Items": [{"NodeName": "node-1"}], "Total": 2, "Limit": 1, "Offset": 0}
        return {"Items": None, "Total": 0, "Limit": 1, "Offset": 1}

    result, payload, calls = invoke_nodes(monkeypatch, account, data)
    assert result.exit_code == 1
    assert "Total changed between pages" in payload["error"]["message"]
    assert payload["error"]["request_id"] == "request-2"
    assert len(calls) == 2
