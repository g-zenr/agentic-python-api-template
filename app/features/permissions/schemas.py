"""Permission feature schemas: the assignable catalog, grant payloads, and effective sets."""

from datetime import datetime
from typing import Any

from pydantic import Field, model_validator

from app.core.constants import GrantEffect
from app.shared.schemas import ApiModel


class GrantIn(ApiModel):
    """One page×action assignment for a user. `conditions` uses the ADR-0019 vocabulary."""

    resource: str = Field(min_length=1, max_length=50)
    action: str = Field(min_length=1, max_length=50)
    effect: GrantEffect = GrantEffect.ALLOW
    conditions: dict[str, Any] | None = None
    expires_at: datetime | None = None


class GrantsIn(ApiModel):
    """Replace-all payload: the full set of grants for the target user."""

    grants: list[GrantIn] = Field(max_length=100)


class GrantOut(ApiModel):
    id: str
    resource: str
    action: str
    effect: str
    conditions: dict[str, Any] | None
    granted_by: str | None
    expires_at: datetime | None
    created_at: datetime


class EffectiveOut(ApiModel):
    """What a user can do: static role baseline + explicit grants + the resulting set."""

    baseline: list[str]
    grants: list[GrantOut]
    effective: list[str]


class CatalogOut(ApiModel):
    """The assignable page × action matrix (drives admin UIs)."""

    resources: dict[str, list[str]]
    permissions: list[str]

    @model_validator(mode="after")
    def _sorted(self) -> "CatalogOut":
        self.resources = {k: sorted(v) for k, v in sorted(self.resources.items())}
        self.permissions = sorted(self.permissions)
        return self
