"""Shared workspace connection options for SSH, transfer and diagnostics."""

import click

from ..cli_support import account_for, assignments
from ..connection_resolver import connection_for


def discovery_options(kind):
    def decorate(command):
        if kind != "workspace":
            return command
        for option in (
            click.option(
                "--forward-agent/--no-forward-agent",
                default=None,
                help="Override Agent forwarding; discovered connections enable it by default.",
            ),
            click.option(
                "--by-name",
                is_flag=True,
                help="Resolve a platform name, bypassing local registration.",
            ),
            click.option(
                "--lookup-set",
                "lookup_settings",
                multiple=True,
                help='Name lookup filter FIELD=JSON, e.g. Creator="USER".',
            ),
            click.option("--identity", help="Private key path for this invocation."),
            click.option("--ssh-host", help="Explicit gateway for automatic discovery."),
            click.option(
                "--ssh-port", type=click.IntRange(1, 65535), help="Gateway port (default: 2202)."
            ),
            click.option("--shared", is_flag=True, help="Use the shared-workspace gateway route."),
            click.option(
                "--ssh-user", help="Actual platform login username; required with --shared."
            ),
        ):
            command = option(command)
        return command

    return decorate


def resolve_connection(ctx, kind, resource, project, zone, lookup_settings=(), **options):
    return connection_for(
        account_for(ctx),
        kind,
        resource,
        project,
        zone,
        lookup=assignments(lookup_settings),
        **options,
    )
