"""Offline regressions derived from live findings; no platform credentials or resources."""

import copy
import json
import os
import subprocess
import sys

import httpx
import pytest
from click.testing import CliRunner

from yicloud.catalog import operation, validate
from yicloud.cli import main
from yicloud.client import YicloudClient
from yicloud.creation import create_params
from yicloud.errors import InputError, YicloudError


def job_request(**extra):
    return {
        "Name": "fixture-job",
        "Project": "fixture-project",
        "ZoneId": "fixture-zone",
        "QuotaGroup": "fixture-quota",
        "TaskSpecs": {
            "task1": {
                "Image": "fixture-image",
                "Command": ["sh", "-c", "true"],
                "CPU": "1",
                "Memory": "1Gi",
                "Env": {},
                "Replicas": 1,
            }
        },
        **extra,
    }


@pytest.mark.parametrize("gpu", [None, "0", "1", "2"])
@pytest.mark.parametrize("kind", ["job", "workspace"])
def test_gpu_default_only_applies_to_quota_job_shortcut(kind, gpu):
    request = create_params(
        kind,
        name="fixture",
        project="fixture-project",
        zone="fixture-zone",
        image="fixture-image",
        entrypoint="true" if kind == "job" else None,
        quota_group="fixture-quota",
        cpu="1",
        memory="1Gi",
        gpu=gpu,
    )
    spec = request["TaskSpecs"]["t0"] if kind == "job" else request
    if gpu is None and kind == "workspace":
        assert "GPU" not in spec
    else:
        assert spec["GPU"] == ("0" if gpu is None else gpu)


def test_sku_job_does_not_add_gpu():
    request = create_params(
        "job",
        name="fixture",
        project="p",
        zone="z",
        image="image",
        entrypoint="true",
        sku="sku",
        sku_scope="public",
    )
    assert "GPU" not in request["TaskSpecs"]["t0"]


@pytest.mark.parametrize("entrypoint", ["shortcut", "file", "api"])
def test_actual_cli_gpu_default_and_raw_request_preservation(tmp_path, entrypoint):
    env = dict(os.environ, YICLOUD_PUBLIC_KEY="fixture-public", YICLOUD_SECRET_KEY="fixture-secret")
    request = job_request(RestartPolicy="Never", BackoffLimit=0)
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request), encoding="utf-8")
    if entrypoint == "shortcut":
        args = [
            "job",
            "create",
            "--name",
            "fixture",
            "--project",
            "p",
            "--zone",
            "z",
            "--image",
            "image",
            "--quota-group",
            "quota",
            "--cpu",
            "1",
            "--memory",
            "1Gi",
            "--command",
            "true",
        ]
    elif entrypoint == "file":
        args = ["job", "create", "--file", str(path)]
    else:
        args = ["api", "call", "job", "CreateJob", "--file", str(path)]
    result = subprocess.run(
        [sys.executable, "-m", "yicloud", "--json", *args, "--dry-run"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    body = json.loads(result.stdout)["data"]["body"]
    if entrypoint == "shortcut":
        assert body["TaskSpecs"]["t0"]["GPU"] == "0"
    else:
        assert body == request


@pytest.mark.parametrize(
    "params,code,expected_hint",
    [
        (job_request(RestartPolicy="Never", BackoffLimit=0), 1001000, "RestartPolicy=Never"),
        (job_request(), 100, 'GPU="0"'),
        (job_request(RestartPolicy="Never"), 1001000, None),
        (job_request(BackoffLimit=0), 1001000, None),
        (job_request(RestartPolicy="Never", BackoffLimit=1), 1001000, None),
        (job_request(RestartPolicy="OnFailure", BackoffLimit=0), 1001000, None),
        (job_request(RestartPolicy="Never", BackoffLimit=0), 101, None),
    ],
)
def test_create_failure_hints_preserve_error_and_never_rewrite_or_retry(
    account, params, code, expected_hint
):
    original = copy.deepcopy(params)
    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={"Code": code, "Msg": "fixture rejection"},
            headers={"X-OGW-Request-Id": "fixture-request-id"},
        )

    with YicloudClient(account, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(YicloudError) as exc:
            client.call("job", "CreateJob", params)
    error = exc.value
    assert sent == [original] and params == original
    assert str(error) == "fixture rejection"
    assert error.code == code and error.request_id == "fixture-request-id"
    assert error.outcome_unknown is False
    if expected_hint:
        assert expected_hint in error.hints[0]
        assert error.as_dict()["hints"] == error.hints
    else:
        assert error.hints == [] and "hints" not in error.as_dict()


@pytest.mark.parametrize("json_output", [True, False])
def test_failure_hints_are_visible_on_stderr(account, monkeypatch, json_output):
    params = job_request(RestartPolicy="Never", BackoffLimit=0)
    monkeypatch.setattr(
        "yicloud.commands.workloads.client_for",
        lambda _: YicloudClient(
            account,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200, json={"Code": 1001000, "Msg": "fixture rejection"}
                )
            ),
        ),
    )
    result = CliRunner().invoke(
        main,
        (["--json"] if json_output else []) + ["job", "create", "--file", "-"],
        input=json.dumps(params),
    )
    assert result.exit_code == 1 and result.stdout == ""
    if json_output:
        error = json.loads(result.stderr)["error"]
        assert error["code"] == 1001000
        assert error["message"] == "fixture rejection"
        assert "RestartPolicy=Never" in error["hints"][0]
    else:
        assert "Hint:" in result.stderr and "RestartPolicy=Never" in result.stderr


