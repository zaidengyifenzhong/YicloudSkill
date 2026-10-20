"""Manage local platform scope without storing credentials in contexts."""

import os

import click

from .. import context as contexts_api
from ..cli_support import account_for, context_for, emit
from ..config import read_state


@click.group()
def context():
    """Manage named account/project/zone contexts (local only)."""


@context.command("set")
@click.argument("name")
@click.option("--account", required=True)
@click.option("--project", required=True)
@click.option("--zone", required=True)
@click.pass_context
def set_context(ctx, name, account, project, zone):
    emit(ctx, {"name": name, "values": contexts_api.save_context(name, account, project, zone)})


@context.command("use")
@click.argument("name")
@click.pass_context
def use_context(ctx, name):
    contexts_api.use_context(name)
    emit(ctx, {"current": name})


@context.command("remove")
@click.argument("name")
@click.pass_context
def remove_context(ctx, name):
    contexts_api.remove_context(name)
    emit(ctx, {"removed": name})


@context.command("list")
@click.pass_context
def list_contexts(ctx):
    state = read_state()
    emit(
        ctx,
        [
            dict(name=name, **values, current=name == state.get("current_context"))
            for name, values in sorted(contexts_api.contexts(state).items())
        ],
    )


@context.command("show")
@click.pass_context
def show_context(ctx):
    chosen = context_for(ctx)
    account = account_for(ctx, inspect_conflicts=True)
    values = chosen["values"]
    sources = {k: "context" for k in values}
    sources["account"] = (
        "argument"
        if ctx.obj.get("alias") is not None
        else "context"
        if "account" in values
        else "current_account"
        if read_state().get("current")
        else "environment/default"
    )
    for key, env_name in (("host", "YICLOUD_API_HOST"), ("region", "YICLOUD_REGION_ID")):
        sources[key] = (
            "argument"
            if ctx.obj.get(key) is not None
            else ("environment" if os.getenv(env_name) else "account/default")
        )
    auth_env = (
        "YICLOUD_AUTHN_TOKEN",
        "YICLOUD_PUBLIC_KEY",
        "YICLOUD_SECRET_KEY",
        "YICLOUD_IS_SERVICE_ACCOUNT",
    )
    emit(
        ctx,
        {
            "name": chosen["name"],
            "values": dict(values, account=account.alias, host=account.host, region=account.region),
            "sources": sources,
            "auth_source": "environment" if any(k in os.environ for k in auth_env) else "account",
            "account_conflict": ctx.obj.get("account_conflict"),
        },
    )
