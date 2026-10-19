import json
import time

from .catalog import operation, request_schema
from .errors import InputError, YicloudError

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


def items(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("Items", "items", "List", "list", "Replicas", "Pods"):
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
    result = client.call(service, action, params)
    if not all_pages:
        return result
    combined = list(items(result.data))
    previous = set()
    page = items(result.data)
    while len(page) == params["Limit"]:
        fingerprint = json.dumps(page, sort_keys=True)
        if fingerprint in previous:
            raise YicloudError("Pagination did not advance; server repeated a page")
        previous.add(fingerprint)
        params["Offset"] += len(page)
        next_result = client.call(service, action, params)
        page = items(next_result.data)
        combined.extend(page)
        if isinstance(next_result.data, dict) and len(combined) >= next_result.data.get(
            "Total", float("inf")
        ):
            break
    result.data = {"Items": combined, "Total": len(combined)}
    return result


def resolve(client, kind, value, project, zone, by_name=False):
    w = WORKLOADS[kind]
    if not by_name:
        return value
    if not project or not zone:
        raise InputError("Name lookup requires --project and --zone")
    params = {"Project": project}
    fields = request_schema(operation(w["service"], w["list"]))["properties"]
    if "ZoneId" in fields:
        params["ZoneId"] = zone
    rows = items(paginated(client, w["service"], w["list"], params, True).data)
    matches = [
        r
        for r in rows
        if r.get("Name", r.get("DisplayName")) == value
        and r.get("Project") == project
        and r.get("ZoneId") == zone
    ]
    if len(matches) != 1:
        candidates = [
            {k: r.get(k) for k in (w["id"], "Name", "DisplayName", "Project", "ZoneId")}
            for r in matches
        ]
        raise InputError(
            f"Name lookup found {len(matches)} matches: {json.dumps(candidates, ensure_ascii=False)}"
        )
    row = matches[0]
    resource_id = row.get(w["id"], row.get("Id"))
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


def wait(client, kind, params, *, timeout=1800, interval=5, clock=time.monotonic, sleep=time.sleep):
    w = WORKLOADS[kind]
    deadline = clock() + timeout
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
        data = result.data or {}
        status = str(
            data.get("Phase", data.get("Status", data.get("JobStatus", "Unknown")))
        ).lower()
        if status in success:
            return result
        if status in {"failed", "stopped", "stopping", "deleted", "selfhealfailed"}:
            raise YicloudError(f"Remote workload ended with {status}")
        if status not in pending:
            raise YicloudError(f"Unknown workload status: {status}; inspect status/events manually")
        remaining = deadline - clock()
        if remaining <= 0:
            raise YicloudError("Wait timed out; remote workload continues")
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
        else:
            start = max(start, end - 3 * 10**9)
        seen = next_seen
        sleep(interval)
