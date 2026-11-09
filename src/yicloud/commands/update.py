"""Update the current installation and its existing agent skills."""

import click

from ..cli_support import emit
from ..update import apply_update, inspect_update


@click.command()
@click.option(
    "--check", is_flag=True, help="Check stable release and local state without changing files."
)
@click.pass_context
def update(ctx, check):
    """Check/install the latest stable CLI and synchronize existing Skills."""
    report = inspect_update()
    emit(ctx, report if check else apply_update(report, ctx.obj["json"]))
