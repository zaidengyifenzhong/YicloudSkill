"""Public CLI entry point and command composition root."""

import click

from .cli_support import Root
from .commands.accounts import account
from .commands.contexts import context
from .commands.doctor import doctor
from .errors import InputError
from .commands.api import api
from .commands.discovery import register_discovery
from .commands.skills import skill
from .commands.workloads import register_workloads
from .commands.catalog_commands import register_catalog_commands


@click.group(cls=Root)
@click.option("--context", "context_name", help="Use a named local platform context.")
@click.option("--no-context", is_flag=True, help="Ignore the selected context for this invocation.")
@click.option("--account", "alias", help="Account alias; affects only this invocation.")
@click.option("--host", help="HTTPS API origin.")
@click.option("--region", help="Region ID.")
@click.option("--json", "json_output", is_flag=True, help="Fixed JSON envelope.")
@click.option("--show-secrets", is_flag=True, help="Explicitly reveal newly returned API secrets.")
@click.version_option(package_name="yicloud-skill")
@click.pass_context
def main(ctx, alias, host, region, json_output, show_secrets, context_name, no_context):
    """Yicloud CLI. API fields are case sensitive; see the skill for validation scope."""
    ctx.obj = dict(
        alias=alias,
        host=host,
        region=region,
        json=json_output,
        show=show_secrets,
        secrets=[],
        context_name=context_name,
        no_context=no_context,
    )
    ctx.command.active_context = ctx
    if context_name and no_context:
        raise InputError("--context and --no-context are mutually exclusive")


main.add_command(api)
main.add_command(account)
main.add_command(context)
main.add_command(doctor)
main.add_command(skill)
register_discovery(main)
register_workloads(main)
register_catalog_commands(main)
