"""Extract a request body from an existing successful JSON dry-run preview."""

import argparse
import json
import math
import os
from pathlib import Path
import sys


def reject_constant(_value):
    raise ValueError("Non-finite JSON number")


def finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Non-finite JSON number")
    return number


def has_redaction(value):
    if isinstance(value, str):
        return "[REDACTED]" in value
    if isinstance(value, dict):
        return any(has_redaction(key) or has_redaction(item) for key, item in value.items())
    if isinstance(value, list):
        return any(has_redaction(item) for item in value)
    return False


def request_bytes(text):
    preview = json.loads(text, parse_constant=reject_constant, parse_float=finite_float)
    if not isinstance(preview, dict) or preview.get("ok") is not True:
        raise ValueError("Successful dry-run preview required")
    data = preview.get("data")
    if not isinstance(data, dict) or not (
        data.get("method") == "POST"
        and data.get("validation") == "passed"
        and data.get("validation_scope") == "local_pinned_sdk_request"
        and data.get("query") == []
        and isinstance(data.get("body"), dict)
    ):
        raise ValueError("Validated POST preview with an object body and empty query required")
    if has_redaction(data["body"]):
        raise ValueError("Redacted request body cannot be exported")
    return (json.dumps(data["body"], ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode(
        "utf-8"
    )


def write_new(path, payload):
    descriptor = os.open(
        path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600
    )
    created = os.fstat(descriptor)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = None
            stream.write(payload)
    except BaseException:
        # Remove only the file created by this invocation, even if its path changed.
        try:
            current = path.lstat()
            if (current.st_dev, current.st_ino) == (created.st_dev, created.st_ino):
                path.unlink()
        except OSError:
            pass
        raise
    finally:
        if descriptor is not None:
            os.close(descriptor)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="UTF-8 preview file; default: stdin")
    parser.add_argument("--output", type=Path, required=True, help="New request JSON file")
    args = parser.parse_args()
    try:
        text = (
            args.input.read_text(encoding="utf-8")
            if args.input
            else sys.stdin.buffer.read().decode("utf-8")
        )
        write_new(args.output, request_bytes(text))
    except (OSError, ValueError, RecursionError):
        print(
            "Cannot export preview: invalid input or unavailable new output file", file=sys.stderr
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
