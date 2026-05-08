"""Cross-cutting pydantic request payload models for the API.

These models are shared by multiple routers (human review, budget, settings
files, API keys, service tier, AI provider, manual job import). Domain-specific
candidate-profile payloads live alongside in `api.schemas.candidate`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field


class ReviewerActionRequest(BaseModel):
    """Request payload for human-review action endpoints.

    Attributes:
        reviewer_notes: Optional note to persist with the reviewer action.
    """

    reviewer_notes: str | None = Field(
        default=None,
        description="Optional note to persist with this reviewer action.",
    )


class BudgetUpdateRequest(BaseModel):
    """Request payload for monthly budget updates.

    Attributes:
        monthly_budget_usd: New non-negative budget in USD.
    """

    monthly_budget_usd: float = Field(
        ge=0,
        description="New monthly budget limit in USD.",
    )


class YamlTextUpdateRequest(BaseModel):
    """Request payload for raw YAML text save operations.

    Attributes:
        yaml_text: UTF-8 YAML content to validate and persist.
    """

    yaml_text: str = Field(
        min_length=1,
        description="UTF-8 YAML content to validate and persist.",
    )


class YamlPayload(BaseModel):
    """Payload for writing a YAML config file."""

    yaml_text: str
    model_config = ConfigDict(extra="forbid")


class ApiKeyUpsertRequest(BaseModel):
    """Request payload for adding or replacing one API key secret.

    Attributes:
        value: Raw secret value supplied by the user.
    """

    value: str = Field(min_length=1, description="Secret value for the API key.")
    model_config = ConfigDict(extra="forbid")


class ServiceTierUpdateRequest(BaseModel):
    """Request payload for updating the active service tier.

    Attributes:
        tier: One of 'base', 'latex', or 'full'.
    """

    tier: str = Field(description="Active service tier identifier.")
    model_config = ConfigDict(extra="forbid")


class ProviderConfigRequest(BaseModel):
    """Payload for configuring the active AI provider."""

    mode: str = Field(description="'codex' or 'byok'")
    provider_type: str = Field(default="openai", description="openai, anthropic, gemini, openrouter")
    api_key: str | None = Field(default=None, description="API key for BYOK mode")
    base_url: str | None = Field(default=None, description="Custom endpoint URL")
    default_model: str | None = Field(default=None, description="Default model override")


class JobImportRequest(BaseModel):
    """Request body for manual job import."""

    model_config = ConfigDict(strict=True)

    mode: Literal["url", "text"]
    url: str | None = None
    company: str | None = None
    title: str | None = None
    location: str | None = None
    description: str | None = None
