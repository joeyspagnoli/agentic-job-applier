# LLM Provider Abstraction Subsystem (`src/providers/`)

## Purpose

The provider abstraction was designed to decouple the pipeline from a single LLM vendor, enabling multi-provider BYOK (bring-your-own-key) support. The factory and protocol (`AIProvider`) allow stages (gate, tailor, review, apply finisher) to invoke language models through a unified interface without SDK coupling.

**Current state:** OpenAI BYOK only. Post-issue-61 cleanup removed scaffolding for Anthropic, Gemini, and Codex device-auth providers.

**Intended state (issue #35):** Anthropic, Gemini, OpenRouter, and Codex providers wired alongside OpenAI, persisted through settings UI.

## Factory Architecture

**File:** `src/providers/factory.py` (92 lines)

The factory (`build_provider(config: ProviderConfig) -> AIProvider`) is the single entry point for provider construction. It accepts a `ProviderConfig` object and returns a configured `AIProvider` instance.

**Function signatures:**

- `build_provider(config: ProviderConfig) -> AIProvider` — Takes explicit config; raises `ProviderAuthError` if `api_key` is missing; raises `ProviderError` for unsupported providers.
- `build_provider_from_env() -> AIProvider` — Convenience entry point reading `OPENAI_API_KEY` from the environment; used by scripts that don't thread config objects.

**Return type:** Both functions return an `OpenAIProvider` instance (never a polymorphic subclass). The factory does not instantiate Anthropic or Gemini providers; those branches would be added under issue #35.

**Provider routing (current):**
- `ProviderType.OPENAI` → `OpenAIProvider(api_key, base_url=None, default_model="gpt-5-mini", provider_type=OPENAI)`
- `ProviderType.OPENROUTER` → `OpenAIProvider(api_key, base_url="https://openrouter.ai/api/v1", default_model="openai/gpt-5-mini", provider_type=OPENROUTER)`
- All other types → `ProviderError` with message "Anthropic, Gemini, and Codex providers were removed."

**Error handling:** Exceptions (`ProviderAuthError`, `ProviderError`) carry a `provider` field so callers can log which backend failed.

## Supported Providers

### Live (OpenAI + OpenRouter)

**File:** `src/providers/openai_provider.py` (314 lines)

`OpenAIProvider` is the only concrete implementation. It sends requests via the `openai` Python SDK (v2.38.0) and is compatible with any OpenAI-compatible endpoint (e.g., Ollama, LM Studio). The `base_url` parameter enables OpenRouter routing without subclassing.

**Authentication:** API key supplied at construction; validated in `validate_credentials()` by calling `client.models.list()`.

**Default models:**
- OpenAI proper: `gpt-5-mini`
- OpenRouter: `openai/gpt-5-mini`

**Protocol implementation:**
- `provider_type` property returns the enum value.
- `is_authenticated` property checks `bool(self._api_key)`.
- `async complete(request: CompletionRequest) -> CompletionResponse` — Sends a chat completion to the endpoint and unpacks the response into the canonical `CompletionResponse` object.
- `compute_cost(model: str, usage: TokenUsage) -> CostBreakdown` — Delegates cost calculation to `litellm.cost_per_token()`.
- `async validate_credentials() -> bool` — Tests the key by listing models.

### Scaffolded (removed)

**Status:** Post-issue-61 cleanup removed scaffolding. Per `factory.py` docstring (lines 3-7):
> Anthropic, Gemini, and Codex device-auth providers were removed in the post-issue-61 cleanup. The pipeline now resolves to a single OpenAI provider built from `OPENAI_API_KEY`, keeping a thin abstraction so the gate / tailor / review stages can still depend on the `AIProvider` protocol without re-importing the OpenAI SDK directly.

No per-provider modules exist for Anthropic, Gemini, OpenRouter-specific logic, or Codex. The types and protocol remain in `src/providers/types.py` to support future implementations.

## Where Each Stage Calls LLMs

### Gate (apply/skip decision)

**File:** `src/agents/root_apply_decider/unified_runtime.py` (101 lines)

The gate stage uses the unified provider abstraction and is provider-agnostic.

- **Entry point:** `run_gate_with_provider(provider: AIProvider, job: Mapping) -> GateRunOutcome` (lines 49–100)
- **Provider:** Accepts any `AIProvider` instance; does not hardcode OpenAI.
- **Call shape:** Builds a `CompletionRequest` with system and user messages, calls `provider.complete(request)`, and parses the response into `ApplyDecision.APPLY` or `ApplyDecision.SKIP`.
- **Cost recording:** Returns a `GateRunOutcome` bundling the parsed decision with the raw `CompletionResponse` so the caller can persist cost via `record_llm_call_cost()` without re-invoking the provider.

**SDK:** The provider abstraction; caller never imports OpenAI SDK directly.

### Tailor & Trim

**File:** `src/agents/resume_tailor/llm.py` (392 lines)

**Hardcoded OpenAI.** This stage is NOT provider-agnostic—it directly imports and instantiates `OpenAI` from the `openai` SDK and uses `instructor` for response validation.

- **Entry points:**
  - `call_tailor(user_message: str) -> LlmCallResult[TailorOutput]` (lines 330–348)
  - `call_trim(user_message: str) -> LlmCallResult[TailorOutput]` (lines 351–369)

- **Model resolution:** 
  - `get_tailor_model_name()` checks `RESUME_TAILOR_MODEL` env var; defaults to `"openai/gpt-5.4"`.
  - `get_reviewer_model_name()` checks `RESUME_REVIEWER_MODEL` env var; defaults to `"openai/gpt-5-mini"`.

- **Client construction:** `_build_client(qualified_model: str)` (lines 152–184) parses the model identifier and branches on the provider part:
  - If provider is `"openai"`: Instantiates `OpenAI()` client and wraps it with `instructor.from_openai(..., mode=instructor.Mode.RESPONSES_TOOLS)` (line 177–179).
  - Otherwise: Raises `ValueError` stating the provider is unsupported.

- **Cost computation:** Uses `_get_cost_provider()` which constructs an `OpenAIProvider` lazily for cost math only (lines 50–62). The provider's `compute_cost()` method is called with the model name and token usage (line 278).

- **SDK:** Direct imports of `openai.OpenAI` and `instructor`; no provider abstraction.

### Reviewer (scoring base vs. tailored variants)

**File:** `src/agents/resume_tailor/llm.py` (lines 372–391)

Same pattern as tailor/trim:

- **Entry point:** `call_reviewer(user_message: str) -> LlmCallResult[ReviewerOutput]` (lines 372–391)
- **Hardcoded OpenAI:** Calls `_structured_call(qualified_model=get_reviewer_model_name(), ...)` which routes to the same `_build_client()` logic as tailor.
- **Model:** Defaults to `"openai/gpt-5-mini"`.
- **Cost:** Computed via the lazy `_get_cost_provider()` OpenAIProvider instance.

### Apply Finisher (form field completion)

**File:** `src/agents/apply_finisher/runner.py` (partial; see cost logic at lines 132–170)

The apply finisher does NOT call an LLM; it is a browser-automation stub. Cost tracking for this stage is a synthetic zero-cost row tagged `cost_source="internal"` (see `record_apply_browser_stub()` in `src/utils/cost_tracking.py`).

However, cost computation for other stages uses the same pattern as tailor—`litellm.cost_per_token()` is called directly with a model name and token counts. This mirrors the provider abstraction's cost math but doesn't use the provider interface.

## Cost Tracking

### Per-Call Computation

**File:** `src/providers/openai_provider.py`, lines 182–250 (`compute_cost` method)

The `OpenAIProvider.compute_cost()` method:

1. Imports `litellm.cost_per_token` at runtime (lines 202–208).
2. Computes billable prompt tokens by subtracting cached tokens: `billable_prompt = max(prompt_tokens - cached_input_tokens, 0)` (lines 210–212).
3. Calls `cost_per_token(model=model, prompt_tokens=billable_prompt, completion_tokens=completion_tokens)` (lines 215–219).
4. If cached tokens are present, calls `cost_per_token` again for the cached portion and applies the `OPENAI_CACHED_INPUT_DISCOUNT = 0.5` multiplier (lines 228–238).
5. Returns a `CostBreakdown` with `source="computed"` on success, or `source="unknown"` and zero costs if litellm raises an exception or is not installed.

**LiteLLM integration:**
- Respects `LITELLM_LOCAL_MODEL_COST_MAP=true` to force local-only pricing tables (avoids network lookup).
- Ships bundled pricing for OpenAI gpt-5 family and other major providers.
- Unknown models yield `source="unknown"` and zero costs (no hard failures).

### Central Recording

**File:** `src/utils/cost_tracking.py`, lines 36–100 (`record_llm_call_cost`)

This is the single write path for all billed LLM calls. It accepts a `CompletionResponse` and persists its `cost` field alongside metadata:

```python
async def record_llm_call_cost(
    *,
    db: DatabaseManager,
    stage: str,
    run_id: str | None,
    phase: str | None,
    response: CompletionResponse,
    job_hash: str | None = None,
    extra_metadata: Mapping[str, Any] | None = None,
) -> None:
```

- **Metadata captured:** `provider`, `model`, `phase`, `prompt_tokens`, `completion_tokens`, `cached_input_tokens`, `reasoning_tokens`, `cost_source`, and per-component costs (input_cost_usd, output_cost_usd, cached_input_cost_usd).
- **Persistence:** Writes to the `cost_events` table in SQLite.

### Database Schema

**File:** `src/database/_mixins/costs.py` (387 lines)

The `cost_events` table stores per-call telemetry:

```sql
CREATE TABLE cost_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stage TEXT NOT NULL,  -- GATE, TAILOR, REVIEW, APPLY, DISCOVERY
    job_hash TEXT,
    run_id TEXT,
    cost_usd REAL NOT NULL,
    metadata_json TEXT,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    provider TEXT NOT NULL DEFAULT 'unknown',
    model TEXT NOT NULL DEFAULT 'unknown',
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    cached_input_tokens INTEGER NOT NULL DEFAULT 0,
    reasoning_tokens INTEGER NOT NULL DEFAULT 0,
    phase TEXT,
    cost_source TEXT NOT NULL DEFAULT 'unknown'
    -- Constraints and indexes omitted for brevity
);
```

Issue #59 added the per-model columns (provider, model, prompt_tokens, etc.) via PRAGMA-guarded ALTER TABLE migrations so old databases pick them up on startup.

**Usage:** Dashboard and settings UI call `get_budget_settings()` to compute monthly spend rollup:

```python
async def get_budget_settings(self) -> JSONObject:
    # Sums cost_usd for the current month, returns {monthly_budget_usd, spent_usd, remaining_usd, utilization_pct}
```

## API-Key Persistence

### Storage Location

**File:** `api/services/env_keys.py` (141 lines)

API keys are persisted in the project `.env` file as environment variables. No encryption at rest; keys are plaintext on disk.

- **OPENAI_API_KEY** for OpenAI BYOK (currently the only supported mode).
- **ANTHROPIC_API_KEY**, **GOOGLE_API_KEY** (placeholders in the codebase but not functional for authentication).

### Read/Write API

Three low-level helpers in `env_keys.py`:

- `_read_env_pairs() -> list[tuple[str, str]]` — Parses `.env` line-by-line, preserving comments and order (lines 24–48).
- `_write_env_key(key_name: str, key_value: str)` — Upserts a KEY=VALUE line into `.env` and reloads `os.environ` (lines 74–100).
- `_delete_env_key(key_name: str)` — Removes a key from `.env` (lines 103–118).

**Placeholder detection:** `ENV_KEY_PLACEHOLDER_VALUES = {"", "your_openai_api_key_here", ...}` (lines 14–21) so the API does not report a placeholder as "configured."

### API Endpoint

**File:** `api/routers/settings_api_keys.py` (136 lines)

- `GET /api/settings/api-keys` — Returns `{ok: true, keys: [{name, configured}, ...]}` for all allowed keys (lines 19–31).
- `PUT /api/settings/api-keys/{key_name}` — Upserts a key value (lines 34–59).
- `DELETE /api/settings/api-keys/{key_name}` — Revokes a key (lines 62–83).

**Validation:** `key_name` must be in `api/config.py::ALLOWED_API_KEY_NAMES` (a hardcoded frozenset).

### Encryption

**Status:** NOT implemented. Keys are stored in plaintext in `.env`. The `cryptography` library (v46.0.6) is a dependency but is NOT used by the provider or key-storage modules. No encryption/decryption logic exists in the codebase.

## Provider Switching UI

### Settings Endpoint

**File:** `api/routers/settings_provider.py` (169 lines)

- `POST /api/settings/provider` — Accepts `{provider_type: str, api_key: str}` and persists the key via `_write_env_key("OPENAI_API_KEY", api_key)` (lines 69–109).

**Validation:**
- `provider_type` must be `"openai"` (lines 86–93).
- If `provider_type` is not `"openai"`, returns HTTP 400 with `code="UNSUPPORTED_PROVIDER"` and message "Only OpenAI is supported in this release. Track issue #35 for wider BYOK support."
- Explicitly rejects `"anthropic"`, `"gemini"`, `"openrouter"`, `"codex"` (lines 33–40).

**Future:** When issue #35 is resolved, this endpoint would accept multiple provider types, validate the key against the corresponding SDK, and store both the `provider_type` and `api_key` in a persistent config table (instead of env vars).

### Onboarding Status

- `GET /api/settings/onboarding-status` — Returns whether profile and resume steps are complete (lines 112–147). Does not surface provider selection UI status.

## Risks and Gotchas

### Hardcoded OpenAI in Tailor & Review (Issue #35)

The tailor and review stages bypass the provider abstraction and directly instantiate `OpenAI()` from the `openai` SDK. This means:

- **No env var override:** Swapping to Anthropic would require manual code changes in `src/agents/resume_tailor/llm.py`.
- **Instructor coupling:** Tailor/review use `instructor` for response validation, which has native OpenAI support but would require conditional logic for Anthropic (e.g., `instructor.from_anthropic(...)`).
- **Cost math duplication:** Tailor computes cost via an isolated `_get_cost_provider()` OpenAIProvider instance, not through the pipeline's central provider. If Anthropic were to be adopted, the cache-discount math (different from OpenAI's 50%) would need to be added to `AnthropicProvider.compute_cost()`.

