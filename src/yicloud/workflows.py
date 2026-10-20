import json
import time
from datetime import datetime, timezone

from .catalog import operation, request_schema
from .errors import InputError, RemoteFailed, UnknownState, WaitTimeout, YicloudError

WORKLOADS = {
    "workspace": {
        "service": "workspace",
        "id": "WorkspaceId",
        "list": "ListWorkspaces",
        "status": "GetWorkspace",
        "create": "CreateWorkspace",
        "start": "StartWorkspace",
        "stop": "StopWorkspace",
        "restart": "RestartWorkspace",
        "delete": "DeleteWorkspace",
        "processes": "ListProcesses",
    },
    "job": {
        "service": "job",
        "id": "JobId",
        "list": "ListJobs",
        "status": "GetJob",
        "create": "CreateJob",
        "stop": "StopJob",
        "delete": "BatchDeleteJobs",
        "replicas": "ListJobReplicas",
        "precheck": "GetPrecheckStatus",
        "logs": "GetLogs",
    },
    "ray": {
        "service": "ray",
        "id": "JobName",
        "list": "ListRayJobs",
        "status": "GetRayJob",
        "create": "CreateRayJob",
        "stop": "StopRayJob",
        "delete": "DeleteRayJob",
        "events": "GetRayJobEvents",
        "instances": "GetRayJobPods",
        "workers": "UpdateRayJobWorkerGroups",
        "logs": "GetRayJobLogs",
    },
    "serving": {
        "service": "inferset",
        "id": "ID",
        "list": "ListInferSet",
        "status": "GetInferSet",
        "create": "CreateInferSet",
        "start": "StartInferSet",
        "stop": "StopInferSet",
        "delete": "DeleteInferSet",
        "scale": "ScaleInferSet",
        "instances": "ListInferSetReplica",
        "logs": "GetInferSetLogsQueryRange",
    },
}


# Response fields differ from lifecycle request fields in the fixed SDK.
LIST_FIELDS = {
    "workspace": {"project": "Project", "name": "Name", "id": "WorkspaceId"},
    "job": {"project": "Project", "name": "Name", "id": "JobId"},
    "ray": {"project": "Namespace", "name": "DisplayName", "id": "RayJobName"},
    "serving": {"project": "Namespace", "name": "Name", "id": "ID"},
}


