"""Catalog request encoding and response parsing; no authentication or retries."""

import json
import os
import tempfile
from pathlib import Path
from urllib.parse import urlencode

from .catalog import operation, request_schema, validate
from .errors import AuthenticationError, UnsupportedProtocol, YicloudError
from .output import redact


def scalar(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return str(v)


def encode_query(params, schema):
    pairs = []
    for key in sorted(params):
        value = params[key]
        name = schema.get("properties", {}).get(key, {}).get("query_name", key)
        for item in value if isinstance(value, list) else [value]:
            pairs.append((name, scalar(item)))
    return urlencode(pairs)


def prepare_request(service, action, params=None, *, allow_unknown_fields=False):
    op = dict(operation(service, action))
    params = {} if params is None else params
    validate(op, params, allow_unknown_fields)
    if service == "ray" and action == "GetRayJobLogs" and params.get("Method") == "download":
        op["response_mode"] = "file"
    if op["response_mode"] == "deferred":
        raise UnsupportedProtocol(
            f"{service}/{action}: realtime protocol lacks a verified contract; use documented historical log queries"
        )
    query = encode_query(params, request_schema(op)) if op["method"] == "GET" else ""
    body = (
        b""
        if op["method"] == "GET"
        else json.dumps(params, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
    )
    return op, query, body


def _platform_code(payload, op, request_id):
    code = payload.get("Code", 0)
    if type(code) is not int:
        raise YicloudError(
            "Response has invalid platform Code",
            request_id=request_id,
            outcome_unknown=not op["read_only"],
        )
    return code


def decode_response(op, response, *, output=None, secrets=()):
    request_id = redact(response.headers.get("X-OGW-Request-Id"), secrets)
    if not 200 <= response.status_code < 300:
        error = AuthenticationError if response.status_code in (401, 403) else YicloudError
        code = response.status_code
        message = f"HTTP {response.status_code}"
        try:
            failure = response.json()
        except ValueError:
            failure = None
        if isinstance(failure, dict):
            if type(failure.get("Code")) is int:
                code = failure["Code"]
            if isinstance(failure.get("Msg"), str) and failure["Msg"]:
                message += ": " + redact(failure["Msg"], secrets)
        raise error(
            message,
            request_id=request_id,
            code=code,
            outcome_unknown=not op["read_only"] and response.status_code >= 500,
            http_status=response.status_code,
        )
    if op["response_mode"] == "file":
        if "json" in response.headers.get("content-type", "").lower():
            try:
                error_payload = response.json()
            except ValueError as e:
                raise YicloudError("Invalid JSON download response", request_id=request_id) from e
            code = (
                _platform_code(error_payload, op, request_id)
                if isinstance(error_payload, dict)
                else 0
            )
            if code != 0:
                raise YicloudError(
                    redact(str(error_payload.get("Msg", "Download failed")), secrets),
                    code=code,
                    request_id=request_id,
                )
        path = Path(output)
        fd, tmp = tempfile.mkstemp(prefix=".yicloud-download-", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(response.content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        return {"path": str(path), "bytes": len(response.content)}
    if not response.content:
        if response.status_code == 204 or op["response_mode"] == "empty":
            return None
        raise YicloudError(
            "Unexpected empty JSON response",
            request_id=request_id,
            outcome_unknown=not op["read_only"],
        )
    try:
        payload = response.json()
    except ValueError as e:
        raise YicloudError(
            "Invalid JSON response", request_id=request_id, outcome_unknown=not op["read_only"]
        ) from e
    if not isinstance(payload, dict):
        raise YicloudError(
            "Expected response object", request_id=request_id, outcome_unknown=not op["read_only"]
        )
    if op["response_mode"] == "envelope" and "Code" not in payload:
        raise YicloudError(
            "Response is missing platform Code",
            request_id=request_id,
            outcome_unknown=not op["read_only"],
        )
    code = _platform_code(payload, op, request_id)
    if code != 0:
        raise YicloudError(
            redact(str(payload.get("Msg", "Platform error")), secrets),
            code=code,
            request_id=request_id,
        )
    data = payload.get("Data", payload) if op["response_mode"] == "direct" else payload.get("Data")
    return data