@pytest.mark.parametrize("task_change", [{"GPU": "0"}, {"GPU": "1"}, {"SKUId": "fixture-sku"}])
def test_resource_hint_does_not_guess_cpu_intent_for_explicit_gpu_or_sku(account, task_change):
    params = job_request()
    params["TaskSpecs"]["task1"].update(task_change)
    with YicloudClient(
        account,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"Code": 100, "Msg": "fixture rejection"})
        ),
    ) as client:
        with pytest.raises(YicloudError) as exc:
            client.call("job", "CreateJob", params)
    assert exc.value.hints == []


def test_ambiguous_create_failure_keeps_inspect_before_retry_semantics(account):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(500, json={"Code": 1001000, "Msg": "fixture rejection"})

    with YicloudClient(account, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(YicloudError) as exc:
            client.call("job", "CreateJob", job_request(RestartPolicy="Never", BackoffLimit=0))
    assert len(calls) == 1
    assert exc.value.outcome_unknown is True and exc.value.hints == []


@pytest.mark.parametrize("allow_unknown", [True, False])
def test_runtime_cluster_enum_remains_strict_with_catalog_hint(allow_unknown):
    # The observed server value is not silently accepted as a new API contract.
    op = operation("fs", "ListFilesetsWithQuotaInfo")
    with pytest.raises(InputError) as exc:
        validate(op, {"FsCluster": "gpfs2"}, allow_unknown)
    assert "FsCluster: expected one of" in str(exc.value)
    assert "SDK v0.5.1" in exc.value.hints[0]
    assert "does not bypass enum validation" in exc.value.hints[0]


def shortcut_kwargs():
    return dict(
        name="fixture",
        project="p",
        zone="z",
        image="image",
        entrypoint="true",
        quota_group="quota",
        cpu="1",
        memory="1Gi",
    )


def test_job_scheduling_defaults_do_not_override_platform():
    params = create_params("job", **shortcut_kwargs())
    assert not {"UsePrivateMachine", "Qos", "Priority"} & params.keys()
    spec = params["TaskSpecs"]["t0"]
    assert not {"MaxWaitDuration", "MaxRunningDuration"} & spec.keys()
    assert spec["GPU"] == "0"


@pytest.mark.parametrize("private", [True, False])
@pytest.mark.parametrize("priority", [1, 5, 9])
@pytest.mark.parametrize("sku", [True, False])
def test_explicit_job_scheduling_uses_correct_field_locations(private, priority, sku):
    kwargs = shortcut_kwargs()
    if sku:
        for key in ("quota_group", "cpu", "memory"):
            kwargs.pop(key)
        kwargs.update(sku="fixture-sku", sku_scope="public")
    params = create_params(
        "job",
        **kwargs,
        use_private_machine=private,
        qos="Guaranteed",
        priority=priority,
        max_wait_duration="2m",
        max_running_duration="1d",
    )
    assert params["UsePrivateMachine"] is private
    assert params["Qos"] == "Guaranteed" and params["Priority"] == str(priority)
    assert "MaxWaitDuration" not in params and "MaxRunningDuration" not in params
    spec = params["TaskSpecs"]["t0"]
    assert spec["MaxWaitDuration"] == "120s" and spec["MaxRunningDuration"] == "86400s"
    assert not {"UsePrivateMachine", "Qos", "Priority"} & spec.keys()
    assert ("GPU" not in spec) if sku else spec["GPU"] == "0"
    validate(operation("job", "CreateJob"), params)


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("use_private_machine", "true", "boolean"),
        ("priority", 0, "1 to 9"),
        ("priority", 10, "1 to 9"),
        ("priority", True, "1 to 9"),
        ("priority", "5", "1 to 9"),
        ("qos", "", "nonempty"),
        ("qos", " Guaranteed ", "whitespace"),
        ("qos", 1, "nonempty"),
        ("max_wait_duration", "0s", "--max-wait-duration"),
        ("max_wait_duration", "-1m", "--max-wait-duration"),
        ("max_running_duration", "1.5m", "--max-running-duration"),
        ("max_running_duration", "10", "--max-running-duration"),
        ("max_running_duration", 10, "--max-running-duration"),
    ],
)
def test_invalid_job_scheduling_is_rejected_locally(field, value, message):
    with pytest.raises(InputError, match=message):
        create_params("job", **shortcut_kwargs(), **{field: value})


