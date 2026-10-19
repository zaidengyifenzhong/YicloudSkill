"""Local account management and authentication checks."""

from dataclasses import asdict

import click

from ..cli_support import account_for, client_for, emit, emit_result
from ..config import Account, read_state, write_state
from ..errors import ConfigurationError


@click.group()
def account():
    """Local accounts. Credentials are entered without echo, never as command arguments."""


@account.command("add")
@click.argument("alias")
@click.option(
    "--auth", type=click.Choice(["token", "hmac", "service"]), default="hmac", show_default=True
)
@click.option("--host", default="https://gate.yicloud.com", show_default=True)
@click.option("--region", default="cn-shanghai", show_default=True)
@click.pass_context
def account_add(ctx, alias, auth, host, region):
    state = read_state()
    if alias in state["accounts"]:
        raise ConfigurationError("Account already exists; remove it explicitly before replacing")
    a = Account(alias=alias, host=host, region=region)
    if auth == "token":
        a.token = click.prompt("Authorization token (include scheme if required)", hide_input=True)
    else:
        a.public_key = click.prompt("Public key", hide_input=True)
        a.secret_key = click.prompt("Secret key", hide_input=True)
        a.service_account = auth == "service"
    values = asdict(a)
    values.pop("alias")
    state["accounts"][alias] = values
    state.setdefault("current", alias)
    write_state(state)
    emit(ctx, {"account": alias, "saved": True})


@account.command("list")
@click.pass_context
def account_list(ctx):
    state = read_state()
    emit(
        ctx,
        [
            {
                "alias": name,
                "host": v.get("host"),
                "region": v.get("region"),
                "current": name == state.get("current"),
                "auth": "token"
                if v.get("token")
                else "service"
                if v.get("service_account")
                else "hmac",
            }
            for name, v in state["accounts"].items()
        ],
    )


@account.command("current")
@click.pass_context
def account_current(ctx):
    a = account_for(ctx)
    emit(ctx, {"alias": a.alias, "host": a.host, "region": a.region})


@account.command("use")
@click.argument("alias")
@click.pass_context
def account_use(ctx, alias):
    state = read_state()
    if alias not in state["accounts"]:
        raise ConfigurationError(f"Unknown account: {alias}")
    state["current"] = alias
    write_state(state)
    emit(ctx, {"current": alias})


@account.command("remove")
@click.argument("alias")
@click.pass_context
def account_remove(ctx, alias):
    state = read_state()
    if alias not in state["accounts"]:
        raise ConfigurationError(f"Unknown account: {alias}")
    del state["accounts"][alias]
    if state.get("current") == alias:
        state.pop("current")
    write_state(state)
    emit(ctx, {"removed": alias, "connections_preserved": True})


@account.command("check")
@click.pass_context
def account_check(ctx):
    with client_for(ctx) as client:
        emit_result(ctx, client.call("mc", "ListZones"), "mc", "ListZones")
