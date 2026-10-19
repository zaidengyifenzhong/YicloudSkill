"""Authenticated HTTP delivery and bounded retries, independent of response formats."""

import time

import httpx

from . import auth
from .errors import NetworkError


class HttpTransport:
    def __init__(self, *, transport=None, timeout=30, sleep=time.sleep):
        self._http = httpx.Client(transport=transport, timeout=timeout, follow_redirects=False)
        self._sleep = sleep

    def close(self):
        self._http.close()

    def send(self, account, op, query, body):
        attempts = 3 if op["read_only"] else 1
        for attempt in range(attempts):
            headers = auth.headers(account, int(time.time() * 1000), query, body)
            try:
                response = self._http.request(
                    op["method"],
                    account.host + op["path"] + ("?" + query if query else ""),
                    content=body,
                    headers=headers,
                )
            except httpx.TransportError:
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
                ) from None
            if response.status_code in (429, 502, 503, 504) and attempt + 1 < attempts:
                self._sleep(0.25 * 2**attempt)
                continue
            break
        return response
