import json
from functools import lru_cache
from importlib.resources import files

from .errors import InputError


@lru_cache(maxsize=1)
def catalog():
    return json.loads(files("yicloud").joinpath("data/catalog.json").read_text(encoding="utf-8"))


def operation(service, action):
    for op in catalog()["operations"]:
        if op["service"] == service and op["action"] == action:
            return op
    raise InputError(f"Unknown operation {service}/{action}; use api list")


def request_schema(op):
    return catalog()["definitions"][op["service"]][op["request"]]


def validate(op, value, allow_unknown=False):
    definitions = catalog()["definitions"][op["service"]]

    def walk(s, v, path):
        if "ref" in s:
            if v is None and s.get("nullable"):
                return
            return walk(definitions[s["ref"]], v, path)
        if v is None and (s.get("nullable") or not s):
            return
        typ = s.get("type")
        checks = {
            "object": lambda: isinstance(v, dict),
            "array": lambda: isinstance(v, list),
            "string": lambda: isinstance(v, str),
            "boolean": lambda: type(v) is bool,
            "integer": lambda: type(v) is int,
            "number": lambda: type(v) in (int, float),
        }
        if typ in checks and not checks[typ]():
            raise InputError(f"{path}: expected {typ}")
        if "enum" in s and str(v) not in s["enum"]:
            raise InputError(f"{path}: expected one of {s['enum']}")
        if typ == "object":
            for k in s.get("required", []):
                if k not in v or v[k] is None:
                    raise InputError(f"{path}.{k}: required")
            props = s.get("properties", {})
            for k, x in v.items():
                if k in props:
                    walk(props[k], x, f"{path}.{k}")
                elif "additional" in s:
                    walk(s["additional"], x, f"{path}.{k}")
                elif not allow_unknown:
                    raise InputError(f"{path}.{k}: unknown field (case sensitive)")
        elif typ == "array":
            for i, x in enumerate(v):
                walk(s["items"], x, f"{path}[{i}]")

    if not isinstance(value, dict):
        raise InputError("Request must be a JSON object")
    walk(request_schema(op), value, "request")