@pytest.mark.parametrize(
    "flags",
    [
        ["--use-private-machine"],
        ["--no-use-private-machine"],
        ["--qos", "Guaranteed"],
        ["--priority", "5"],
        ["--max-wait-duration", "1m"],
        ["--max-running-duration", "1m"],
    ],
)
@pytest.mark.parametrize("invocation", [["job", "create", "--file", "-"], ["workspace", "create"]])
def test_scheduling_options_are_job_shortcut_only(monkeypatch, flags, invocation):
    def forbidden(_):
        pytest.fail("Invalid invocation must not create a client")

    monkeypatch.setattr("yicloud.commands.workloads.client_for", forbidden)
    result = CliRunner().invoke(main, ["--json", *invocation, *flags], input="{}")
    assert result.exit_code == 1
    error = json.loads(result.stderr)["error"]
    assert error["kind"] == "input"
    assert (
        "mutually exclusive" in error["message"]
        if invocation[0] == "job"
        else "No such option" in error["message"]
    )


def test_actual_cli_explicit_job_scheduling(tmp_path):
    env = dict(os.environ, YICLOUD_PUBLIC_KEY="fixture-public", YICLOUD_SECRET_KEY="fixture-secret")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "yicloud",
            "--json",
            "job",
            "create",
            "--dry-run",
            "--name",
            "fixture",
            "--project",
            "p",
            "--zone",
            "z",
            "--image",
            "image",
            "--quota-group",
            "quota",
            "--cpu",
            "1",
            "--memory",
            "8Gi",
            "--command",
            "true",
            "--no-use-private-machine",
            "--qos",
            "Guaranteed",
            "--priority",
            "5",
            "--max-wait-duration",
            "2m",
            "--max-running-duration",
            "60s",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    body = json.loads(result.stdout)["data"]["body"]
    assert body["UsePrivateMachine"] is False and body["Priority"] == "5"
    assert body["Qos"] == "Guaranteed"
    task = body["TaskSpecs"]["t0"]
    assert task["GPU"] == "0"
    assert task["MaxWaitDuration"] == "120s" and task["MaxRunningDuration"] == "60s"
