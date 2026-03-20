from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, ConfigDict


class ParsedAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["assign_item", "split_item", "exclude_item", "assign_extra_all", "done"]
    item_match: str | None = None
    participants: list[str] = Field(default_factory=list)
    ratios: list[Decimal] = Field(default_factory=list)
    extra_kind: Literal["tax", "service_charge", "tips"] | None = None


class ParsedIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actions: list[ParsedAction] = Field(default_factory=list)


class ParticipantTotal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    participant: str
    amount: Decimal


class SplitSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    currency: str
    totals: list[ParticipantTotal]
    unassigned_items: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)