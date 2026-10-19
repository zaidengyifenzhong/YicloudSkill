"""Public CLI entry point and command composition root."""

import click

from .cli_support import Root
from .commands.accounts import account
from .commands.api import api
from .commands.discovery import register_discovery
from .commands.skills import skill
from .commands.workloads import register_workloads


@click.group(cls=Root)
@click.option("--account", "alias", help="Account alias; affects only this invocation.")
@click.option("--host", help="HTTPS API origin.")
@click.option("--region", help="Region ID.")
@click.option("--json", "json_output", is_flag=True, help="Fixed JSON envelope.")
@click.option("--show-secrets", is_flag=True, help="Explicitly reveal newly returned API secrets.")
@click.version_option(package_name="yicloud-skill")
@click.pass_context
def main(ctx, alias, host, region, json_output, show_secrets):
    """Yicloud CLI. API fields are case sensitive; see the skill for validation scope."""
    ctx.obj = dict(
        alias=alias, host=host, region=region, json=json_output, show=show_secrets, secrets=[]
    )
    ctx.command.active_context = ctx


main.add_command(api)
main.add_command(account)
main.add_command(skill)
register_discovery(main)
register_workloads(main)
