"""Resource and project queries shared with workload listing."""

import click

from ..catalog import operation, request_schema
from ..cli_support import assignments, client_for, emit_result, read_json, scope_for
from ..errors import InputError, YicloudError
from ..workflows import paginated, scoped_params


class _NodePages:
    """Adapt the observed ListNodes nil-slice response without relaxing other lists."""

    def __init__(self, client):
        self.client = client
        self.first_data = None
        self.current = None

    def call(self, service, action, params):
        self.current = None
        result = self.client.call(service, action, params)
        self.current = result
        data = result.data
        message = None
        if not isinstance(data, dict) or "Items" not in data:
            message = "Unrecognized ListNodes response; node visibility is not verified"
        elif "Offset" in data and (
            type(data["Offset"]) is not int or data["Offset"] != params["Offset"]
        ):
            message = "ListNodes response Offset does not match the request"
        elif self.first_data is not None and data.get("Total") != self.first_data.get("Total"):
            message = "ListNodes Total changed between pages; completeness is not verified"
        elif data["Items"] is None:
            # The pinned SDK declares Items as []NodeData. A successful live reply
            # serializes the empty slice as null, with explicit pagination fields.
            if not (
                type(data.get("Total")) is int
                and data["Total"] == 0
                and type(data.get("Offset")) is int
                and data["Offset"] >= 0
                and type(data.get("Limit")) is int
                and data["Limit"] > 0
            ):
                message = "ListNodes null Items lacks a verified empty-page contract"
            else:
                result.data = dict(data, Items=[])
        elif not isinstance(data["Items"], list):
            message = "ListNodes Items is not a node list"
        if message:
            raise YicloudError(
                message, request_id=result.request_id, http_status=result.raw.status_code
            )
        if self.first_data is None:
            self.first_data = dict(result.data)
        return result


def _query_result(client, service, action, params, all_pages):
    if (service, action) != ("mc", "ListNodes"):
        return paginated(client, service, action, params, all_pages)
    pages = _NodePages(client)
    try:
        result = paginated(pages, service, action, params, all_pages)
    except YicloudError as error:
        if pages.current is not None and error.request_id is None:
            error.request_id = pages.current.request_id
            error.http_status = pages.current.raw.status_code
        raise
    if all_pages:
        # Keep the server's additional node metadata; generic pagination returns
        # only Items/Total. These fields are copied, never interpreted as capacity.
        result.data = dict(pages.first_data, **result.data)
    return result


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
        if not file:
            allowed = tuple(
                k
                for k, field in (("project", "Project"), ("zone", "ZoneId"))
                if field in fields
                and field not in params
                and not (service == "mc" and action == "ListProjects")
            )
            project, zone = scope_for(
                ctx, params.get("Project"), params.get("ZoneId"), allowed=allowed
            )
            params.update(scoped_params(service, action, project, zone))
        with client_for(ctx) as client:
            emit_result(
                ctx, _query_result(client, service, action, params, all_pages), service, action
            )

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
    "resources",
    help="Query resource specifications, quota groups, nodes and scheduling predictions.",
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
