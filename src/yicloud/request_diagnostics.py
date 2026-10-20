"""Conservative hints for observed platform failures; never alter or resend requests."""


def request_failure_hints(service, action, params, error):
    if (
        service != "job"
        or action != "CreateJob"
        or not isinstance(params, dict)
        or error.outcome_unknown
    ):
        return []
    if (
        error.code == 1001000
        and params.get("RestartPolicy") == "Never"
        and params.get("BackoffLimit") == 0
    ):
        return [
            "This request includes RestartPolicy=Never and BackoffLimit=0. A live environment "
            "rejected this combination and accepted the otherwise identical request without "
            "both fields. The responsible field and cross-environment behavior are unconfirmed. "
            "Verify the platform's default retry policy before changing these fields; the CLI "
            "has not changed or retried this request."
        ]
    if error.code == 100 and params.get("QuotaGroup"):
        specs = params.get("TaskSpecs", {})
        if isinstance(specs, dict) and any(
            isinstance(spec, dict)
            and spec.get("CPU")
            and not spec.get("SKUId")
            and "GPU" not in spec
            for spec in specs.values()
        ):
            return [
                "A quota-mode task omits GPU. For an intended CPU-only task, check whether "
                'the platform requires GPU="0", as sent by the console. GPU omission changed '
                "the error in one live environment, but was not isolated as the sole cause. "
                "The CLI has not changed or retried this request."
            ]
    return []
