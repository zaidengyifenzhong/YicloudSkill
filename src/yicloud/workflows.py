import json
import math
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


def workload_list_params(kind, resource_id, project, zone):
    w = WORKLOADS[kind]
    params = scoped_params(w["service"], w["list"], project, zone)
    # These filters only narrow the query. Always compare returned IDs exactly.
    if kind == "workspace":
        params["WorkspaceId"] = [resource_id]
    elif kind == "job":
        params["JobIds"] = resource_id
    elif kind == "serving":
        params["Id"] = resource_id
    return params


def resource_rows(client, kind, resource_id, project, zone):
    w = WORKLOADS[kind]
    result = paginated(
        client,
        w["service"],
        w["list"],
        workload_list_params(kind, resource_id, project, zone),
        True,
    )
    rows = items(result.data)
    id_field = LIST_FIELDS[kind]["id"]
    if any(
        not isinstance(row, dict) or not isinstance(row.get(id_field), str) or not row[id_field]
        for row in rows
    ):
        raise YicloudError("Cannot identify resources in list response; scope is not verified")
    matches = [row for row in rows if row[id_field] == resource_id]
    if len(matches) > 1:
        raise YicloudError("Resource ID is ambiguous in list response; scope is not verified")
    return result, matches


def _check_scope_fields(data, kind, resource_id, project, zone):
    if not isinstance(data, dict):
        raise YicloudError("Unrecognized resource detail response; scope is not verified")
    expected = {"Project": project, "Namespace": project, "ZoneId": zone}
    # Endpoints identify their target by ID. Also check echoed IDs whenever available.
    for key in {WORKLOADS[kind]["id"], LIST_FIELDS[kind]["id"]}:
        if key in data and data[key] != resource_id:
            raise InputError(f"Resource ID mismatch in {key}; refusing to write")
    for key, value in expected.items():
        if key in data and data[key] != value:
            raise InputError(f"Resource scope mismatch in {key}; refusing to write")
    return ("Project" in data or "Namespace" in data) and "ZoneId" in data


def verify_workload_scope(client, kind, resource_id, project, zone):
    """Verify actual resource ownership before a CLI mutation, never during preview."""
    if not project or not zone:
        raise InputError("Resource writes require project and zone for scope verification")
    w = WORKLOADS[kind]
    params = scoped_params(w["service"], w["status"], project, zone, resource_id, w["id"])
    detail = client.call(w["service"], w["status"], params)
    if _check_scope_fields(detail.data, kind, resource_id, project, zone):
        return
    _, rows = resource_rows(client, kind, resource_id, project, zone)
    if not rows or not _check_scope_fields(rows[0], kind, resource_id, project, zone):
        raise YicloudError(
            "API responses cannot prove the requested project and zone; refusing to write"
        )


def workload_write_kind(service, action):
    """Only operations with a known parent workload identity can use this guard."""
    for kind, w in WORKLOADS.items():
        if w["service"] != service or action == w["create"]:
            continue
        op = operation(service, action)
        fields = request_schema(op)["properties"]
        if not op["read_only"] and (w["id"] in fields or "Resources" in fields):
            return kind
    return None


def verify_workload_write(client, service, action, params, *, zone=None):
    kind = workload_write_kind(service, action)
    if kind is None:
        return
    w = WORKLOADS[kind]
    targets = params.get("Resources", [params])
    if not isinstance(targets, list) or not targets:
        raise InputError("Resource write requires at least one identifiable target")
    for target in targets:
        if not isinstance(target, dict) or not target.get(w["id"]):
            raise InputError("Resource write requires an explicit workload ID for every target")
        verify_workload_scope(
            client,
            kind,
            target[w["id"]],
            target.get("Project"),
            target.get("ZoneId") or zone,
        )


def validate_polling(timeout, interval):
    if timeout is not None and (
        type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout < 0
    ):
        raise InputError("Wait timeout must be finite and non-negative or None")
    if type(interval) not in (int, float) or not math.isfinite(interval) or interval <= 0:
        raise InputError("Polling interval must be finite and positive")


def _wait_deadline(timeout, interval, clock):
    validate_polling(timeout, interval)
    return None if timeout is None else clock() + timeout


