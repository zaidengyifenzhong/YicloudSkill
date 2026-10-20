class YicloudError(Exception):
    kind = "platform"

    def __init__(
        self,
        message,
        *,
        request_id=None,
        code=None,
        outcome_unknown=False,
        http_status=None,
        hints=(),
    ):
        super().__init__(message)
        self.request_id = request_id
        self.code = code
        self.outcome_unknown = outcome_unknown
        self.http_status = http_status
        self.hints = list(hints)

    def as_dict(self):
        result = {
            "kind": self.kind,
            "message": str(self),
            "code": self.code,
            "request_id": self.request_id,
            "outcome_unknown": self.outcome_unknown,
            "http_status": self.http_status,
        }
        if self.hints:
            result["hints"] = self.hints
        return result


class ConfigurationError(YicloudError):
    kind = "configuration"


class InputError(YicloudError):
    kind = "input"


class AuthenticationError(YicloudError):
    kind = "authentication"


class NetworkError(YicloudError):
    kind = "network"


class UnsupportedProtocol(YicloudError):
    kind = "unsupported_protocol"


class OperationInterrupted(YicloudError):
    kind = "interrupted"


class WaitError(YicloudError):
    def __init__(self, message, *, last_status, observed_at, request_id=None):
        super().__init__(message, request_id=request_id)
        self.last_status = last_status
        self.observed_at = observed_at

    def as_dict(self):
        return dict(super().as_dict(), last_status=self.last_status, observed_at=self.observed_at)


class WaitTimeout(WaitError):
    kind = "wait_timeout"


class RemoteFailed(WaitError):
    kind = "remote_failed"


class UnknownState(WaitError):
    kind = "unknown_state"
