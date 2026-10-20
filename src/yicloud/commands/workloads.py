"""Workload commands with options specific to each operation."""

import time

import click
from click.core import ParameterSource

from ..catalog import operation, request_schema
from ..cli_support import assignments, client_for, emit, emit_result, read_json, scope_for
from ..creation import create_params
from ..errors import InputError
from ..time_input import duration_ns, timestamp_ns
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


def resource_options(command):
    command = click.option(
        "--lookup-set",
        "lookup_settings",
        multiple=True,
        help="List filter FIELD=JSON for --by-name only; not sent to the final operation.",
    )(command)
    command = click.option(
        "--dry-run", is_flag=True, help="Preview request; name lookup may read the API."
    )(command)
    command = click.option(
        "--by-name", is_flag=True, help="Resolve an exact name within project and zone."
    )(command)
    command = click.option("--zone", help="Lookup scope; sent only if the API accepts it.")(command)
    command = click.option("--project")(command)
    return click.argument("resource")(command)


def extra_options(kind, verb, command):
    w = WORKLOADS[kind]
    action = w["status"] if verb == "wait" else w[verb]
    fields = request_schema(operation(w["service"], action))["properties"]
    managed = {"Project", "ZoneId", w["id"], "Resources"}
    if verb == "logs":
        managed.update(
            {"Start", "End", "StartTime", "EndTime", "Method", "Limit", "Replicas", "Direction"}
        )
    if verb == "scale":
        managed.add("Replicas")
    if fields.keys() - managed:
        command = click.option(
            "--set",
            "settings",
            multiple=True,
            help="Additional FIELD=JSON; cannot override scope or ID.",
        )(command)
        command = click.option("--file", help="Additional request fields as JSON.")(command)
    return command


def create_command(kind):
    @click.pass_context
    def command(ctx, file, dry_run, **shortcuts):
        if file:
            if any(value is not None for value in shortcuts.values()):
                raise InputError("--file and shortcut flags are mutually exclusive")
            params = read_json(file)
        else:
            shortcuts["project"], shortcuts["zone"] = scope_for(
                ctx, shortcuts.get("project"), shortcuts.get("zone"), required=True
            )
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

    command = click.option("--dry-run", is_flag=True)(command)
    if kind in ("workspace", "job"):
        for name in reversed(
            ("name", "project", "zone", "image", "sku", "quota-group", "cpu", "memory", "gpu")
        ):
            help_text = (
                "GPU count; defaults to 0 for quota-mode job shortcuts."
                if name == "gpu" and kind == "job"
                else None
            )
            command = click.option(f"--{name}", help=help_text)(command)
        command = click.option("--sku-scope", type=click.Choice(["public", "tenant", "project"]))(
            command
        )
        if kind == "job":
            command = click.option(
                "--use-private-machine/--no-use-private-machine",
                default=None,
                help="Explicitly select private-machine scheduling; omitted by default.",
            )(command)
            command = click.option(
                "--qos", help="Platform QoS value, e.g. Guaranteed; omitted by default."
            )(command)
            command = click.option(
                "--priority",
                type=click.IntRange(1, 9),
                help="Scheduling priority; omitted by default so the platform chooses.",
            )(command)
            for duration_option, phase in (
                ("--max-wait-duration", "waiting"),
                ("--max-running-duration", "running"),
            ):
                command = click.option(
                    duration_option,
                    help=f"Task {phase} limit (30s, 15m, 2h, 1d); sent as seconds. Omitted by default.",
                )(command)
            command = click.option(
                "--login-shell",
                is_flag=True,
                default=None,
                help="Use sh -lc instead of sh -c for --command.",
            )(command)
            command = click.option("--command", "entrypoint", help="Container shell command.")(
                command
            )
    command = click.option(
        "--file",
        required=kind in ("ray", "serving"),
        help=(
            "Request JSON file, or - for stdin; exclusive with shortcut flags."
            if kind in ("workspace", "job")
            else "Request JSON file, or - for stdin."
        ),
    )(command)
    label = {
        "workspace": "workspace",
        "job": "training job",
        "ray": "Ray job",
        "serving": "serving deployment",
    }[kind]
    return click.command("create", help=f"Create a {label}.")(command)


