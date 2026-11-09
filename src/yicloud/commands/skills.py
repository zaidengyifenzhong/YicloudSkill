"""Install the agent skill bundled with this CLI."""

from pathlib import Path

import click

from ..agents import TARGET_NAMES, inventory
from ..cli_support import emit
from ..skill_install import install, registered_paths, remember_path, targets


@click.group()
def skill():
    """Install or uninstall this package's matching agent skill."""


def skill_command(uninstall):
    @click.command("uninstall" if uninstall else "install")
    @click.option(
        "--target",
        type=click.Choice(TARGET_NAMES),
        multiple=True,
        default=("auto",),
        show_default=True,
    )
    @click.option(
        "--path",
        type=click.Path(path_type=Path),
        help="Exact skill directory; use with one target.",
    )
    @click.pass_context
    def command(ctx, target, path):
        if path is not None:
            registered_paths()  # Fail before changing files if the registry needs repair.
        if path is not None and len(target) != 1:
            raise click.UsageError("--path requires exactly one --target")
        destinations = list(dict.fromkeys(p for name in target for p in targets(name, path)))
        paths = install("all", uninstall=uninstall, destinations=destinations)
        if path is not None:
            remember_path(path, uninstall)
        emit(
            ctx,
            {
                "paths": paths,
                "action": "uninstall" if uninstall else "install",
                "message": "Skill paths processed"
                if paths
                else "No supported agents detected; use skill agents or --target custom --path PATH",
            },
        )

    return command


skill.add_command(skill_command(False))
skill.add_command(skill_command(True))


@skill.command("status")
@click.option("--target", type=click.Choice(TARGET_NAMES), default="auto")
@click.option(
    "--path", type=click.Path(path_type=Path), help="Exact skill directory for one target."
)
@click.pass_context
def skill_status(ctx, target, path):
    from importlib.metadata import version
    import shutil
    import sys

    from ..skill_install import status

    emit(
        ctx,
        dict(
            status(target, path),
            version=version("yicloud-skill"),
            remote_checked=False,
            latest_version=None,
            python=sys.executable,
            cli_entrypoint=sys.argv[0],
            command_on_path=shutil.which("yicloud"),
        ),
    )


@skill.command("agents")
@click.pass_context
def skill_agents(ctx):
    """List supported agents, detection results and destination paths without installing."""
    emit(ctx, {"agents": inventory()})
