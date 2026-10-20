"""Shared CLI input, output, account resolution and error boundary."""

import json
import sys

import click

from .client import YicloudClient
from .config import Account
from .context import effective_scope, selected
from .errors import ConfigurationError, InputError, OperationInterrupted, YicloudError
from .output import redact, secret_values


class Root(click.Group):
    def main(self, *args, **kwargs):
        standalone = kwargs.pop("standalone_mode", True)
        self.active_context = None
        argv = args[0] if args else kwargs.get("args")
        argv = list(sys.argv[1:] if argv is None else argv)
        json_requested = False
        skip_value = False
        for arg in argv:
            if skip_value:
                skip_value = False
                continue
            if arg == "--" or not arg.startswith("-"):
                break
            if arg == "--json":
                json_requested = True
            if arg in ("--account", "--host", "--region", "--context"):
                skip_value = True
        # JSON and Chinese API descriptions use UTF-8 even when Windows redirects stdout.
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                try:
                    stream.reconfigure(encoding="utf-8")
                except (OSError, ValueError):
                    pass
        try:
            code = super().main(*args, standalone_mode=False, **kwargs)
        except (YicloudError, OSError, ValueError, click.ClickException) as e:
            ctx = self.active_context
            opts = ctx.obj if ctx else {}
            if isinstance(e, YicloudError):
                err = e
            elif isinstance(e, click.ClickException):
                err = InputError(e.format_message())
            else:
                err = ConfigurationError("Local configuration, JSON input or file operation failed")
            secrets = (opts or {}).get("secrets", ())
            if (opts or {}).get("json", json_requested):
                payload = {"ok": False, "error": err.as_dict()}
                click.echo(json.dumps(redact(payload, secrets), ensure_ascii=False), err=True)
            else:
                if isinstance(e, click.UsageError) and e.ctx is not None:
                    click.echo(e.ctx.get_usage(), err=True)
                    click.echo(f"Try '{e.ctx.command_path} --help' for help.\n", err=True)
                click.echo("Error: " + redact(str(err), secrets), err=True)
                if err.request_id:
                    click.echo("Request ID: " + redact(str(err.request_id), secrets), err=True)
                if err.outcome_unknown:
                    click.echo("Remote outcome unknown; inspect state before retrying.", err=True)
                for hint in err.hints:
                    click.echo("Hint: " + redact(hint, secrets), err=True)
            if standalone:
                raise SystemExit(1) from e
            raise err from e
        except (KeyboardInterrupt, click.Abort):
            message = (
                "Local operation interrupted; remote writes may have completed. "
                "Inspect remote state before retrying. Interrupting a local wait "
                "does not stop the workload."
            )
            ctx = self.active_context
            if ctx and ctx.obj and ctx.obj["json"]:
                error = OperationInterrupted(message, outcome_unknown=True)
                click.echo(json.dumps({"ok": False, "error": error.as_dict()}), err=True)
            else:
                click.echo(message, err=True)
            if standalone:
                raise SystemExit(130) from None
            raise
        else:
            if standalone:
                raise SystemExit(code if isinstance(code, int) else 0)
            return code


def context_for(ctx):
    if "resolved_context" not in ctx.obj:
        ctx.obj["resolved_context"] = selected(
            ctx.obj.get("context_name"), ctx.obj.get("no_context", False)
        )
    return ctx.obj["resolved_context"]


def scope_for(ctx, project, zone, *, required=False, allowed=("project", "zone")):
    values = {k: v for k, v in context_for(ctx)["values"].items() if k in allowed}
    scope, sources = effective_scope(project, zone, values, required=required)
    ctx.obj.setdefault("effective_context", {}).update(
        {k: {"value": v, "source": sources[k]} for k, v in scope.items() if v is not None}
    )
    return scope["project"], scope["zone"]


def account_for(ctx):
    chosen = context_for(ctx)
    alias = ctx.obj["alias"] if ctx.obj["alias"] is not None else chosen["values"].get("account")
    a = Account.resolve(alias, ctx.obj["host"], ctx.obj["region"])
    ctx.obj.setdefault("effective_context", {}).update(
        account=a.alias, host=a.host, region=a.region, name=chosen["name"]
    )
    ctx.obj["secrets"].extend([a.token, a.public_key, a.secret_key])
    return a


def client_for(ctx):
    return YicloudClient(account_for(ctx))


def emit(ctx, data, service=None, action=None, request_id=None, schema=False):
    data = redact(data, ctx.obj.get("secrets", ()), show=ctx.obj["show"] or schema)
    if ctx.obj["json"]:
        data = {
            "ok": True,
            "data": data,
            "meta": {"service": service, "action": action, "request_id": request_id},
        }
    if ctx.obj["json"] and ctx.obj.get("effective_context"):
        data["meta"]["context"] = redact(ctx.obj["effective_context"], ctx.obj.get("secrets", ()))
    click.echo(json.dumps(data, ensure_ascii=False, indent=2))


def emit_result(ctx, result, service, action):
    emit(ctx, result.data, service, action, result.request_id)


def read_json(file):
    if file is None:
        return {}
    try:
        with click.open_file(file, "r", encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, ValueError) as e:
        raise InputError("Cannot read request JSON; provide a valid UTF-8 object") from e
    if not isinstance(value, dict):
        raise InputError("Request must be a JSON object")
    ctx = click.get_current_context(silent=True)
    if ctx and ctx.obj is not None:
        ctx.obj["secrets"].extend(secret_values(value))
    return value


def assignments(values):
    result = {}
    for value in values:
        key, sep, text = value.partition("=")
        if not sep or not key or key in result:
            raise InputError("Use unique --set FIELD=JSON entries")
        try:
            result[key] = json.loads(text)
        except ValueError as e:
            raise InputError(
                "--set requires a JSON value, e.g. --set 'Limit=20' or --set 'SKUType=\"gpu\"'"
            ) from e
    ctx = click.get_current_context(silent=True)
    if ctx and ctx.obj is not None:
        ctx.obj["secrets"].extend(secret_values(result))
    return result
