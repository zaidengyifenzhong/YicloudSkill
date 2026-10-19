"""Resource and project queries shared with workload listing."""

import click

from ..cli_support import assignments, client_for, emit_result, read_json
from ..errors import InputError
from ..workflows import paginated, scoped_params


def query_command(service, action, name):
    @click.command(name)
    @click.option("--file", help="Request JSON; mutually exclusive with flags.")
    @click.option("--project")
    @click.option("--zone")
    @click.option("--set", "settings", multiple=True, help="Official field as FIELD=JSON.")
    @click.option("--all", "all_pages", is_flag=True, help="Read all pages.")
    @click.pass_context
    def command(ctx, file, project, zone, settings, all_pages):
        if file and (project or zone or settings):
            raise InputError("--file and field flags are mutually exclusive")
        params = read_json(file) if file else scoped_params(service, action, project, zone)
        params.update(assignments(settings))
        with client_for(ctx) as client:
            emit_result(ctx, paginated(client, service, action, params, all_pages), service, action)

    return command


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
