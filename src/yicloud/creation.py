"""Pure workload request construction, shared independently of Click."""

from .errors import InputError
from .time_input import duration_ns


def create_params(
    kind,
    *,
    name=None,
    project=None,
    zone=None,
    image=None,
    entrypoint=None,
    sku=None,
    sku_scope=None,
    quota_group=None,
    cpu=None,
    memory=None,
    gpu=None,
    login_shell=False,
    use_private_machine=None,
    qos=None,
    priority=None,
    max_wait_duration=None,
    max_running_duration=None,
):
    if login_shell and kind != "job":
        raise InputError("Login shell is only supported for job creation")
    if sku_scope not in (None, "public", "tenant", "project"):
        raise InputError("SKU scope must be public, tenant or project")
    if kind not in ("workspace", "job"):
        raise InputError("Ray and serving creation require --file")
    scheduling = (use_private_machine, qos, priority, max_wait_duration, max_running_duration)
    if kind != "job" and any(value is not None for value in scheduling):
        raise InputError("Scheduling and task duration shortcuts are only supported for jobs")
    if use_private_machine is not None and type(use_private_machine) is not bool:
        raise InputError("--use-private-machine requires a boolean")
    if priority is not None and (type(priority) is not int or not 1 <= priority <= 9):
        raise InputError("--priority requires an integer from 1 to 9")
    if qos is not None and (not isinstance(qos, str) or not qos or qos.strip() != qos):
        raise InputError("--qos requires a nonempty platform value without surrounding whitespace")
    durations = {}
    for field, option, value in (
        ("MaxWaitDuration", "--max-wait-duration", max_wait_duration),
        ("MaxRunningDuration", "--max-running-duration", max_running_duration),
    ):
        if value is not None:
            durations[field] = f"{duration_ns(value, option=option) // 10**9}s"
    if not all((name, project, zone, image)):
        raise InputError("Shortcut requires --name --project --zone --image")
    if sku:
        if not sku_scope or any((quota_group, cpu, memory, gpu)):
            raise InputError(
                "SKU mode requires --sku-scope and excludes quota-group/cpu/memory/gpu"
            )
    elif not all((quota_group, cpu, memory)) or sku_scope:
        raise InputError(
            "Quota mode requires --quota-group --cpu --memory; otherwise use --sku and --sku-scope"
        )
    params = {"Name": name, "Project": project, "ZoneId": zone}
    # Quota-mode CPU jobs use an explicit zero, matching the console request.
    # Full request files and SKU-based selection retain their original semantics.
    if kind == "job" and quota_group and gpu is None:
        gpu = "0"
    spec = {
        k: v
        for k, v in {"Image": image, "CPU": cpu, "Memory": memory, "GPU": gpu}.items()
        if v is not None
    }
    if sku:
        spec["SkuId" if kind == "workspace" else "SKUId"] = sku
        if kind == "workspace":
            params.update(SkuPublic=sku_scope == "public", SkuPrivate=sku_scope != "public")
            if sku_scope != "public":
                params["SkuTenant" if sku_scope == "tenant" else "SkuProject"] = True
        else:
            params.update(SKUPublic=sku_scope == "public", SKUPrivate=sku_scope != "public")
            if sku_scope != "public":
                params["SKUPrivateTenant" if sku_scope == "tenant" else "SKUPrivateProject"] = True
    if quota_group:
        params["QuotaGroup"] = quota_group
    if kind == "job":
        if not entrypoint:
            raise InputError("Training shortcut requires --command")
        params.update(
            {
                key: value
                for key, value in {
                    "UsePrivateMachine": use_private_machine,
                    "Qos": qos,
                    "Priority": str(priority) if priority is not None else None,
                }.items()
                if value is not None
            }
        )
        spec.update(Command=["sh", "-lc" if login_shell else "-c", entrypoint], Env={}, Replicas=1)
        spec.update(durations)
        params["TaskSpecs"] = {"t0": spec}
    else:
        if entrypoint:
            raise InputError(
                "Workspace API has no creation Command field; use workspace exec after startup"
            )
        params.update(spec)
        params["SystemDisk"] = {"Name": name + "-system", "Storage": "50Gi"}
    return params
