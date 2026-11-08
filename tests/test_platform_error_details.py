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


@pytest.mark.parametrize("status", [200, 400])
@pytest.mark.parametrize("download", [False, True])
@pytest.mark.parametrize("nested", [False, True])
@pytest.mark.parametrize(
    "encode", [lambda value: value, lambda value: quote(value, safe=""), quote_plus]
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


@pytest.mark.parametrize("status", [200, 400])
@pytest.mark.parametrize("download", [False, True])
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


@pytest.mark.parametrize("json_output", [False, True])
@pytest.mark.parametrize("status", [200, 403, 500])
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
@pytest.mark.parametrize("status", [200, 400])
@pytest.mark.parametrize("detail", [None, "", " \n\t ", False, 0, 123, [], {}, ["detail"]])
def test_empty_and_nonstring_details_preserve_legacy_errors(tmp_path, mode, status, detail):
    payload = {"Code": 101, "Msg": "legacy reason", "_err": detail}
    response = httpx.Response(status, json=payload)
    with pytest.raises(YicloudError) as caught:
        decode_response(
            dict(read_only=True, response_mode=mode), response, output=tmp_path / "download"
        )
    error = caught.value
    assert str(error) == ("HTTP 400: " if status == 400 else "") + "legacy reason"
    assert error.hints == [] and "hints" not in error.as_dict()
    assert error.code == 101 and error.http_status == status
    assert not (tmp_path / "download").exists()


@pytest.mark.parametrize("status", [200, 400])
@pytest.mark.parametrize("detail", ["legacy reason", " legacy reason \n", "Bearer secret"])
def test_duplicate_detail_is_suppressed_after_redaction(status, detail):
    message = "Bearer other" if detail.startswith("Bearer") else "legacy reason"
    with pytest.raises(YicloudError) as caught:
        decode_response(
            dict(read_only=True, response_mode="envelope"),
            httpx.Response(status, json={"Code": 1, "Msg": message, "_err": detail}),
        )
    assert caught.value.hints == []


@pytest.mark.parametrize("mode", ["envelope", "direct", "file"])
def test_detail_survives_each_platform_error_response_mode(tmp_path, mode):
    with pytest.raises(YicloudError) as caught:
        decode_response(
            dict(read_only=True, response_mode=mode),
            httpx.Response(200, json={"Code": -1, "Msg": "generic", "_err": " specific \n"}),
            output=tmp_path / "download",
        )
    assert str(caught.value) == "generic"
    assert caught.value.hints == ["specific"]
    assert caught.value.http_status == 200
    assert not (tmp_path / "download").exists()


@pytest.mark.parametrize("mode", ["envelope", "direct", "file"])
@pytest.mark.parametrize("status", [200, 400])
def test_response_sibling_secrets_are_collected_in_all_decoder_error_paths(tmp_path, mode, status):
    with pytest.raises(YicloudError) as caught:
        decode_response(
            dict(read_only=True, response_mode=mode),
            httpx.Response(
                status,
                json={
                    "Code": 1,
                    "Msg": "generic SYNTHETIC_SERVER_TOKEN_VALUE",
                    "_err": "upstream token SYNTHETIC_SERVER_TOKEN_VALUE",
                    "Data": {"AccessToken": "SYNTHETIC_SERVER_TOKEN_VALUE"},
                },
            ),
            output=tmp_path / "download",
        )
    assert caught.value.hints == ["upstream token [REDACTED]"]
    assert str(caught.value) == ("HTTP 400: " if status == 400 else "") + "generic [REDACTED]"


@pytest.mark.parametrize("mode", ["envelope", "direct", "file"])
def test_missing_detail_preserves_legacy_error_and_reports_http_status(tmp_path, mode):
    with pytest.raises(YicloudError) as caught:
        decode_response(
            dict(read_only=True, response_mode=mode),
            httpx.Response(202, json={"Code": 9, "Msg": "legacy reason"}),
            output=tmp_path / "download",
        )
    assert caught.value.as_dict() == {
        "kind": "platform",
        "message": "legacy reason",
        "code": 9,
        "request_id": None,
        "outcome_unknown": False,
        "http_status": 202,
    }


@pytest.mark.parametrize("mode", ["envelope", "direct", "file"])
def test_success_does_not_interpret_detail(tmp_path, mode):
    response = httpx.Response(200, json={"Code": 0, "_err": "ignored", "Data": {"ok": True}})
    output = tmp_path / "download"
    data = decode_response(dict(read_only=True, response_mode=mode), response, output=output)
    if mode == "file":
        assert data == {"path": str(output), "bytes": len(response.content)}
        assert output.read_bytes() == response.content
    else:
        assert data == {"ok": True}


@pytest.mark.parametrize("message", [None, False, 17, {"reason": "legacy"}])
def test_nonstring_message_compatibility_with_valid_detail(message):
    with pytest.raises(YicloudError) as caught:
        decode_response(
            dict(read_only=False, response_mode="envelope"),
            httpx.Response(200, json={"Code": 9, "Msg": message, "_err": "specific detail"}),
        )
    assert str(caught.value) == str(message)
    assert caught.value.hints == ["specific detail"]
    assert caught.value.outcome_unknown is False


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
