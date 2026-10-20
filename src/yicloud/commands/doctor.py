"""Read-only diagnostics with explicit local, API and remote boundaries."""

import click

from .. import diagnostics
from ..cli_support import account_for, emit, scope_for
from ..client import YicloudClient
from ..errors import YicloudError
from .connection_options import discovery_options, resolve_connection


def report(ctx, rows):
    emit(ctx, {"checks": rows})
    if any(row["status"] == "fail" for row in rows):
        ctx.exit(1)


@click.group()
def doctor():
    """Inspect local installation or API access; never repair automatically."""


@doctor.command("local")
@click.pass_context
def local(ctx):
    report(ctx, diagnostics.local_checks())


@doctor.command("api")
@click.option("--project")
@click.option("--zone")
@click.pass_context
def api(ctx, project, zone):
    project, zone = scope_for(ctx, project, zone)
    a = account_for(ctx)
    with YicloudClient(a, timeout=8) as client:
        report(ctx, diagnostics.api_checks(client, project, zone))


def remote_doctor(kind):
    @click.argument("resource")
    @discovery_options(kind)
    @click.option("--project")
    @click.option("--zone")
    @click.option(
        "--timeout", type=click.IntRange(1, 60), default=8, help="Timeout per SSH probe in seconds."
    )
    @click.pass_context
    def command(ctx, resource, project, zone, timeout, **options):
        project, zone = scope_for(ctx, project, zone, required=True)
        try:
            connection = resolve_connection(ctx, kind, resource, project, zone, **options)
        except YicloudError as e:
            report(ctx, [diagnostics.check("ssh.connection", "fail", str(e))])
            return
        report(ctx, diagnostics.remote_checks(connection, timeout))

    return click.command(
        "doctor", help="Read-only SSH, disk and GPU probes using a saved or resolved connection."
    )(command)
