"""Named user contexts. No directory discovery and no request-file mutation."""

import re

from .config import read_state, write_state
from .errors import ConfigurationError, InputError

FIELDS = {"account", "project", "zone"}


def contexts(state):
    values = state.get("contexts", {})
    if not isinstance(values, dict):
        raise ConfigurationError("Invalid contexts in account configuration")
    for name, value in values.items():
        if (
            not isinstance(name, str)
            or not isinstance(value, dict)
            or value.keys() - FIELDS
            or any(not isinstance(v, str) or not v.strip() for v in value.values())
        ):
            raise ConfigurationError("Invalid named context")
    return values


def selected(name=None, disabled=False):
    if disabled:
        return {"name": None, "values": {}}
    state = read_state()
    name = name if name is not None else state.get("current_context")
    if name is None:
        return {"name": None, "values": {}}
    if not isinstance(name, str) or name not in contexts(state):
        raise ConfigurationError(f"Unknown context: {name}; use context list or --no-context")
    return {"name": name, "values": dict(contexts(state)[name])}


def save_context(name, account, project, zone):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or name.startswith("-"):
        raise InputError("Context name must contain letters, digits, _, . or -")
    if any(not isinstance(v, str) or not v.strip() for v in (account, project, zone)):
        raise InputError("Context requires non-empty account, project and zone")
    state = read_state()
    if account not in state["accounts"]:
        raise ConfigurationError(f"Unknown account: {account}")
    values = contexts(state)
    values[name] = dict(account=account, project=project, zone=zone)
    state["contexts"] = values
    write_state(state)
    return values[name]


def use_context(name):
    state = read_state()
    if name not in contexts(state):
        raise ConfigurationError(f"Unknown context: {name}")
    state["current_context"] = name
    write_state(state)


def remove_context(name):
    state = read_state()
    values = contexts(state)
    if name not in values:
        raise ConfigurationError(f"Unknown context: {name}")
    del values[name]
    state["contexts"] = values
    if state.get("current_context") == name:
        state.pop("current_context")
    write_state(state)


def effective_scope(project, zone, values, *, required=False):
    result = {}
    sources = {}
    for key, explicit in (("project", project), ("zone", zone)):
        result[key] = explicit if explicit is not None else values.get(key)
        sources[key] = "argument" if explicit is not None else "context" if key in values else None
        if required and not result[key]:
            raise InputError(f"Requires --{key} or a named context containing {key}")
    return result, sources