**Migration path:** To add Anthropic support:
1. Create `src/providers/anthropic_provider.py` implementing the `AIProvider` protocol.
2. Add an Anthropic branch in `_build_client()` that calls `instructor.from_anthropic(...)`.
3. Implement `AnthropicProvider.compute_cost()` with Anthropic's cache-read discount (10% per Anthropic docs, different from OpenAI's 50%).
4. Add Anthropic to the factory's routing.
5. Add Anthropic to the provider settings API (remove from UNSUPPORTED_PROVIDERS).

### Retry and Error Semantics

**OpenAI-specific retries:** `OpenAIProvider.complete()` raises specific exceptions (`AuthenticationError`, `RateLimitError`, `APIConnectionError`, `APIError`) which are mapped to provider-agnostic exceptions (`ProviderAuthError`, `ProviderRateLimitError`, `ProviderConnectionError`, `ProviderResponseError`) (lines 136–157).

`ProviderRateLimitError` carries an optional `retry_after_seconds` field (extracted from `exc.retry_after` when available). Callers can inspect this to implement exponential backoff.

**No automatic retries:** The provider does NOT retry; all retries are caller-driven. The instructor library implements its own retries (`INSTRUCTOR_MAX_RETRIES = 3`) for validation failures, but not for transient network errors.

