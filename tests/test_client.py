"""All payloads in this suite are synthetic fixtures, not evidence of live platform responses."""

import hashlib
import hmac
import json
from urllib.parse import parse_qsl

import httpx
import pytest

from yicloud.auth import headers, sign
from yicloud.catalog import catalog, operation, validate
from yicloud.client import YicloudClient, encode_query
from yicloud.config import Account
from yicloud.errors import (
    AuthenticationError,
    InputError,
    NetworkError,
    UnsupportedProtocol,
    YicloudError,
)

JOB = {"Project": "fixture-project", "JobId": "fixture-job"}


def client(account, handler):
    return YicloudClient(account, transport=httpx.MockTransport(handler), sleep=lambda _: None)


def test_signature_unicode_repeated_stable_keys():
    query = "z=&a=%E4%B8%AD%E6%96%87&a=two+words&bare&false=false&zero=0"
    body = '{"Image":"测试","Enabled":false}'.encode()
    expected = hmac.new(
        b"secret",
        b"1700000000123public" + "a中文atwo wordsbarefalsefalsezzero0".encode() + body,
        hashlib.sha256,
    ).hexdigest()
    assert sign("1700000000123", "public", "secret", query, body) == expected


def test_token_priority_and_basic():
    a = Account(token="fixture-token", public_key="p", secret_key="s", service_account=True)
    assert headers(a, 1, "", b"")["Authorization"] == "fixture-token"
    a.token = ""
    assert headers(a, 1, "", b"")["Authorization"] == "Basic cDpz"
    a.secret_key = ""
    with pytest.raises(AuthenticationError):
        headers(a, 1, "", b"")


def test_catalog_all_refs_resolve_and_paths():
    c = catalog()
    assert len(c["operations"]) == 227
    assert len({(o["service"], o["action"]) for o in c["operations"]}) == 227

    def check(value, defs):
        if isinstance(value, dict):
            if "ref" in value:
                assert value["ref"] in defs
            for child in value.values():
                check(child, defs)
        elif isinstance(value, list):
            for child in value:
                check(child, defs)

    for defs in c["definitions"].values():
        check(defs, defs)
    assert operation("fs/alpha", "ListDir")["path"] == "/yifs/v1alpha1/ListFiles"
    assert operation("fs/alpha", "SetFilesetQuota")["path"] == "/yifs/v1alpha1/FilesetQuota"


def test_query_arrays_zero_false_unicode_null():
    q = encode_query(
        {"z": 0, "a": ["中文", "two words"], "bool": False, "empty": "", "null": None}, {}
    )
    assert parse_qsl(q, keep_blank_values=True) == [
        ("a", "中文"),
        ("a", "two words"),
        ("bool", "false"),
        ("empty", ""),
        ("null", ""),
        ("z", "0"),
    ]


def test_input_nested_types_and_unknown():
    op = operation("job", "CreateJob")
    valid = {
        "Name": "test",
        "Project": "test",
        "ZoneId": "test",
        "TaskSpecs": {"t0": {"Command": [], "Env": {}, "Image": "test", "Replicas": 0}},
    }
    validate(op, valid)
    valid["TaskSpecs"]["t0"]["Replicas"] = False
    with pytest.raises(InputError, match="integer"):
        validate(op, valid)
    with pytest.raises(InputError, match="required"):
        validate(operation("job", "GetJob"), {"Project": None, "JobId": "j"})
    with pytest.raises(InputError, match="unknown"):
        validate(operation("job", "GetJob"), dict(JOB, jobid="bad"))
    validate(operation("job", "GetJob"), dict(JOB, Future=False), True)


def test_exact_body_signed_once(account):
    def handler(request):
        assert request.method == "POST"
        assert request.url.path == "/job/v1alpha1/StopJob"
        assert request.headers["X-OGW-SIGN"] == sign(
            request.headers["X-OGW-TICK"],
            account.public_key,
            account.secret_key,
            "",
            request.content,
        )
        assert json.loads(request.content) == dict(JOB, ZoneId="测试")
        return httpx.Response(200, json={"Code": 0}, headers={"X-OGW-Request-Id": "fixture-id"})

    with client(account, handler) as c:
        r = c.call("job", "StopJob", dict(JOB, ZoneId="测试"))
        assert r.data is None and r.request_id == "fixture-id"