def run_operation(
    ctx,
    kind,
    verb,
    resource,
    project,
    zone,
    by_name,
    dry_run,
    lookup_settings=(),
    file=None,
    settings=(),
    timeout=1800,
    interval=None,
    follow=False,
    **options,
):
    project, zone = scope_for(ctx, project, zone, required=True)
    w = WORKLOADS[kind]
    action = w["status"] if verb == "wait" else w[verb]
    extra = read_json(file)
    fields = assignments(settings)
    duplicates = extra.keys() & fields.keys()
    if duplicates:
        raise InputError(
            "Fields supplied by both --file and --set: " + ", ".join(sorted(duplicates))
        )
    extra.update(fields)
    validate_workload_extra(kind, extra)
    if verb == "logs":
        controlled = {
            "Start",
            "End",
            "StartTime",
            "EndTime",
            "Method",
            "Limit",
            "Replicas",
            "Direction",
        }
        if controlled.intersection(extra):
            raise InputError(
                "Use log options for time, limit and instance; direction is managed automatically"
            )
    with client_for(ctx) as client:
        rid = resolve(
            client, kind, resource, project, zone, by_name, lookup=assignments(lookup_settings)
        )
        params = workload_params(kind, verb, rid, project, zone, extra=extra, **options)
        if dry_run:
            emit(ctx, client.dry_run(w["service"], action, params), w["service"], action)
        elif verb == "wait":
            emit_result(
                ctx,
                wait(client, kind, params, timeout=timeout, interval=interval),
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


def action_command(kind, verb):
    @click.pass_context
    def command(ctx, **options):
        run_operation(ctx, kind, verb, **options)

    return click.command(verb)(resource_options(extra_options(kind, verb, command)))


def wait_command(kind):
    @click.option("--no-timeout", is_flag=True, help="Wait until completion or interruption.")
    @click.option("--timeout", type=click.FloatRange(min=0), default=1800, show_default=True)
    @click.option(
        "--interval",
        type=click.FloatRange(min=0.1),
        default=5,
        show_default=True,
        help="Polling interval in seconds.",
    )
    @click.pass_context
    def command(ctx, no_timeout, **options):
        if no_timeout:
            if ctx.get_parameter_source("timeout") == ParameterSource.COMMANDLINE:
                raise InputError("--timeout and --no-timeout are mutually exclusive")
            options["timeout"] = None
        run_operation(ctx, kind, "wait", **options)

    return click.command("wait", help="Wait for the workload to reach its success state.")(
        resource_options(extra_options(kind, "wait", command))
    )


def logs_command(kind):
    @click.option(
        "--follow", is_flag=True, help="Poll logs; incompatible with --json, --dry-run and --end."
    )
    @click.option(
        "--interval",
        type=click.FloatRange(min=0.1),
        help="Polling seconds with --follow (default: 3).",
    )
    @click.option("--start", help="Unix nanoseconds or RFC3339 with timezone, inclusive.")
    @click.option("--end", help="Unix nanoseconds or RFC3339 with timezone; default: now.")
    @click.option("--since", help="Positive duration before end, e.g. 15m; excludes --start.")
    @click.option("--limit", type=click.IntRange(1, 10000), default=200, show_default=True)
    @click.option("--instance", help="Replica filter.")
    @click.pass_context
    def command(ctx, follow, interval, since, **options):
        if follow and (ctx.obj["json"] or options["dry_run"] or options["end"] is not None):
            raise InputError("--follow requires logs without --json, --dry-run or --end")
        if interval is not None and not follow:
            raise InputError("--interval requires --follow")
        if since is not None and options["start"] is not None:
            raise InputError("--since and --start are mutually exclusive")
        options["start"] = timestamp_ns(options["start"])
        options["end"] = timestamp_ns(options["end"])
        if since is not None:
            options["end"] = time.time_ns() if options["end"] is None else options["end"]
            options["start"] = options["end"] - duration_ns(since)
        run_operation(ctx, kind, "logs", follow=follow, interval=interval, **options)

    return click.command("logs", help="Read workload logs.")(
        resource_options(extra_options(kind, "logs", command))
    )


def scale_command(kind):
    @click.option(
        "--replicas", required=True, type=click.IntRange(min=0), help="Desired replica count."
    )
    @click.pass_context
    def command(ctx, **options):
        run_operation(ctx, kind, "scale", **options)

    return click.command("scale", help="Set the serving replica count.")(resource_options(command))


def workers_command(kind):
    @click.option(
        "--file", required=True, help="JSON object containing WorkerGroups; use - for stdin."
    )
    @click.pass_context
    def command(ctx, **options):
        run_operation(ctx, kind, "workers", **options)

    return click.command("workers", help="Update Ray worker groups from a request file.")(
        resource_options(command)
    )


def register_workloads(main):
    for kind, w in WORKLOADS.items():
        group = click.Group(kind, help=f"Manage {kind}; use --help on each operation.")
        group.add_command(query_command(w["service"], w["list"], "list"))
        group.add_command(create_command(kind))
        for verb in w:
            if verb in ("service", "id", "list", "create"):
                continue
            factory = {
                "logs": logs_command,
                "scale": scale_command,
                "workers": workers_command,
            }.get(verb)
            group.add_command(factory(kind) if factory else action_command(kind, verb))
        group.add_command(wait_command(kind))
        if kind in ("workspace", "job"):
            connection_commands(group, kind)
        main.add_command(group)
