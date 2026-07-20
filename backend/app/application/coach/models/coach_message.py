from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class CoachMessage:

    greeting: str

    planned_lines: list[str] = field(
        default_factory=list,
    )

    executed_lines: list[str] = field(
        default_factory=list,
    )

    interval_lines: list[str] = field(
        default_factory=list,
    )

    block_lines: list[str] = field(
        default_factory=list,
    )

    splits_lines: list[str] = field(
        default_factory=list,
    )

    positives: list[str] = field(
        default_factory=list,
    )

    improvements: list[str] = field(
        default_factory=list,
    )

    history: list[str] = field(
        default_factory=list,
    )

    recovery: list[str] = field(
        default_factory=list,
    )

    next_training: list[str] = field(
        default_factory=list,
    )

    closing: str = ""