def _wait_sleep(deadline, interval, clock, sleep, evidence):
    remaining = interval if deadline is None else deadline - clock()
    if remaining <= 0:
        raise WaitTimeout(
            "Local wait timed out; remote workload was not stopped; query status again",
            **evidence,
        )
    sleep(min(interval, remaining))


def wait_deleted(
    client,
    kind,
    resource_id,
    project,
    zone,
    *,
    timeout=1800,
    interval=5,
    clock=time.monotonic,
    sleep=time.sleep,
):
    """Confirm absence from a complete scoped listing, without reclassifying API errors."""
    deadline = _wait_deadline(timeout, interval, clock)
    while True:
        result, rows = resource_rows(client, kind, resource_id, project, zone)
        observed_at = datetime.now(timezone.utc).isoformat()
        if not rows:
            result.data = {
                "resource_id": resource_id,
                "project": project,
                "zone": zone,
                "state": "absent",
                "evidence": "complete_scoped_list",
                "observed_at": observed_at,
            }
            return result
        if not _check_scope_fields(rows[0], kind, resource_id, project, zone):
            raise YicloudError("Cannot verify the listed resource scope while waiting for deletion")
        _wait_sleep(
            deadline,
            interval,
            clock,
            sleep,
            {
                "last_status": "present",
                "observed_at": observed_at,
                "request_id": result.request_id,
            },
        )


def _replicas_ready(data, replicas, evidence):
    # GetInferSet's documented counts apply to simple deployments, not distributed
    # or PD topologies. Missing mode flags do not prove a simple deployment.
    for field in ("Distributed", "PDSeparationEnabled"):
        if data.get(field) is not False:
            raise UnknownState(
                f"Replica waiting requires {field}=false; inspect deployment topology", **evidence
            )
    counts = [data.get(field) for field in ("Replicas", "TotalReplicas", "ReadyReplicas")]
    if any(type(count) is not int or count < 0 for count in counts):
        raise UnknownState(
            "Replica counts are missing or invalid; cannot verify readiness", **evidence
        )
    return all(count == replicas for count in counts)


def wait(
    client,
    kind,
    params,
    *,
    timeout=1800,
    interval=5,
    target="default",
    replicas=None,
    clock=time.monotonic,
    sleep=time.sleep,
):
    w = WORKLOADS[kind]
    if target not in {"default", "stopped"}:
        raise InputError("Status wait target must be default or stopped")
    if replicas is not None and (
        kind != "serving" or target != "default" or type(replicas) is not int or replicas < 0
    ):
        raise InputError(
            "Replica waiting requires serving default target and a non-negative integer"
        )
    deadline = _wait_deadline(timeout, interval, clock)
    success = (
        {"stopped"}
        if target == "stopped"
        else (
            {"running"}
            if kind in ("workspace", "serving")
            else {"succeeded", "complete", "completed"}
        )
    )
    if replicas == 0:
        success = {"running", "stopped"}
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
    if target == "stopped":
        pending.add("stopping")
    while True:
        result = client.call(w["service"], w["status"], params)
        observed_at = datetime.now(timezone.utc).isoformat()
        data = result.data
        evidence = dict(
            last_status="unknown", observed_at=observed_at, request_id=result.request_id
        )
        if not isinstance(data, dict):
            raise UnknownState("Unrecognized workload status response", **evidence)
        raw_status = data.get("Phase", data.get("Status", data.get("JobStatus")))
        if not isinstance(raw_status, str) or not raw_status:
            raise UnknownState("Missing or invalid workload status", **evidence)
        status = raw_status.lower()
        evidence["last_status"] = status
        ready = _replicas_ready(data, replicas, evidence) if replicas is not None else True
        if status in success and ready:
            return result
        if target == "stopped" and status in {"succeeded", "complete", "completed"}:
            raise RemoteFailed(f"Remote workload ended with {status}, not stopped", **evidence)
        if (
            status
            in {"failed", "stopped", "stopping", "deleted", "selfhealfailed"} - success - pending
        ):
            raise RemoteFailed(f"Remote workload ended with {status}", **evidence)
        if status not in pending | success:
            raise UnknownState(
                f"Unknown workload status: {status}; inspect status/events manually", **evidence
            )
        _wait_sleep(deadline, interval, clock, sleep, evidence)


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
    validate_polling(None, interval)
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
