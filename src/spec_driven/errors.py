class SpecDrivenError(Exception):
    code = "SPEC_DRIVEN_ERROR"

    def __init__(self, message: str, *, retryable: bool = False, remediation: str | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.remediation = remediation


class ConfigError(SpecDrivenError):
    code = "CONFIG_INVALID"


class DiscoveryAmbiguousError(SpecDrivenError):
    code = "DISCOVERY_AMBIGUOUS"


class InvalidEventError(SpecDrivenError):
    code = "EVENT_INVALID"


class GateBlockedError(SpecDrivenError):
    code = "TEST_GATE_BLOCKED"


class StateConflictError(SpecDrivenError):
    code = "STATE_CONFLICT"


class DocumentConflictError(SpecDrivenError):
    code = "DOCUMENT_CONFLICT"


class RecoveryRequiredError(SpecDrivenError):
    code = "RECOVERY_REQUIRED"
