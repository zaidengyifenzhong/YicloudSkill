"""Every ordinary HTTP operation exercised with generated synthetic request/response data.

This verifies catalog/transport reachability and encoding, not server business validation.
"""

import json
from pathlib import Path

import httpx
import pytest

from yicloud.auth import sign
from yicloud.catalog import catalog
from yicloud.client import YicloudClient


@pytest.mark.parametrize(
    "op",
    [o for o in catalog()["operations"] if o["response_mode"] != "deferred"],
    ids=lambda o: o["service"] + "/" + o["action"],
)
def test_every_http_operation_contract(op, account, tmp_path):
    definitions = catalog()["definitions"][op["service"]]

    def sample(s):
        if "ref" in s:
            return sample(definitions[s["ref"]])
        if "enum" in s:
            return s["enum"][0]
        if s.get("type") == "object":
            return {k: sample(s["properties"][k]) for k in s.get("required", [])}
        return {"string": "fixture", "integer": 0, "number": 0, "boolean": False, "array": []}.get(
            s.get("type")
        )

    params = sample(definitions[op["request"]])
    seen = []

    def handler(request):
        seen.append(request)
        assert request.method == op["method"]
        assert request.url.path == op["path"]
        assert request.headers["X-OGW-REGION-ID"] == account.region
        assert request.headers["X-OGW-SIGN"] == sign(
            request.headers["X-OGW-TICK"],
            account.public_key,
            account.secret_key,
            request.url.query.decode(),
            request.content,
        )
        if op["method"] == "POST":
            assert json.loads(request.content) == params
        if op["response_mode"] == "file":
            return httpx.Response(200, content=b"synthetic file")
        return httpx.Response(200, json={"Code": 0, "Data": {"synthetic": True}})

    with YicloudClient(account, transport=httpx.MockTransport(handler)) as client:
        result = client.call(op["service"], op["action"], params, output=tmp_path / "file")
    assert result.data is not None
    assert len(seen) == 1


def test_signatures_against_unmodified_go_sdk_vectors():
    vectors = json.loads(Path(__file__).with_name("sign_vectors.json").read_text(encoding="utf-8"))
    for v in vectors:
        assert (
            sign(v["timestamp"], v["public"], v["secret"], v["query"], v["body"].encode())
            == v["signature"]
        )
