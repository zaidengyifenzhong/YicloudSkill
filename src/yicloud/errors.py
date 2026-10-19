class YicloudError(Exception):
    kind = "platform"

    def __init__(
        self, message, *, request_id=None, code=None, outcome_unknown=False, http_status=None
    ):
        super().__init__(message)
        self.request_id = request_id
        self.code = code
        self.outcome_unknown = outcome_unknown
        self.http_status = http_status

    def as_dict(self):
        return {
            "kind": self.kind,
            "message": str(self),
            "code": self.code,
            "request_id": self.request_id,
            "outcome_unknown": self.outcome_unknown,
            "http_status": self.http_status,
        }


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
