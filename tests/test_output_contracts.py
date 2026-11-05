"""Synthetic repeated-secret responses and the public CLI disclosure boundary."""

import copy
import json
import re
from urllib.parse import quote, quote_plus

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


@pytest.mark.parametrize(
    "encode",
    [
        quote,
        lambda value: quote(value, safe=""),
        quote_plus,
        lambda value: re.sub(
            r"%[0-9A-F]{2}", lambda match: match[0].lower(), quote(value, safe="")
        ),
    ],
    ids=["path-percent", "percent", "form", "lowercase-escape-hex"],
)
def test_known_secrets_are_hidden_in_common_url_representations(encode):
    secret = "AbCase/plus+ space=雪"
    encoded = encode(secret)
    value = {"AccessToken": secret, "url": f"https://example.invalid/?token={encoded}"}
    original = copy.deepcopy(value)
    hidden = redact(value)
    assert hidden["url"] == "https://example.invalid/?token=[REDACTED]"
    assert secret not in json.dumps(hidden) and encoded not in json.dumps(hidden)
    assert value == original
    # Explicit disclosure applies to new values and their URL representations.
    assert redact(value, show=True) == value


def test_percent_escape_case_matching_does_not_change_credential_case():
    secret = "AbCase/Token+Value="
    same = quote(secret, safe="").replace("%2F", "%2f").replace("%2B", "%2b")
    different = same.replace("AbCase", "aBCase")
    hidden = redact({"AccessToken": secret, "same": same, "different": different})
    assert hidden["same"] == "[REDACTED]"
    assert hidden["different"] == different


@pytest.mark.parametrize("scheme", ["Bearer", "Basic", "bEaReR"])
@pytest.mark.parametrize("show", [False, True])
def test_existing_authorization_hides_full_bare_and_encoded_credentials(scheme, show):
    credential = "Synthetic/Existing+Token=="
    authorization = f"{scheme} {credential}"
    value = {
        "header": authorization,
        "bare": credential,
        "encoded": quote(credential, safe=""),
        "form_header": quote_plus(authorization),
    }
    hidden = redact(value, secrets=[authorization], show=show)
    assert set(hidden.values()) == {"[REDACTED]"}


@pytest.mark.parametrize(
    "container",
    [
        {"type": "Bearer", "value": "synthetic-container-secret"},
        [{"type": "Bearer", "value": "synthetic-container-secret"}],
        ({"type": "Bearer", "value": "synthetic-container-secret"},),
        {"type": "Bearer", "value": ["synthetic-container-secret"]},
        {"type": "Bearer", "details": {"Value": "synthetic-container-secret"}},
    ],
    ids=["object", "list", "tuple", "value-list", "nested-value"],
)
def test_sensitive_containers_collect_value_leaves_without_metadata(container):
    metadata = {"type": "Bearer", "description": "token", "value": "public"}
    value = {
        "Credentials": container,
        "metadata": metadata,
        "url": "https://example.invalid/?token=synthetic-container-secret",
    }
    original = copy.deepcopy(value)
    assert secret_values(value) == ["synthetic-container-secret"]
    hidden = redact(value)
    assert hidden["Credentials"] == "[REDACTED]"
    assert hidden["metadata"] == metadata
    assert hidden["url"] == "https://example.invalid/?token=[REDACTED]"
    assert value == original


def test_generic_value_and_authorization_metadata_are_not_secrets():
    value = {"value": "public", "type": "Bearer", "description": "token"}
    assert secret_values(value) == []
    assert redact(value) == value
    container = {"Credentials": {"type": "Bearer", "description": "token"}, "type": "Bearer"}
    assert secret_values(container) == []
    assert redact(container)["type"] == "Bearer"


def test_named_secret_values_propagate_through_container_shapes():
    value = {
        "query": [{"name": "AccessToken", "value": ({"value": "synthetic-nested-secret"},)}],
        "url": "https://example.invalid/?token=synthetic-nested-secret",
    }
    assert secret_values(value) == ["synthetic-nested-secret"]
    assert redact(value)["url"] == "https://example.invalid/?token=[REDACTED]"


@pytest.mark.parametrize("show", [False, True])
def test_cli_finite_secret_representations_preserve_explicit_disclosure(monkeypatch, show):
    old = "Synthetic/Existing+Token=="
    new = "Synthetic/Returned+Token=="
    nested = "Synthetic/Nested+Token=="
    authorization = f"Bearer {old}"
    data = {
        "Authorization": f"Bearer {new}",
        "Credentials": [{"type": "Bearer", "value": nested}],
        "old_url": "https://example.invalid/?token=" + quote(old, safe="").replace("%2F", "%2f"),
        "old_header": quote_plus(authorization),
        "new_url": "https://example.invalid/?token=" + quote(new, safe=""),
        "nested_url": "https://example.invalid/?token=" + quote(nested, safe=""),
        "metadata": {"type": "Bearer", "value": "public", "description": "token"},
        "num_tokens": 42,
        "tokenizer": "example/model",
    }
    original_client = httpx.Client
    calls = []

    def handler(request):
        calls.append(request.method)
        assert request.headers["Authorization"] == authorization
        return httpx.Response(200, json={"Code": 0, "Data": data})

    monkeypatch.setenv("YICLOUD_AUTHN_TOKEN", authorization)
    monkeypatch.setattr(
        "yicloud.transport.httpx.Client",
        lambda **kwargs: original_client(**dict(kwargs, transport=httpx.MockTransport(handler))),
    )
    result = CliRunner().invoke(
        main,
        [
            "--json",
            *(["--show-secrets"] if show else []),
            "sandbox",
            "get-sandbox",
            "--project-name",
            "fixture",
            "--sandbox-id",
            "fixture",
        ],
    )
    assert result.exit_code == 0, result.output
    output = json.loads(result.output)["data"]
    assert output["old_url"] == "https://example.invalid/?token=[REDACTED]"
    assert output["old_header"] == "[REDACTED]"
    for field in ("Authorization", "Credentials", "new_url", "nested_url"):
        if show:
            assert output[field] == data[field]
        elif field.endswith("_url"):
            assert output[field] == "https://example.invalid/?token=[REDACTED]"
        else:
            assert output[field] == "[REDACTED]"
    assert output["metadata"] == data["metadata"]
    assert output["num_tokens"] == 42 and output["tokenizer"] == "example/model"
    assert calls == ["GET"]
