"""Install the agent skill bundled with this CLI."""

from pathlib import Path

import click

from ..cli_support import emit
from ..skill_install import install


@click.group()
def skill():
    """Install or uninstall this package's matching agent skill."""


def skill_command(uninstall):
    @click.command("uninstall" if uninstall else "install")
    @click.option(
        "--target", type=click.Choice(["codex", "claude", "all"]), default="all", show_default=True
    )
    @click.option(
        "--path",
        type=click.Path(path_type=Path),
        help="Exact skill directory; use with one target.",
    )
    @click.pass_context
    def command(ctx, target, path):
        emit(
            ctx,
            {
                "paths": install(target, path, uninstall),
                "action": "uninstall" if uninstall else "install",
            },
        )

    return command


skill.add_command(skill_command(False))
skill.add_command(skill_command(True))
