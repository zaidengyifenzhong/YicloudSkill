"""Catalog discovery and generic API calls."""

from pathlib import Path

import click

from ..catalog import catalog, operation, request_schema
from ..cli_support import client_for, emit, emit_result, read_json
from ..errors import InputError


@click.group()
def api():
    """Discover and invoke the pinned SDK operation catalog."""


@api.command("list")
@click.option("--service")
@click.pass_context
def api_list(ctx, service):
    rows = [
        {
            k: op[k]
            for k in ("service", "action", "method", "path", "read_only", "response_mode", "status")
        }
        for op in catalog()["operations"]
        if service is None or op["service"] == service
    ]
    if service and not rows:
        raise InputError(f"Unknown service: {service}")
    emit(ctx, rows)


@api.command("describe")
@click.argument("service")
@click.argument("action")
@click.pass_context
def api_describe(ctx, service, action):
    op = operation(service, action)
    schema = request_schema(op)
    definitions = catalog()["definitions"][service]
    reachable = {}

    def visit(value):
        if isinstance(value, dict):
            ref = value.get("ref")
            if ref and ref not in reachable:
                reachable[ref] = definitions[ref]
                visit(definitions[ref])
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(schema)
    emit(
        ctx,
        dict(op, schema=schema, definitions=reachable),
        schema=True,
    )


@api.command("call")
@click.argument("service")
@click.argument("action")
@click.option("--file", type=str, help="JSON request file, or - for stdin.")
@click.option("--dry-run", is_flag=True)
@click.option("--allow-unknown-fields", is_flag=True)
@click.option("--output", type=click.Path(path_type=Path), help="Destination for file responses.")
@click.pass_context
def api_call(ctx, service, action, file, dry_run, allow_unknown_fields, output):
    params = read_json(file)
    with client_for(ctx) as client:
        if dry_run:
            emit(
                ctx,
                client.dry_run(service, action, params, allow_unknown_fields=allow_unknown_fields),
                service,
                action,
            )
        else:
            emit_result(
                ctx,
                client.call(
                    service,
                    action,
                    params,
                    allow_unknown_fields=allow_unknown_fields,
                    output=output,
                ),
                service,
                action,
            )