@pytest.mark.parametrize(
    "status,body", [(400, {"Code": 0}), (200, {"Code": 100, "Msg": "fixture-error"})]
)
def test_http_and_business_errors(account, status, body):
    with client(account, lambda _: httpx.Response(status, json=body)) as c:
        with pytest.raises(YicloudError):
            c.call("job", "GetJob", JOB)


@pytest.mark.parametrize("readonly,expected", [(True, 3), (False, 1)])
def test_transport_retry_safety(account, readonly, expected):
    calls = []

    def handler(req):
        calls.append(req)
        raise httpx.ReadTimeout("fixture disconnect")

    with client(account, handler) as c:
        with pytest.raises(NetworkError) as exc:
            c.call("job", "GetJob" if readonly else "StopJob", JOB)
        assert exc.value.outcome_unknown is (not readonly)
    assert len(calls) == expected


def test_read_http_retry_and_no_redirect(account):
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(
            503 if len(calls) < 3 else 200, json={"Code": 0, "Data": {"Phase": "Running"}}
        )

    with client(account, handler) as c:
        assert c.call("job", "GetJob", JOB).data["Phase"] == "Running"
    assert len(calls) == 3
    with client(
        account, lambda _: httpx.Response(302, headers={"Location": "https://elsewhere.invalid/"})
    ) as c:
        with pytest.raises(YicloudError, match="302"):
            c.call("job", "GetJob", JOB)


def test_special_responses_and_deferred(account):
    with client(account, lambda _: httpx.Response(200, json={"files": [], "total": 0})) as c:
        assert c.call("fs/alpha", "ListDir", {"path": "/fixture"}).data == {"files": [], "total": 0}
    with client(account, lambda _: httpx.Response(204)) as c:
        assert c.call("job", "StopJob", JOB).data is None
    with client(account, lambda _: httpx.Response(200, text="<html>fixture</html>")) as c:
        with pytest.raises(YicloudError, match="Invalid JSON"):
            c.call("job", "GetJob", JOB)
        with pytest.raises(UnsupportedProtocol):
            c.call("inferset", "GetInferSetTerminal", {"Project": "p", "ID": "i"})


def test_download_atomic_and_failure_preserves_destination(account, tmp_path):
    target = tmp_path / "logs.txt"
    target.write_text("old")
    params = {"Project": "p", "ID": "i", "Start": 0, "End": 1}
    with client(account, lambda _: httpx.Response(500)) as c:
        with pytest.raises(YicloudError):
            c.call("inferset", "DownloadInferSetLogs", params, output=target)
    assert target.read_text() == "old"
    with client(account, lambda _: httpx.Response(200, content=b"fixture logs")) as c:
        assert c.call("inferset", "DownloadInferSetLogs", params, output=target).data["bytes"] == 12
    assert target.read_bytes() == b"fixture logs"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["logs.txt"]


def test_dry_run_no_auth_or_transport(account):
    def handler(_):
        pytest.fail("dry run sent a request")

    with client(Account(), handler) as c:
        result = c.dry_run("job", "StopJob", JOB)
    assert result["body"] == JOB and "headers" not in result


def test_sku_type_is_compute_class_not_visibility_scope():
    op = operation("mc", "ListSKUs")
    validate(op, {"SKUType": "gpu", "Scope": "public"})
    with pytest.raises(InputError, match="one of"):
        validate(op, {"SKUType": "public"})


def test_http_failure_preserves_platform_reason_and_request_id(account):
    with client(
        account,
        lambda _: httpx.Response(
            400,
            json={"Code": -1, "Msg": "fixture key not found"},
            headers={"X-OGW-Request-Id": "fixture-request"},
        ),
    ) as c:
        with pytest.raises(YicloudError) as caught:
            c.call("job", "GetJob", JOB)
    error = caught.value
    assert str(error) == "HTTP 400: fixture key not found"
    assert error.code == -1 and error.http_status == 400
    assert error.request_id == "fixture-request"
    assert error.as_dict()["http_status"] == 400


def test_http_error_body_cannot_echo_credentials_or_signature(account):
    def handler(request):
        message = " ".join([account.public_key, account.secret_key, request.headers["X-OGW-SIGN"]])
        return httpx.Response(400, json={"Code": -1, "Msg": message})

    with client(account, handler) as c:
        with pytest.raises(YicloudError) as caught:
            c.call("job", "GetJob", JOB)
    assert account.public_key not in str(caught.value)
    assert account.secret_key not in str(caught.value)
    assert str(caught.value) == "HTTP 400: [REDACTED] [REDACTED] [REDACTED]"