### Cost Source Semantics

`CostBreakdown.source` can be:
- `"provider"` — Cost reported directly by the provider (e.g., OpenAI's response headers; not currently used).
- `"computed"` — Cost derived from token counts via `litellm.cost_per_token()`.
- `"internal"` — Cost is synthetic (e.g., apply finisher's zero cost).
- `"unknown"` — Pricing for the model is not available.

The dashboard and budget guards use `source` to decide how to handle the row. Unknown costs do not fail the pipeline but may be logged as warnings.

### Model Identifier Conventions

The tailor/review stages use fully qualified `provider/model` identifiers (e.g., `"openai/gpt-5.4"`, `"openai/gpt-5-mini"`). The factory and OpenAIProvider accept bare model names (e.g., `"gpt-5.4-mini"` for OpenAI or `"openai/gpt-5-mini"` for OpenRouter).

**Inconsistency:** Tailor hardcodes `"openai/gpt-5.4"` but the factory defaults to `"gpt-5-mini"` (without the provider prefix). This works because the tailor stage always uses OpenAI, but it creates friction for future multi-provider support.

### LiteLLM Pricing Table Staleness

`litellm.cost_per_token()` is called at runtime and relies on a bundled pricing table. If a model is new or a price changed, the table may be out-of-date. Callers can set `LITELLM_LOCAL_MODEL_COST_MAP=true` to skip network lookups and rely entirely on the bundled table (reducing latency but potentially missing updates).

There is no mechanism to refresh the pricing table without upgrading litellm itself. Custom model pricing can be registered via `src/utils/llm_pricing.py` (for internal/test models).

## Summary

The LLM provider abstraction cleanly separates gate/apply from the OpenAI SDK via the `AIProvider` protocol and factory. Cost accounting is provider-owned (each provider computes its own `CostBreakdown`), centralizing pricing logic so the recorder stays vendor-agnostic. However, tailor and review stages hardcode OpenAI + instructor, bypassing the abstraction entirely. Switching to Anthropic would require adding an `AnthropicProvider` class and conditional instructor client construction. API-key persistence uses unencrypted plaintext in `.env`; no encryption-at-rest is implemented. The provider settings UI currently rejects all non-OpenAI requests; supporting additional providers requires lifting that restriction, persisting provider type in the database, and threading it through the pipeline.
