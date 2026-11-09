"""Update the current installation and its existing agent skills."""

import click

from ..cli_support import emit
from ..update import apply_update, inspect_update


@click.command()
@click.option(
    "--check", is_flag=True, help="Check GitHub main and local state without changing files."
)
@click.pass_context
def update(ctx, check):
    """Update from GitHub main and synchronize existing Skills."""
    report = inspect_update()
    emit(ctx, report if check else apply_update(report, ctx.obj["json"]))
