"""Pure workload request construction, shared independently of Click."""

from .errors import InputError


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
):
    if login_shell and kind != "job":
        raise InputError("Login shell is only supported for job creation")
    if sku_scope not in (None, "public", "tenant", "project"):
        raise InputError("SKU scope must be public, tenant or project")
    if kind not in ("workspace", "job"):
        raise InputError("Ray and serving creation require --file")
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
        spec.update(Command=["sh", "-lc" if login_shell else "-c", entrypoint], Env={}, Replicas=1)
        params["TaskSpecs"] = {"t0": spec}
    else:
        if entrypoint:
            raise InputError(
                "Workspace API has no creation Command field; use workspace exec after startup"
            )
        params.update(spec)
        params["SystemDisk"] = {"Name": name + "-system", "Storage": "50Gi"}
    return params
