"""Native OpenSSH command adapters for workspace and job connections."""

from dataclasses import asdict

import click

from .. import ssh
from ..cli_support import account_for, emit, scope_for
from ..errors import InputError
from .doctor import remote_doctor


def connection_commands(group, kind):
    group.add_command(remote_doctor(kind))
    connection = click.Group(
        "connection", help="Store explicit platform SSH connection information."
    )

    @connection.command("set")
    @click.argument("resource")
    @click.option("--project")
    @click.option("--zone")
    @click.option(
        "--ssh-command",
        required=True,
        help="Parsed, never executed. Supports -p -i -l -J, -CAXY and Host aliases.",
    )
    @click.option("--identity")
    @click.option("--proxy-jump")
    @click.pass_context
    def set_connection(ctx, resource, project, zone, ssh_command, identity, proxy_jump):
        project, zone = scope_for(ctx, project, zone, required=True)
        a = account_for(ctx)
        c = ssh.Connection.parse(ssh_command, identity, proxy_jump)
        ssh.save(a.alias, kind, project, zone, resource, c)
        emit(ctx, {"resource": resource, "connection": asdict(c)})

    @connection.command("list")
    @click.option("--project")
    @click.option("--zone")
    @click.pass_context
    def list_connections(ctx, project, zone):
        project, zone = scope_for(ctx, project, zone)
        a = account_for(ctx)
        emit(ctx, ssh.connections(a.alias, kind, project, zone))

    def local_connection(verb):
        @click.argument("resource")
        @click.option("--project")
        @click.option("--zone")
        @click.pass_context
        def command(ctx, resource, project, zone):
            project, zone = scope_for(ctx, project, zone, required=True)
            a = account_for(ctx)
            if verb == "show":
                emit(
                    ctx,
                    {
                        "resource": resource,
                        "connection": asdict(ssh.load(a.alias, kind, project, zone, resource)),
                    },
                )
            else:
                ssh.remove(a.alias, kind, project, zone, resource)
                emit(ctx, {"removed": resource, "local_only": True})

        return click.command(verb)(command)

    connection.add_command(local_connection("show"))
    connection.add_command(local_connection("remove"))
    group.add_command(connection)

    def connected(verb):
        @click.option("--project")
        @click.option("--zone")
        @click.pass_context
        def command(ctx, resource, project, zone, command=()):
            if verb != "ssh-config" and ctx.obj["json"]:
                raise InputError("SSH commands cannot use --json; use native process streams")
            if verb == "exec" and not command:
                raise InputError("exec requires -- COMMAND [ARGS...]")
            project, zone = scope_for(ctx, project, zone, required=True)
            a = account_for(ctx)
            c = ssh.load(a.alias, kind, project, zone, resource)
            if verb == "ssh-config":
                if ctx.obj["json"]:
                    emit(ctx, {"config": c.config(resource)})
                else:
                    click.echo(c.config(resource), nl=False)
            else:
                ctx.exit(ssh.run(c, command))

        if verb == "exec":
            command = click.argument("command", nargs=-1, type=click.UNPROCESSED)(command)
        command = click.argument("resource")(command)
        return click.command(verb, context_settings={"ignore_unknown_options": verb == "exec"})(
            command
        )

    for verb in ("ssh", "exec", "ssh-config"):
        group.add_command(connected(verb))

    @group.command("scp")
    @click.option("--recursive", "-r", is_flag=True, help="Copy directories recursively.")
    @click.argument("source")
    @click.argument("destination")
    @click.option("--project")
    @click.option("--zone")
    @click.pass_context
    def scp(ctx, source, destination, project, zone, recursive):
        if ctx.obj["json"]:
            raise InputError("scp cannot use --json")

        # Windows drive letters are local paths, never resource aliases.
        def remote(v):
            return ":" in v and not (len(v) >= 3 and v[1] == ":" and v[2] in "\\/")

        endpoints = [v for v in (source, destination) if remote(v)]
        if len(endpoints) != 1:
            raise InputError("Exactly one endpoint must be RESOURCE:/remote/path")
        resource = endpoints[0].split(":", 1)[0]
        project, zone = scope_for(ctx, project, zone, required=True)
        a = account_for(ctx)
        c = ssh.load(a.alias, kind, project, zone, resource)
        paths = [ssh.scp_endpoint(v, resource, c) for v in (source, destination)]
        ctx.exit(ssh.run(c, scp_paths=paths, recursive=recursive))
