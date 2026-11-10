"""Synthetic regressions for the observed top-level platform error detail field."""

import json
from pathlib import Path
from urllib.parse import quote, quote_plus

import httpx
import pytest

from yicloud.cli import main
from yicloud.errors import YicloudError
from yicloud.protocol import decode_response


def fake_http(monkeypatch, handler):
    original = httpx.Client
    monkeypatch.setenv("YICLOUD_AUTHN_TOKEN", "synthetic/account+token")
    monkeypatch.setattr(
        "yicloud.transport.httpx.Client",
        lambda **kwargs: original(**dict(kwargs, transport=httpx.MockTransport(handler))),
    )


# Container traversal and URL representations are shared by all decoder paths.
# Keep both shapes and every representation on the two business-error paths,
# plus ordinary/download HTTP errors without repeating the full product.
@pytest.mark.parametrize(
    "status,download,nested,encode",
    [
        (200, False, False, lambda value: value),
        (200, False, True, lambda value: quote(value, safe="")),
        (200, False, True, quote_plus),
        (200, True, False, lambda value: value),
        (200, True, True, lambda value: quote(value, safe="")),
        (200, True, True, quote_plus),
        (400, False, False, lambda value: quote(value, safe="")),
        (400, True, True, quote_plus),
    ],
)
def test_cli_details_redact_sensitive_sibling_values(
    monkeypatch, separated_cli_runner, tmp_path, status, download, nested, encode
):
    secret = "SYNTHETIC_SERVER_TOKEN_VALUE/plus+ space=雪"
    named_secret = "SYNTHETIC_NAMED_SECRET/plus+ space=云"
    data = (
        {
            "layers": [
                {"credentials": {"clientSecret": secret}},
                {"name": "API_TOKEN", "value": named_secret},
            ]
        }
        if nested
        else {"AccessToken": secret, "Password": named_secret}
    )
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status,
            json={
                "Code": 1,
                "Msg": f"generic token {encode(secret)}; named credential {encode(named_secret)}",
                "_err": f"upstream token {encode(secret)}; named credential {encode(named_secret)}",
                "Data": data,
                "Extra": "private-extra",
            },
        )

    fake_http(monkeypatch, handler)
    output = tmp_path / "download"
    args = ["--json", "--show-secrets", "api", "call"]
    if download:
        args += ["inferset", "DownloadInferSetLogs", "--output", str(output)]
        params = {"Project": "synthetic", "ID": "synthetic", "Start": 1, "End": 2}
    else:
        args += ["workspace", "CreateWorkspace"]
        params = {"Name": "synthetic", "Project": "synthetic", "ZoneId": "synthetic"}
    result = separated_cli_runner.invoke(main, [*args, "--file", "-"], input=json.dumps(params))
    assert result.exit_code == 1 and result.stdout == "" and len(calls) == 1
    error = json.loads(result.stderr)["error"]
    assert error["message"] == ("HTTP 400: " if status == 400 else "") + (
        "generic token [REDACTED]; named credential [REDACTED]"
    )
    assert error["hints"] == ["upstream token [REDACTED]; named credential [REDACTED]"]
    assert error["http_status"] == status and error["code"] == 1
    for value in (secret, named_secret, encode(secret), encode(named_secret), "private-extra"):
        assert value not in result.stderr
    assert "Data" not in error and not output.exists()


@pytest.mark.parametrize("status,download", [(200, False), (200, True), (400, False)])
def test_cli_message_redacts_sensitive_siblings_without_detail(
    monkeypatch, separated_cli_runner, tmp_path, status, download
):
    secret = "SYNTHETIC_MESSAGE_REFLECTED_TOKEN"
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status,
            json={"Code": 1, "Msg": f"upstream token {secret}", "Data": {"AccessToken": secret}},
        )

    fake_http(monkeypatch, handler)
    output = tmp_path / "download"
    if download:
        args = ["inferset", "DownloadInferSetLogs", "--output", str(output)]
        params = {"Project": "synthetic", "ID": "synthetic", "Start": 1, "End": 2}
    else:
        args = ["workspace", "CreateWorkspace"]
        params = {"Name": "synthetic", "Project": "synthetic", "ZoneId": "synthetic"}
    result = separated_cli_runner.invoke(
        main, ["--json", "api", "call", *args, "--file", "-"], input=json.dumps(params)
    )
    assert result.exit_code == 1 and result.stdout == "" and len(calls) == 1
    error = json.loads(result.stderr)["error"]
    assert error["message"] == ("HTTP 400: " if status == 400 else "") + (
        "upstream token [REDACTED]"
    )
    assert secret not in result.stderr and "hints" not in error
    assert error["code"] == 1 and error["http_status"] == status
    assert not output.exists()


