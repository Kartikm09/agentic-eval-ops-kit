"""Shared data models for scenario evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Event:
    type: str
    actor: str = "assistant"
    content: str = ""
    name: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Event":
        return cls(
            type=str(raw.get("type", "message")),
            actor=str(raw.get("actor", "assistant")),
            content=str(raw.get("content", "")),
            name=str(raw.get("name", "")),
            metadata=dict(raw.get("metadata", {})),
        )

    def searchable_text(self) -> str:
        return " ".join([self.type, self.actor, self.name, self.content]).strip()


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    domain: str
    objective: str
    events: tuple[Event, ...]
    must_include: tuple[str, ...] = ()
    must_not_include: tuple[str, ...] = ()
    required_tools: tuple[str, ...] = ()
    forbidden_tools: tuple[str, ...] = ()
    required_sequence: tuple[str, ...] = ()
    expected_fields: tuple[str, ...] = ()
    rubric: tuple[dict[str, Any], ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Scenario":
        return cls(
            scenario_id=str(raw["scenario_id"]),
            domain=str(raw.get("domain", "general")),
            objective=str(raw.get("objective", "")),
            events=tuple(Event.from_dict(item) for item in raw.get("events", [])),
            must_include=tuple(map(str, raw.get("must_include", []))),
            must_not_include=tuple(map(str, raw.get("must_not_include", []))),
            required_tools=tuple(map(str, raw.get("required_tools", []))),
            forbidden_tools=tuple(map(str, raw.get("forbidden_tools", []))),
            required_sequence=tuple(map(str, raw.get("required_sequence", []))),
            expected_fields=tuple(map(str, raw.get("expected_fields", []))),
            rubric=tuple(dict(item) for item in raw.get("rubric", [])),
            metadata=dict(raw.get("metadata", {})),
        )

    def transcript_text(self) -> str:
        return "\n".join(event.searchable_text() for event in self.events)

    def tool_names(self) -> tuple[str, ...]:
        return tuple(event.name for event in self.events if event.type == "tool_call" and event.name)


@dataclass(frozen=True)
class CheckResult:
    check_id: str
    passed: bool
    points: float
    possible: float
    severity: str
    message: str


@dataclass(frozen=True)
class Evaluation:
    scenario_id: str
    domain: str
    score: float
    decision: str
    checks: tuple[CheckResult, ...]

    @property
    def critical_issues(self) -> tuple[CheckResult, ...]:
        return tuple(check for check in self.checks if not check.passed and check.severity == "critical")

    @property
    def warnings(self) -> tuple[CheckResult, ...]:
        return tuple(check for check in self.checks if not check.passed and check.severity == "warning")

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "domain": self.domain,
            "score": round(self.score, 4),
            "decision": self.decision,
            "critical_issues": len(self.critical_issues),
            "warnings": len(self.warnings),
            "checks": [check.__dict__ for check in self.checks],
        }
