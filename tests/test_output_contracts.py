"""Synthetic repeated-secret responses and the public CLI disclosure boundary."""

import copy
import json

import httpx
import pytest
from click.testing import CliRunner

from yicloud.cli import main
from yicloud.output import redact, secret_values


def test_sensitive_values_are_hidden_across_sibling_containers_without_mutation():
    secret = "synthetic-returned-token"
    value = {
        "url": f"https://example.invalid/?token={secret}",
        "messages": [f"connect with {secret}"],
        "credentials": ({"name": "AccessToken", "value": secret},),
    }
    original = copy.deepcopy(value)
    hidden = redact(value)
    assert secret not in json.dumps(hidden)
    assert hidden["url"] == "https://example.invalid/?token=[REDACTED]"
    assert secret_values(value) == [secret]
    assert value == original


def test_overlapping_secret_values_are_hidden_longest_first():
    short = "synthetic-secret"
    long = short + "-longer-value"
    value = {"SecretKey": long, "message": f"{long} and {short}"}
    hidden = redact(value, secrets=[short, short])
    assert hidden["message"] == "[REDACTED] and [REDACTED]"


def test_show_secrets_reveals_new_values_but_keeps_existing_credentials_hidden():
    returned = "synthetic-new-token"
    existing = "synthetic-existing-credential"
    value = {"AccessToken": returned, "url": f"https://example.invalid/{returned}/{existing}"}
    shown = redact(value, secrets=(secret for secret in [existing]), show=True)
    assert shown["AccessToken"] == returned
    assert shown["url"] == f"https://example.invalid/{returned}/[REDACTED]"


def test_repeated_secret_detection_preserves_token_metrics_and_tokenizer():
    value = {
        "AccessToken": "synthetic-hidden-token",
        "num_tokens": 42,
        "token_count": 8,
        "max_new_tokens": 32,
        "tokenizer": "example/model",
        "url": "https://example.invalid/?token=synthetic-hidden-token",
    }
    hidden = redact(value)
    for key in ("num_tokens", "token_count", "max_new_tokens", "tokenizer"):
        assert hidden[key] == value[key]
    assert "synthetic-hidden-token" not in json.dumps(hidden)


@pytest.mark.parametrize("show", [False, True])
@pytest.mark.parametrize("json_output", [False, True])
def test_sandbox_cli_repeated_returned_secret_respects_disclosure_mode(
    monkeypatch, show, json_output
):
    existing = "synthetic-existing-account-credential"
    returned = "synthetic-sandbox-returned-token"
    data = {
        "Endpoints": {
            "AccessToken": returned,
            "Endpoints": {"browser": {"ExternalUrl": f"https://example.invalid/?token={returned}"}},
        },
        "message": f"Existing credential {existing}",
        "tokenizer": "example/model",
        "num_tokens": 42,
    }
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path))
        return httpx.Response(200, json={"Code": 0, "Data": data})

    original_client = httpx.Client
    monkeypatch.setenv("YICLOUD_AUTHN_TOKEN", existing)
    monkeypatch.setattr(
        "yicloud.transport.httpx.Client",
        lambda **kwargs: original_client(**dict(kwargs, transport=httpx.MockTransport(handler))),
    )
    args = (["--json"] if json_output else []) + (["--show-secrets"] if show else [])
    result = CliRunner().invoke(
        main,
        [*args, "sandbox", "get-sandbox", "--project-name", "fixture", "--sandbox-id", "fixture"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    output = payload["data"] if json_output else payload
    expected = returned if show else "[REDACTED]"
    assert output["Endpoints"]["AccessToken"] == expected
    assert output["Endpoints"]["Endpoints"]["browser"]["ExternalUrl"].endswith(expected)
    assert (returned in result.output) is show
    assert existing not in result.output
    assert output["num_tokens"] == 42 and output["tokenizer"] == "example/model"
    assert calls == [("GET", "/sandbox/v1alpha1/GetSandbox")]


def test_api_schema_preserves_sensitive_field_types_and_descriptions():
    result = CliRunner().invoke(main, ["--json", "api", "describe", "iam", "CreateUser"])
    assert result.exit_code == 0, result.output
    password = json.loads(result.output)["data"]["schema"]["properties"]["Password"]
    assert password["type"] == "string"
    assert password["description"] and password["description"] != "[REDACTED]"