def items(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in (
            "Items",
            "Files",
            "items",
            "List",
            "list",
            "Replicas",
            "Pods",
            "Data",
            "GetInferSetLogsQueryRangeData",
        ):
            if isinstance(data.get(key), list):
                return data[key]
    raise YicloudError("Unrecognized list response; inspect with api call")


def paginated(client, service, action, params, all_pages=False):
    fields = request_schema(operation(service, action))["properties"]
    params = dict(params)
    if "Limit" not in fields or "Offset" not in fields:
        return client.call(service, action, params)
    params.setdefault("Limit", 20)
    params.setdefault("Offset", 0)
    if all_pages and (
        type(params["Limit"]) is not int
        or params["Limit"] <= 0
        or type(params["Offset"]) is not int
        or params["Offset"] < 0
    ):
        raise InputError("Pagination requires a positive Limit and a non-negative Offset")
    result = client.call(service, action, params)
    if not all_pages:
        return result
    combined = []
    previous = set()
    current = result
    while True:
        page = items(current.data)
        if page:
            fingerprint = json.dumps(page, sort_keys=True)
            if fingerprint in previous:
                raise YicloudError("Pagination did not advance; server repeated a page")
            previous.add(fingerprint)
        combined.extend(page)
        offset = params["Offset"] + len(page)
        total = current.data.get("Total") if isinstance(current.data, dict) else None
        if type(total) is int and total >= 0:
            # A server may cap Limit. Its total, rather than the requested page size,
            # determines whether a short page is actually the last one.
            if offset >= total:
                break
            if not page:
                raise YicloudError("Pagination ended before the advertised total; retry the query")
        elif len(page) < params["Limit"]:
            break
        params["Offset"] = offset
        current = client.call(service, action, params)
    result.data = {"Items": combined, "Total": len(combined)}
    return result


def resolve(client, kind, value, project, zone, by_name=False, *, lookup=None):
    w = WORKLOADS[kind]
    lookup = {} if lookup is None else dict(lookup)
    if lookup and not by_name:
        raise InputError("Name lookup filters require --by-name")
    if lookup.keys() & {"Project", "ZoneId", "Limit", "Offset"}:
        raise InputError("Name lookup filters cannot override scope or pagination")
    if not by_name:
        return value
    if not project or not zone:
        raise InputError("Name lookup requires --project and --zone")
    params = {"Project": project}
    fields = request_schema(operation(w["service"], w["list"]))["properties"]
    if "ZoneId" in fields:
        params["ZoneId"] = zone
    params.update(lookup)
    rows = items(paginated(client, w["service"], w["list"], params, True).data)
    fields = LIST_FIELDS[kind]
    matches = [
        r
        for r in rows
        if r.get(fields["name"]) == value
        and r.get(fields["project"]) == project
        and r.get("ZoneId") == zone
    ]
    if len(matches) != 1:
        candidates = [
            {k: r.get(k) for k in (fields["id"], fields["name"], fields["project"], "ZoneId")}
            for r in matches
        ]
        raise InputError(
            f"Name lookup found {len(matches)} matches: {json.dumps(candidates, ensure_ascii=False)}"
        )
    row = matches[0]
    resource_id = row.get(fields["id"])
    if not resource_id:
        raise YicloudError("Matched resource has no identifier")
    return resource_id


def scoped_params(service, action, project=None, zone=None, resource_id=None, id_field=None):
    fields = request_schema(operation(service, action))["properties"]
    params = {}
    for key, value in (("Project", project), ("ZoneId", zone), (id_field, resource_id)):
        if key in fields and value is not None:
            params[key] = value
    return params


def validate_workload_extra(kind, extra):
    """Reject explicit resource overrides before any optional name lookup."""
    if any(key in extra for key in ("Project", "ZoneId", WORKLOADS[kind]["id"], "Resources")):
        raise InputError("Additional fields cannot override explicit scope or resource")


def workload_params(
    kind,
    verb,
    resource_id,
    project,
    zone,
    *,
    extra=None,
    replicas=None,
    start=None,
    end=None,
    limit=200,
    instance=None,
):
    """Build a lifecycle request for an already resolved resource, without performing I/O."""
    w = WORKLOADS[kind]
    action = w["status"] if verb == "wait" else w[verb]
    extra = {} if extra is None else dict(extra)
    validate_workload_extra(kind, extra)
    params = scoped_params(w["service"], action, project, zone, resource_id, w["id"])
    if kind == "job" and verb == "delete":
        params = {"Resources": [{"Project": project, "JobId": resource_id}]}
    params.update(extra)
    if verb == "scale":
        if replicas is None:
            raise InputError("scale requires --replicas")
        if type(replicas) is not int or replicas < 0:
            raise InputError("scale requires a non-negative integer replica count")
        params["Replicas"] = replicas
    if verb == "logs":
        params = log_params(kind, params, start, end, limit, instance)
    return params


def wait(client, kind, params, *, timeout=1800, interval=5, clock=time.monotonic, sleep=time.sleep):
    w = WORKLOADS[kind]
    if timeout is not None and timeout < 0:
        raise InputError("Wait timeout must be non-negative or None")
    if interval <= 0:
        raise InputError("Wait interval must be positive")
    deadline = None if timeout is None else clock() + timeout
    success = (
        {"running"} if kind in ("workspace", "serving") else {"succeeded", "complete", "completed"}
    )
    pending = {
        "pending",
        "starting",
        "running",
        "scanning",
        "restarting",
        "inqueue",
        "initializing",
        "deploying",
        "selfhealtriggered",
        "selfhealrunning",
        "selfhealsucceeded",
    }
    while True:
        result = client.call(w["service"], w["status"], params)
        observed_at = datetime.now(timezone.utc).isoformat()
        data = result.data or {}
        status = str(
            data.get("Phase", data.get("Status", data.get("JobStatus", "Unknown")))
        ).lower()
        evidence = dict(last_status=status, observed_at=observed_at, request_id=result.request_id)
        if status in success:
            return result
        if status in {"failed", "stopped", "stopping", "deleted", "selfhealfailed"}:
            raise RemoteFailed(f"Remote workload ended with {status}", **evidence)
        if status not in pending:
            raise UnknownState(
                f"Unknown workload status: {status}; inspect status/events manually", **evidence
            )
        remaining = interval if deadline is None else deadline - clock()
        if remaining <= 0:
            raise WaitTimeout(
                "Local wait timed out; remote workload was not stopped; query status again",
                **evidence,
            )
        sleep(min(interval, remaining))


def log_params(kind, params, start=None, end=None, limit=200, instance=None):
    end = time.time_ns() if end is None else end
    start = end - 600 * 10**9 if start is None else start
    if start > end:
        raise InputError("Log start must be before end")
    p = dict(params, Limit=limit)
    if kind == "ray":
        p.update(Method="query_range", StartTime=str(start), EndTime=str(end))
    else:
        p.update(Start=start, End=end, Direction="backward")
    if instance:
        p["Replicas"] = [instance] if kind == "serving" else instance
    return p


def follow_logs(client, kind, params, emit, *, interval=3, sleep=time.sleep, clock=time.time_ns):
    w = WORKLOADS[kind]
    start = params.get("Start", int(params.get("StartTime", clock())))
    seen = set()
    while True:
        end = clock()
        query = dict(params)
        if kind == "ray":
            query.update(StartTime=str(start), EndTime=str(end))
        else:
            query.update(Start=start, End=end, Direction="forward")
        result = client.call(w["service"], w["logs"], query)
        batch = items(result.data)
        next_seen = set()
        timestamps = []
        for row in batch:
            mark = json.dumps(row, sort_keys=True, ensure_ascii=False)
            next_seen.add(mark)
            if mark not in seen:
                emit(row)
            try:
                timestamps.append(int(row["Timestamp"]))
            except (TypeError, KeyError, ValueError):
                pass
        # Keep the boundary inclusive; overlapping rows are deduplicated, retaining only two batches.
        if timestamps:
            start = max(start, max(timestamps))
        elif len(batch) >= params.get("Limit", 200):
            raise YicloudError("Log window is full without timestamps; query a narrower range")
        # An empty query is not a watermark: logs may reach the index much later
        # than their event timestamp. Keep the start until a timestamp is observed.
        seen = next_seen
        sleep(interval)
