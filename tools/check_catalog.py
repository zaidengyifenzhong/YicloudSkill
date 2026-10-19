"""Check catalog identity, all references and operation uniqueness. Purely offline."""

import json
import sys
from pathlib import Path

path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("src/yicloud/data/catalog.json")
c = json.loads(path.read_text(encoding="utf-8"))
assert c["sdk_commit"] == "8f8d27e2b466b7ceac5dacfa12900d03ad70e3d5"
assert c["sdk_version"] == "v0.5.1"
assert len(c["operations"]) == 227
assert len({(o["service"], o["action"]) for o in c["operations"]}) == 227


def walk(value, definitions):
    if isinstance(value, dict):
        if "ref" in value:
            assert value["ref"] in definitions, value
        for child in value.values():
            walk(child, definitions)
    elif isinstance(value, list):
        for child in value:
            walk(child, definitions)


for definitions in c["definitions"].values():
    walk(definitions, definitions)
for op in c["operations"]:
    assert op["request"] in c["definitions"][op["service"]]
    assert op["path"].startswith("/" + op["product"] + "/" + op["version"] + "/")
    assert op["status"] in ("implemented-offline", "deferred-protocol")
print("Catalog valid: 227 operations, all types resolved")
