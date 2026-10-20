"""Field-aware commands for HTTP operations without a hand-written workflow."""

import json
from pathlib import Path

import click

from ..catalog import operation, request_schema, validate
from ..cli_support import assignments, client_for, emit, emit_result, read_json, scope_for
from ..command_routes import EDIT_IDS, command_routes, kebab
from ..errors import InputError
from ..output import secret_values
from ..workflows import paginated, verify_workload_write, workload_write_kind


class JSONValue(click.ParamType):
    name = "JSON"

    def convert(self, value, param, ctx):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            self.fail("Expected valid JSON", param, ctx)


def field_type(schema):
    # Unknown types and nested structures retain the API's JSON representation.
    if "ref" in schema:
        return JSONValue()
    return {
        "string": click.STRING,
        "integer": click.INT,
        "number": click.FLOAT,
        "boolean": click.BOOL,
    }.get(schema.get("type"), JSONValue())


def field_flags(fields):
    reserved = {"file", "set", "dry-run", "all", "output", "help"}
    flags = {}
    for field in fields:
        flag = {"Project": "project", "ZoneId": "zone"}.get(field, kebab(field))
        if flag in reserved or flag in flags.values():
            flag = "field-" + flag
        if flag in flags.values():
            raise ValueError(f"Ambiguous CLI field: {field}")
        flags[field] = flag
    return flags


def request_command(service, action, name):
    op = operation(service, action)
    schema = request_schema(op)
    fields = schema["properties"]
    id_field = EDIT_IDS.get((service, action))
    guarded_write = workload_write_kind(service, action) is not None
    can_page = op["read_only"] and {"Limit", "Offset"} <= fields.keys()
    can_download = op["response_mode"] == "file"
    # Indexed parameter names keep official field spelling separate from Click names.
    names = {f"field_{index}": field for index, field in enumerate(fields)}

    @click.pass_context
    def command(ctx, file, settings, dry_run, **values):
        resource = values.pop("resource", None)
        verification_zone = values.pop("verification_zone", None)
        all_pages = values.pop("all_pages", False)
        output = values.pop("output", None)
        explicit = {
            field: values[key]
            for key, field in names.items()
            if ctx.get_parameter_source(key) == click.core.ParameterSource.COMMANDLINE
        }
        ctx.obj["secrets"].extend(secret_values(explicit))
        if file is not None and (explicit or settings or resource is not None):
            raise InputError("--file and resource/field options/--set are mutually exclusive")
        if all_pages and dry_run:
            raise InputError("--all and --dry-run are mutually exclusive")
        if file is not None:
            params = read_json(file)
        else:
            params = assignments(settings)
            duplicates = params.keys() & explicit.keys()
            if duplicates:
                raise InputError(
                    "Fields supplied by both options and --set: " + ", ".join(sorted(duplicates))
                )
            params.update(explicit)
            if resource is not None:
                if id_field in params:
                    raise InputError(f"Resource ID supplied twice: {id_field}")
                params[id_field] = resource
            allowed = tuple(
                key
                for key, field in (("project", "Project"), ("zone", "ZoneId"))
                if field in fields and field not in params
            )
            if allowed or {"Project", "ZoneId"} & params.keys():
                project, zone = scope_for(
                    ctx, params.get("Project"), params.get("ZoneId"), allowed=allowed
                )
                for key, value in (("Project", project), ("ZoneId", zone)):
                    if key in fields and key not in params and value is not None:
                        params[key] = value
        if id_field and not params.get(id_field):
            raise InputError(f"Requires a resource ID ({id_field}); names are not resolved")
        validate(op, params)
        if all_pages and (
            not isinstance(params.get("Limit", 20), int)
            or params.get("Limit", 20) <= 0
            or not isinstance(params.get("Offset", 0), int)
            or params.get("Offset", 0) < 0
        ):
            raise InputError("--all requires a positive Limit and a non-negative Offset")
        if can_download and output is None and not dry_run:
            raise InputError("File response requires --output PATH")
        with client_for(ctx) as client:
            if dry_run:
                emit(ctx, client.dry_run(service, action, params), service, action)
            elif all_pages:
                emit_result(
                    ctx, paginated(client, service, action, params, all_pages), service, action
                )
            else:
                if guarded_write:
                    _, scope_zone = scope_for(
                        ctx, None, params.get("ZoneId") or verification_zone, allowed=("zone",)
                    )
                    verify_workload_write(client, service, action, params, zone=scope_zone)
                emit_result(
                    ctx, client.call(service, action, params, output=output), service, action
                )

    options = [
        click.Option(
            ["--file"],
            help="Complete request JSON or - for stdin; excludes field options and resource ID.",
        ),
        click.Option(
            ["--set", "settings"],
            multiple=True,
            help="Additional FIELD=JSON, including explicit null; no duplicate fields.",
        ),
        click.Option(
            ["--dry-run"], is_flag=True, help="Validate and preview without sending requests."
        ),
    ]
    flags = field_flags(fields)
    for key, field in names.items():
        spec = fields[field]
        required = " Required by API." if field in schema.get("required", []) else ""
        choices = " Values: " + ", ".join(spec["enum"]) + "." if spec.get("enum") else ""
        options.append(
            click.Option(
                ["--" + flags[field], key],
                type=field_type(spec),
                default=None,
                help=f"{field}: {spec.get('description', '')}.{required}{choices}",
            )
        )
    if guarded_write and "ZoneId" not in fields:
        options.append(
            click.Option(
                ["--zone", "verification_zone"],
                help="Zone for pre-write resource verification; not added to the API request.",
            )
        )
    if id_field:
        options.append(click.Argument(["resource"], required=False))
    if can_page:
        options.append(
            click.Option(
                ["--all", "all_pages"], is_flag=True, help="Read all pages; excludes --dry-run."
            )
        )
    if can_download:
        options.append(
            click.Option(
                ["--output"],
                type=click.Path(path_type=Path),
                help="Destination for the downloaded file.",
            )
        )
    return click.Command(
        name,
        callback=command,
        params=options,
        help=f"{action}: {(op['description'] or action).splitlines()[0]}\n\n"
        "Field options use the selected context for missing Project/ZoneId. "
        "Request files are sent without context injection. Booleans take true/false; "
        "objects and arrays take JSON."
        + (f" RESOURCE is the {id_field}, not a display name." if id_field else ""),
    )


def register_catalog_commands(main):
    for (service, action), route in command_routes().items():
        group = main
        for part in route[:-1]:
            if part not in group.commands:
                group.add_command(
                    click.Group(part, help=f"Manage {part} resources; see each command's --help.")
                )
            group = group.commands[part]
            if not isinstance(group, click.Group):
                raise ValueError(f"Command route conflicts with an existing command: {route}")
        if route[-1] not in group.commands:
            group.add_command(request_command(service, action, route[-1]))
