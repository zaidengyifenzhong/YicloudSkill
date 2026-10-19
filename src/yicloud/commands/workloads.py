"""Workload create, lifecycle, waiting and log command adapters."""

import click

from ..cli_support import assignments, client_for, emit, emit_result, read_json
from ..creation import create_params
from ..errors import InputError
from ..workflows import (
    WORKLOADS,
    follow_logs,
    resolve,
    validate_workload_extra,
    wait,
    workload_params,
)
from .connections import connection_commands
from .discovery import query_command


def create_command(kind):
    @click.command("create")
    @click.option("--file", help="Full request JSON; exclusive with shortcut flags.")
    @click.option("--name")
    @click.option("--project")
    @click.option("--zone")
    @click.option("--image")
    @click.option("--command", "entrypoint", help="Container shell command (training only).")
    @click.option("--sku")
    @click.option("--sku-scope", type=click.Choice(["public", "tenant", "project"]))
    @click.option("--quota-group")
    @click.option("--cpu")
    @click.option("--memory")
    @click.option("--gpu")
    @click.option("--dry-run", is_flag=True)
    @click.pass_context
    def command(
        ctx,
        file,
        name,
        project,
        zone,
        image,
        entrypoint,
        sku,
        sku_scope,
        quota_group,
        cpu,
        memory,
        gpu,
        dry_run,
    ):
        shortcuts = dict(
            name=name,
            project=project,
            zone=zone,
            image=image,
            entrypoint=entrypoint,
            sku=sku,
            sku_scope=sku_scope,
            quota_group=quota_group,
            cpu=cpu,
            memory=memory,
            gpu=gpu,
        )
        if file:
            if any(value is not None for value in shortcuts.values()):
                raise InputError("--file and shortcut flags are mutually exclusive")
            params = read_json(file)
        else:
            params = create_params(kind, **shortcuts)
        w = WORKLOADS[kind]
        with client_for(ctx) as client:
            if dry_run:
                emit(
                    ctx,
                    client.dry_run(w["service"], w["create"], params),
                    w["service"],
                    w["create"],
                )
            else:
                emit_result(
                    ctx, client.call(w["service"], w["create"], params), w["service"], w["create"]
                )

    return command


def workload_command(kind, verb):
    w = WORKLOADS[kind]
    action = w["status"] if verb == "wait" else w[verb]

    @click.command(verb)
    @click.argument("resource")
    @click.option("--project", required=True)
    @click.option(
        "--zone", required=True, help="Explicit lookup scope; sent only if API accepts it."
    )
    @click.option(
        "--by-name", is_flag=True, help="Resolve an exact display name within project and zone."
    )
    @click.option("--file", help="Additional official fields (workers/precheck/etc.).")
    @click.option(
        "--set",
        "settings",
        multiple=True,
        help="Additional FIELD=JSON; cannot override scope or ID.",
    )
    @click.option("--dry-run", is_flag=True)
    @click.option("--timeout", type=click.FloatRange(min=0), default=1800, show_default=True)
    @click.option(
        "--interval",
        type=click.FloatRange(min=0.1),
        default=None,
        help="Wait: 5 seconds; follow: 3 seconds.",
    )
    @click.option("--follow", is_flag=True, help="Poll historical logs; incompatible with --json.")
    @click.option("--start", type=int, help="Unix nanoseconds, inclusive.")
    @click.option("--end", type=int, help="Unix nanoseconds.")
    @click.option("--limit", type=click.IntRange(1, 10000), default=200)
    @click.option("--instance", help="Replica filter for logs.")
    @click.option("--replicas", type=click.IntRange(min=0), help="Desired serving replica count.")
    @click.pass_context
    def command(
        ctx,
        resource,
        project,
        zone,
        by_name,
        file,
        settings,
        dry_run,
        timeout,
        interval,
        follow,
        start,
        end,
        limit,
        instance,
        replicas,
    ):
        if follow and (verb != "logs" or ctx.obj["json"] or dry_run or end is not None):
            raise InputError("--follow requires logs without --json, --dry-run or --end")
        extra = read_json(file)
        extra.update(assignments(settings))
        validate_workload_extra(kind, extra)
        with client_for(ctx) as client:
            rid = resolve(client, kind, resource, project, zone, by_name)
            params = workload_params(
                kind,
                verb,
                rid,
                project,
                zone,
                extra=extra,
                replicas=replicas,
                start=start,
                end=end,
                limit=limit,
                instance=instance,
            )
            if dry_run:
                emit(ctx, client.dry_run(w["service"], action, params), w["service"], action)
            elif verb == "wait":
                emit_result(
                    ctx,
                    wait(client, kind, params, timeout=timeout, interval=interval or 5),
                    w["service"],
                    action,
                )
            elif follow:
                follow_logs(
                    client,
                    kind,
                    params,
                    lambda row: emit(ctx, row, w["service"], action),
                    interval=interval or 3,
                )
            else:
                emit_result(ctx, client.call(w["service"], action, params), w["service"], action)

    return command


def register_workloads(main):
    for kind, w in WORKLOADS.items():
        group = click.Group(kind, help=f"Manage {kind}; use --help on each operation.")
        group.add_command(query_command(w["service"], w["list"], "list"))
        group.add_command(create_command(kind))
        for verb in list(w):
            if verb not in ("service", "id", "list", "create"):
                group.add_command(workload_command(kind, verb))
        group.add_command(workload_command(kind, "wait"))
        if kind in ("workspace", "job"):
            connection_commands(group, kind)
        main.add_command(group)
