"""Resource and project queries shared with workload listing."""

import click

from ..catalog import operation, request_schema
from ..cli_support import assignments, client_for, emit_result, read_json
from ..errors import InputError
from ..workflows import paginated, scoped_params


def query_command(service, action, name):
    fields = request_schema(operation(service, action))["properties"]

    @click.pass_context
    def command(ctx, file=None, project=None, zone=None, settings=(), all_pages=False):
        if file and (project is not None or zone is not None or settings):
            raise InputError("--file and field flags are mutually exclusive")
        params = read_json(file) if file else scoped_params(service, action, project, zone)
        extra = assignments(settings)
        duplicates = params.keys() & extra.keys()
        if duplicates:
            raise InputError(
                "Fields supplied by both scope flags and --set: " + ", ".join(sorted(duplicates))
            )
        params.update(extra)
        with client_for(ctx) as client:
            emit_result(ctx, paginated(client, service, action, params, all_pages), service, action)

    if "Limit" in fields and "Offset" in fields:
        command = click.option("--all", "all_pages", is_flag=True, help="Read all pages.")(command)
    if fields:
        command = click.option(
            "--set", "settings", multiple=True, help="Official field as FIELD=JSON."
        )(command)
    if "ZoneId" in fields:
        command = click.option("--zone")(command)
    if "Project" in fields:
        command = click.option("--project")(command)
    if fields:
        command = click.option("--file", help="Request JSON; mutually exclusive with flags.")(
            command
        )
    return click.command(name)(command)


resources = click.Group(
    "resources", help="Discover current capacity; quota does not guarantee free nodes."
)
for name, action in {
    "zones": "ListZones",
    "skus": "ListSKUs",
    "quota-groups": "ListQuotaGroups",
    "nodes": "ListNodes",
    "available": "ListQuotaGroupResourcePoolSharedNodes",
}.items():
    resources.add_command(query_command("mc", action, name))
resources.add_command(query_command("workspace", "GetPredict", "predict"))
project_group = click.Group("project", help="Projects and quota.")
for name, action in {
    "list": "ListProjects",
    "status": "GetProject",
    "quota": "GetProjectQuota",
    "quota-limit": "GetProjectQuotaLimit",
}.items():
    project_group.add_command(query_command("mc", action, name))


def register_discovery(main):
    main.add_command(resources)
    main.add_command(project_group)
