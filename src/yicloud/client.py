"""Public synchronous client, composing catalog protocol and HTTP delivery."""

import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl

import httpx

from .config import Account
from .errors import InputError
from .output import redact, secret_values
from .protocol import decode_response, prepare_request
from .protocol import encode_query as encode_query  # Retain the existing import path.
from .protocol import scalar as scalar
from .transport import HttpTransport


@dataclass
class Result:
    data: object
    request_id: str | None
    raw: httpx.Response


class YicloudClient:
    def __init__(self, account=None, *, transport=None, timeout=30, sleep=time.sleep):
        self.account = account or Account.resolve()
        self._transport = HttpTransport(transport=transport, timeout=timeout, sleep=sleep)

    @classmethod
    def from_account(cls, alias=None, **kwargs):
        return cls(Account.resolve(alias), **kwargs)

    def close(self):
        self._transport.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def prepare(self, service, action, params=None, *, allow_unknown_fields=False):
        return prepare_request(service, action, params, allow_unknown_fields=allow_unknown_fields)

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
        response = self._transport.send(self.account, op, query, body)
        secrets = [
            self.account.public_key,
            self.account.secret_key,
            self.account.token,
            response.request.headers.get("X-OGW-SIGN", ""),
            response.request.headers.get("Authorization", ""),
            *secret_values(params),
        ]
        data = decode_response(op, response, output=output, secrets=secrets)
        return Result(data, redact(response.headers.get("X-OGW-Request-Id"), secrets), response)
