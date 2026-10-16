"""Dependency-free reference semantics; not a production service."""
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List


class Lifecycle(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    BLOCKED = "blocked"
    ARCHIVED = "archived"
    SUPERSEDED = "superseded"


class ConflictError(Exception):
    """A conflicting identity or stale write was detected."""


class AuthorizationError(Exception):
    """The requested operation is not authorized."""


@dataclass(frozen=True)
class Version:
    number: int
    content: dict
    actor: str


@dataclass
class Context:
    context_id: str
    owner: str
    status: Lifecycle = Lifecycle.DRAFT
    current_version: int = 1
    versions: Dict[int, Version] = field(default_factory=dict)
    events: List[dict] = field(default_factory=list)

    def __post_init__(self):
        if not self.versions:
            self.versions[1] = Version(1, {}, self.owner)
            self.events.append({
                "event_id": f"{self.context_id}:v1",
                "event_type": "context.created",
                "context_id": self.context_id,
                "result_version": 1,
            })


class ReferenceStore:
    """Models compare-and-swap, immutable history, and an independent approval gate."""

    def __init__(self):
        self.contexts: Dict[str, Context] = {}
        self.approvals: Dict[str, dict] = {}
        self.external_effects: List[dict] = []

    def create(self, context_id: str, owner: str) -> Context:
        if context_id in self.contexts:
            raise ConflictError("context_id already exists")
        ctx = Context(context_id=context_id, owner=owner)
        self.contexts[context_id] = ctx
        return ctx

    def commit(self, context_id: str, actor: str, expected_version: int,
               content: dict, *, can_write: bool) -> Version:
        if not can_write:
            raise AuthorizationError("write permission denied")
        ctx = self.contexts[context_id]
        if expected_version != ctx.current_version:
            raise ConflictError("stale base version")
        new_number = ctx.current_version + 1
        frozen_content = _deep_copy_json(content)
        version = Version(new_number, frozen_content, actor)
        ctx.versions[new_number] = version
        ctx.current_version = new_number
        ctx.events.append({
            "event_id": f"{context_id}:v{new_number}",
            "event_type": "context.version_committed",
            "context_id": context_id,
            "base_version": expected_version,
            "result_version": new_number,
            "actor": actor,
        })
        return version

    def approve(self, operation_id: str, proposer: str, approver: str,
                *, authorized_approver: bool, separation_required: bool = True):
        if not authorized_approver:
            raise AuthorizationError("approver lacks approval permission")
        if separation_required and proposer == approver:
            raise AuthorizationError("self-approval prohibited")
        self.approvals[operation_id] = {
            "proposer": proposer, "approver": approver, "status": "approved"
        }

    def execute_external(self, operation_id: str, actor: str,
                         *, currently_authorized: bool):
        approval = self.approvals.get(operation_id)
        if not currently_authorized or not approval or approval["status"] != "approved":
            raise AuthorizationError(
                "explicit valid approval and current authorization required"
            )
        self.external_effects.append({"operation_id": operation_id, "actor": actor})


def _deep_copy_json(value):
    if isinstance(value, dict):
        return {k: _deep_copy_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_deep_copy_json(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError("content must be JSON-compatible")
