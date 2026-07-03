from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class FindingSeverity(str, Enum):

    POSITIVE = "POSITIVE"

    NEUTRAL = "NEUTRAL"

    ATTENTION = "ATTENTION"


@dataclass(slots=True, frozen=True)
class Finding:

    code: str

    severity: FindingSeverity

    params: dict = field(
        default_factory=dict,
    )
