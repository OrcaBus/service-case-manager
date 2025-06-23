from enum import Enum
from typing import List


class Status(Enum):
    DRAFT = "DRAFT", ['DRAFT', 'INITIAL', 'CREATED']
    READY = "READY", ['READY']
    RUNNING = "RUNNING", ['RUNNING', 'IN_PROGRESS']
    SUCCEEDED = "SUCCEEDED", ['SUCCEEDED', 'SUCCESS']
    FAILED = "FAILED", ['FAILED', 'FAILURE', 'FAIL']
    ABORTED = "ABORTED", ['ABORTED', 'CANCELLED', 'CANCELED']
    RESOLVED = "RESOLVED", ['RESOLVED']

    def __init__(self, convention: str, aliases: List[str]):
        self.convention = convention
        self.aliases = aliases

    def __str__(self):
        return self.convention

    @staticmethod
    def get_convention(status: str):
        # enforce upper case convention
        status = status.upper()
        status = status.replace("-", "_")
        # TODO: handle other characters?
        for s in Status:
            if status in s.aliases:
                return s.convention

        # retain all uncontrolled states
        return status

    @staticmethod
    def is_supported(status: str) -> bool:
        # enforce upper case convention
        status = status.upper()
        for s in Status:
            if status in s.aliases:
                return True
        return False

    @staticmethod
    def is_terminal(status: str) -> bool:
        # enforce upper case convention
        status = status.upper()
        for s in [Status.SUCCEEDED, Status.FAILED, Status.ABORTED]:
            if status in s.aliases:
                return True
        return False

    @staticmethod
    def is_draft(status: str) -> bool:
        # enforce upper case convention
        status = status.upper()
        return status in Status.DRAFT.aliases

    @staticmethod
    def is_running(status: str) -> bool:
        # enforce upper case convention
        status = status.upper()
        return status in Status.RUNNING.aliases

    @staticmethod
    def is_ready(status: str) -> bool:
        # enforce upper case convention
        status = status.upper()
        return status in Status.READY.aliases

    @staticmethod
    def is_resolved(status: str) -> bool:
        # enforce upper case convention
        status = status.upper()
        return status in Status.RESOLVED.aliases
