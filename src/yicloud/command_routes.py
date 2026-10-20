"""Stable CLI paths for the HTTP catalog, including existing workflow commands."""

import re

from .catalog import catalog
from .workflows import WORKLOADS


def kebab(value):
    value = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1-\2", value)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", value).replace("_", "-").lower()


DISCOVERY_ROUTES = {
    ("mc", "ListProjects"): ("project", "list"),
    ("mc", "GetProject"): ("project", "status"),
    ("mc", "GetProjectQuota"): ("project", "quota"),
    ("mc", "GetProjectQuotaLimit"): ("project", "quota-limit"),
    ("mc", "ListZones"): ("resources", "zones"),
    ("mc", "ListSKUs"): ("resources", "skus"),
    ("mc", "ListQuotaGroups"): ("resources", "quota-groups"),
    ("mc", "ListNodes"): ("resources", "nodes"),
    ("mc", "ListQuotaGroupResourcePoolSharedNodes"): ("resources", "available"),
    ("workspace", "GetPredict"): ("resources", "predict"),
}

# These commands accept either a resource ID plus field options, or a complete file.
EDIT_IDS = {
    ("workspace", "EditWorkspace"): "WorkspaceId",
    ("job", "EditJob"): "JobId",
    ("inferset", "UpdateInferSet"): "ID",
}


def command_routes():
    routes = {
        (op["service"], op["action"]): (
            *(("serving",) if op["service"] == "inferset" else op["service"].split("/")),
            kebab(op["action"]),
        )
        for op in catalog()["operations"]
        if op["status"] == "implemented-offline"
    }
    for kind, workload in WORKLOADS.items():
        for verb, action in workload.items():
            if verb not in ("service", "id"):
                routes[workload["service"], action] = (kind, verb)
    routes.update(DISCOVERY_ROUTES)
    routes.update(
        {
            ("workspace", "EditWorkspace"): ("workspace", "edit"),
            ("job", "EditJob"): ("job", "edit"),
            ("inferset", "UpdateInferSet"): ("serving", "update"),
            # job delete accepts one ID; retain a full batch request command as well.
            ("job", "BatchDeleteJobs"): ("job", "batch-delete"),
            ("mc", "CreateProject"): ("project", "create"),
            ("mc", "UpdateProject"): ("project", "update"),
            ("mc", "DeleteProject"): ("project", "delete"),
        }
    )
    return routes
