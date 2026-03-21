
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ParsedParticipants(BaseModel):
    model_config = ConfigDict(extra="forbid")
    participants: list[str] = Field(default_factory=list)


class ParsedAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[
        "assign_item",
        "split_item",
        "assign_by_category",
        "split_by_category",
        "assign_remaining",
        "exclude_item",
        "done",
    ]
    item_match: str | None = None
    category: str | None = None
    participants: list[str] = Field(default_factory=list)
    ratios: list[Decimal] = Field(default_factory=list)
    extra_kind: str | None = None


class ParsedIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actions: list[ParsedAction] = Field(default_factory=list)
    clarification_question: str | None = None
    needs_clarification: bool = False


class ParticipantBreakdown(BaseModel):
    model_config = ConfigDict(extra="forbid")

    participant: str
    amount: Decimal
    items: list[str] = Field(default_factory=list)


class SplitSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    currency: str
    totals: list[ParticipantBreakdown]
    unassigned_items: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