@pytest.mark.parametrize(
    "json_output,status", [(True, 200), (True, 403), (True, 500), (False, 200)]
)
def test_workspace_cli_details_are_redacted_without_retry(
    monkeypatch, separated_cli_runner, json_output, status
):
    calls = []
    secret = "synthetic/input+secret"
    params = json.loads((Path(__file__).parent / "fixtures/requests/workspace.json").read_text())
    params["Env"] = {"API_TOKEN": secret}

    def handler(request):
        calls.append(request)
        assert json.loads(request.content) == params
        return httpx.Response(
            status,
            json={
                "Code": 1006003,
                "Msg": "开发机规格不合法",
                "_err": (
                    "workspace quota validation failed; quotaCPU unavailable; "
                    f"{secret} {quote(secret, safe='')} "
                    f"{request.headers['Authorization']} Bearer synthetic-unknown-token"
                ),
                "Data": {"_err": "private-nested-detail", "raw": "private-data"},
                "Extra": "private-extra",
            },
            headers={"X-OGW-Request-Id": "synthetic-request", "Extra": "private-header"},
        )

    fake_http(monkeypatch, handler)
    result = separated_cli_runner.invoke(
        main,
        (["--json"] if json_output else []) + ["workspace", "create", "--file", "-"],
        input=json.dumps(params),
    )
    assert result.exit_code == 1 and result.stdout == ""
    assert len(calls) == 1
    assert "quotaCPU unavailable" in result.stderr
    assert "[REDACTED]" in result.stderr
    for hidden in (
        secret,
        quote(secret, safe=""),
        "synthetic/account+token",
        "synthetic-unknown-token",
        "private-nested-detail",
        "private-data",
        "private-extra",
        "private-header",
    ):
        assert hidden not in result.stderr
    if json_output:
        error = json.loads(result.stderr)["error"]
        assert error == {
            "kind": "authentication" if status == 403 else "platform",
            "message": (f"HTTP {status}: " if status != 200 else "") + "开发机规格不合法",
            "code": 1006003,
            "request_id": "synthetic-request",
            "outcome_unknown": status == 500,
            "http_status": status,
            "hints": [
                "workspace quota validation failed; quotaCPU unavailable; "
                "[REDACTED] [REDACTED] [REDACTED] Bearer [REDACTED]"
            ],
        }
    else:
        assert "Hint:" in result.stderr


def test_nodes_cli_preserves_generic_message_and_concrete_manager_requirement(
    monkeypatch, separated_cli_runner
):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "Code": 101,
                "Msg": "鉴权失败",
                "_err": "only tenant manager or project manager can query project node list",
            },
        )

    fake_http(monkeypatch, handler)
    result = separated_cli_runner.invoke(
        main, ["--json", "resources", "nodes", "--project", "synthetic", "--zone", "test"]
    )
    assert result.exit_code == 1 and result.stdout == "" and len(calls) == 1
    error = json.loads(result.stderr)["error"]
    assert error["message"] == "鉴权失败" and error["kind"] == "platform"
    assert error["code"] == 101 and error["http_status"] == 200
    assert error["outcome_unknown"] is False
    assert error["hints"] == ["only tenant manager or project manager can query project node list"]


@pytest.mark.parametrize("mode", ["envelope", "direct", "file"])
def test_invalid_code_is_not_replaced_by_detail(mode, tmp_path):
    with pytest.raises(YicloudError, match="invalid platform Code") as caught:
        decode_response(
            dict(read_only=False, response_mode=mode),
            httpx.Response(200, json={"Code": True, "_err": "must not be surfaced"}),
            output=tmp_path / "download",
        )
    assert caught.value.hints == []
    assert caught.value.outcome_unknown is True and caught.value.http_status == 200
