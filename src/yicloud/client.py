import json
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode, parse_qsl

import httpx

from . import auth
from .catalog import operation, request_schema, validate
from .config import Account
from .errors import AuthenticationError, InputError, NetworkError, UnsupportedProtocol, YicloudError


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


@dataclass
class Result:
    data: object
    request_id: str | None
    raw: httpx.Response


class YicloudClient:
    def __init__(self, account=None, *, transport=None, timeout=30, sleep=time.sleep):
        self.account = account or Account.resolve()
        self._http = httpx.Client(transport=transport, timeout=timeout, follow_redirects=False)
        self._sleep = sleep

    @classmethod
    def from_account(cls, alias=None, **kwargs):
        return cls(Account.resolve(alias), **kwargs)

    def close(self):
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def prepare(self, service, action, params=None, *, allow_unknown_fields=False):
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
            else json.dumps(
                params, ensure_ascii=False, separators=(",", ":"), allow_nan=False
            ).encode()
        )
        return op, query, body

    def dry_run(self, service, action, params=None, **kwargs):
        op, query, body = self.prepare(service, action, params, **kwargs)
        return {
            "method": op["method"],
            "url": self.account.host + op["path"],
            "query": [{"name": k, "value": v} for k, v in parse_qsl(query, keep_blank_values=True)],
            "body": json.loads(body) if body else None,
            "validation": "passed",
            "read_only": op["read_only"],
            "status": op["status"],
        }

    def call(self, service, action, params=None, *, allow_unknown_fields=False, output=None):
        op, query, body = self.prepare(
            service, action, params, allow_unknown_fields=allow_unknown_fields
        )
        if op["response_mode"] == "file" and output is None:
            raise InputError("File response requires output=PATH / --output PATH")
        attempts = 3 if op["read_only"] else 1
        for attempt in range(attempts):
            headers = auth.headers(self.account, int(time.time() * 1000), query, body)
            try:
                response = self._http.request(
                    op["method"],
                    self.account.host + op["path"] + ("?" + query if query else ""),
                    content=body,
                    headers=headers,
                )
            except httpx.TransportError as e:
                if attempt + 1 < attempts:
                    self._sleep(0.25 * 2**attempt)
                    continue
                raise NetworkError(
                    "Request transport failed"
                    + (
                        "; write outcome unknown; inspect remote state before retry"
                        if not op["read_only"]
                        else ""
                    ),
                    outcome_unknown=not op["read_only"],
                ) from e
            if response.status_code in (429, 502, 503, 504) and attempt + 1 < attempts:
                self._sleep(0.25 * 2**attempt)
                continue
            break
        request_id = response.headers.get("X-OGW-Request-Id")
        if not 200 <= response.status_code < 300:
            error = AuthenticationError if response.status_code in (401, 403) else YicloudError
            raise error(
                f"HTTP {response.status_code}",
                request_id=request_id,
                code=response.status_code,
                outcome_unknown=not op["read_only"] and response.status_code >= 500,
            )
        if op["response_mode"] == "file":
            if "json" in response.headers.get("content-type", ""):
                try:
                    error_payload = response.json()
                except ValueError as e:
                    raise YicloudError(
                        "Invalid JSON download response", request_id=request_id
                    ) from e
                if isinstance(error_payload, dict) and error_payload.get("Code", 0) != 0:
                    raise YicloudError(
                        str(error_payload.get("Msg", "Download failed")),
                        code=error_payload["Code"],
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
            return Result({"path": str(path), "bytes": len(response.content)}, request_id, response)
        if not response.content:
            if response.status_code == 204 or op["response_mode"] == "empty":
                return Result(None, request_id, response)
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
            raise YicloudError("Expected response object", request_id=request_id)
        if op["response_mode"] == "envelope" and "Code" not in payload:
            raise YicloudError(
                "Response is missing platform Code",
                request_id=request_id,
                outcome_unknown=not op["read_only"],
            )
        code = payload.get("Code", 0)
        if code != 0:
            raise YicloudError(
                str(payload.get("Msg", "Platform error")), code=code, request_id=request_id
            )
        data = (
            payload.get("Data", payload) if op["response_mode"] == "direct" else payload.get("Data")
        )
        return Result(data, request_id, response)
