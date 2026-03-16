"""Schema definitions for the pi-mono resume review workflow.

Purpose:
    Define strict invocation, report, and run-result contracts used by the
    autonomous post-tailor review stage.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel
from pydantic import Field
from pydantic import field_validator
from pydantic import model_validator

DEFAULT_REVIEW_PI_TIMEOUT_SECONDS = 14_400
DEFAULT_REVIEW_MAX_ITERATIONS = 2


class ReviewVerdict(str, Enum):
    """Represent the final review decision chosen by the review agent.

    Purpose:
        Keep review outcomes constrained to the four pipeline verdict values.
    """

    PASS = "PASS"
    TAILORED = "TAILORED"
    BASE = "BASE"
    FAIL = "FAIL"


class ReviewProfileLabel(str, Enum):
    """Represent high-level candidate-versus-base layout profile labels.

    Purpose:
        Provide normalized compare-to-base labels the agent can reason about
        without parsing raw metric deltas.
    """

    SPARSER_THAN_BASE = "SPARSER_THAN_BASE"
    DENSER_THAN_BASE = "DENSER_THAN_BASE"
    MARGIN_IMBALANCE = "MARGIN_IMBALANCE"
    SIMILAR_TO_BASE = "SIMILAR_TO_BASE"


class PdfGeometryMetrics(BaseModel):
    """Store deterministic first-page geometry and density signals.

    Purpose:
        Standardize metric payloads produced by review geometry tooling so they
        can be compared, persisted, and validated reliably.
    """

    page_count: int
    page_width_pt: float
    page_height_pt: float
    margin_top_pt: float
    margin_bottom_pt: float
    margin_left_pt: float
    margin_right_pt: float
    vert_cov: float
    horiz_cov: float
    ink_ratio: float
    bbox_cov: float
    text_block_count: int


class PdfComparisonResult(BaseModel):
    """Store compare-to-base metrics and relative profile labels.

    Purpose:
        Capture deterministic evidence that the agent can cite when deciding
        whether to keep tailored output or fall back to base output.
    """

    candidate_metrics: PdfGeometryMetrics
    base_metrics: PdfGeometryMetrics
    delta: dict[str, float]
    relative_profile: list[ReviewProfileLabel] = Field(default_factory=list)


class LatexLogAnalysis(BaseModel):
    """Store normalized LaTeX log warning/error counters.

    Purpose:
        Provide structured compile-quality signals for review decisions.
    """

    overfull_count: int
    underfull_count: int
    latex_errors: int
    warnings: int
    has_fatal_error: bool


class PdfTextSignals(BaseModel):
    """Store deterministic text-level signals extracted from a rendered PDF.

    Purpose:
        Give the review agent lightweight textual quality proxies without using
        multimodal inference.
    """

    text_length_chars: int
    word_count: int
    nonempty_line_count: int
    bullet_line_count: int


class ReviewReport(BaseModel):
    """Represent the canonical report artifact written by the review agent.

    Purpose:
        Provide a strict, machine-validated completion handshake between the
        high-agency review agent and the safety-shell runtime.
    """

    verdict: ReviewVerdict
    summary: str
    iteration_count: int = Field(default=0, ge=0, le=10)
    selected_yaml_path: str | None = None
    selected_tex_path: str | None = None
    selected_pdf_path: str | None = None
    candidate_geometry: PdfGeometryMetrics | None = None
    base_geometry: PdfGeometryMetrics | None = None
    comparison: PdfComparisonResult | None = None
    latex_log: LatexLogAnalysis | None = None
    text_signals: PdfTextSignals | None = None
    diagnostics: list[str] = Field(default_factory=list)

    @field_validator("selected_yaml_path", "selected_tex_path", "selected_pdf_path")
    @classmethod
    def _normalize_selected_paths(cls, value: str | None) -> str | None:
        """Normalize optional selected artifact paths.

        Purpose:
            Ensure optional artifact paths are stripped and stored consistently
            before verdict-level validation runs.
        Args:
            value: Candidate artifact path string.
        Output:
            Returns normalized path text, or `None` for blank values.
        Raises:
            None.
        """

        if value is None:
            return None
        normalized_value = value.strip()
        if normalized_value == "":
            return None
        return normalized_value

    @model_validator(mode="after")
    def _validate_selected_artifacts_for_verdict(self) -> "ReviewReport":
        """Enforce required selected artifacts for non-FAIL verdicts.

        Purpose:
            Keep downstream pipeline continuation deterministic by requiring the
            selected artifact references for PASS/TAILORED/BASE outcomes.
        Args:
            self: Candidate review report payload being validated.
        Output:
            Returns `self` when verdict requirements are satisfied.
        Raises:
            ValueError: When required selected artifact fields are missing.
        """

        if self.verdict == ReviewVerdict.FAIL:
            return self

        missing_fields: list[str] = []
        if self.selected_yaml_path is None:
            missing_fields.append("selected_yaml_path")
        if self.selected_tex_path is None:
            missing_fields.append("selected_tex_path")
        if self.selected_pdf_path is None:
            missing_fields.append("selected_pdf_path")

        if missing_fields:
            raise ValueError(
                "Review report requires selected artifact paths for verdict "
                f"{self.verdict.value}: missing {', '.join(missing_fields)}"
            )
        return self


class ReviewJobRef(BaseModel):
    """Represent the job selector passed to the review runtime.

    Purpose:
        Allow review invocations to target one job by hash or numeric ID with
        strict selector validation.
    """

    job_hash: str | None = None
    job_id: int | None = None

    @model_validator(mode="after")
    def _validate_selector(self) -> "ReviewJobRef":
        """Validate that exactly one review selector is configured.

        Purpose:
            Prevent ambiguous database lookups and keep invocation contracts
            deterministic for tooling and workers.
        Args:
            self: Candidate `ReviewJobRef` instance.
        Output:
            Returns `self` when one selector is configured.
        Raises:
            ValueError: When both selectors are set or both are empty.
        """

        has_hash = self.job_hash is not None and self.job_hash.strip() != ""
        has_id = self.job_id is not None
        if has_hash == has_id:
            raise ValueError("Provide exactly one of job_hash or job_id")
        if self.job_hash is not None:
            self.job_hash = self.job_hash.strip()
        return self


class ReviewInvocationContract(BaseModel):
    """Represent the runtime contract for pi-mono resume review runs.

    Purpose:
        Define one explicit invocation payload that gives the review agent full
        tool access while keeping runtime safety boundaries deterministic.
    """

    job_ref: ReviewJobRef
    tailor_run_id: int
    database_path: str
    tailored_yaml_path: str
    tailored_tex_path: str
    tailored_pdf_path: str
    tailored_log_path: str
    base_yaml_path: str
    base_tex_path: str
    base_pdf_path: str
    review_report_path: str
    max_review_iterations: int = DEFAULT_REVIEW_MAX_ITERATIONS
    pi_model: str | None = "openai/gpt-5.1-codex-mini"
    pi_coding_agent_command_argv: list[str] | None = None
    pi_coding_agent_command: str | None = None
    pi_coding_agent_workspace_dir: str | None = None
    pi_coding_agent_timeout_seconds: int = DEFAULT_REVIEW_PI_TIMEOUT_SECONDS
    pi_coding_agent_env_allowlist: list[str] = Field(
        default_factory=lambda: [
            "PATH",
            "HOME",
            "SHELL",
            "LANG",
            "LC_ALL",
            "LC_CTYPE",
            "TERM",
            "TMPDIR",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "GOOGLE_API_KEY",
            "GEMINI_API_KEY",
            "PI_CODING_AGENT_DIR",
            "OPENCLAW_AGENT_DIR",
        ]
    )

    @field_validator("max_review_iterations")
    @classmethod
    def _validate_iteration_budget(cls, value: int) -> int:
        """Validate max iteration budget for agent self-review loops.

        Purpose:
            Prevent invalid negative loop budgets and cap iteration counts to a
            bounded operational range.
        Args:
            value: Candidate max-iteration value.
        Output:
            Returns validated iteration budget.
        Raises:
            ValueError: When value is outside allowed range.
        """

        if value < 0:
            raise ValueError("max_review_iterations must be >= 0")
        if value > 10:
            raise ValueError("max_review_iterations must be <= 10")
        return value

    @field_validator("pi_coding_agent_timeout_seconds")
    @classmethod
    def _validate_pi_timeout(cls, value: int) -> int:
        """Validate timeout configuration for pi-coding-agent subprocess runs.

        Purpose:
            Prevent invalid timeout values that would disable runtime failure
            handling for hung pi-coding-agent executions.
        Args:
            value: Candidate timeout value in seconds.
        Output:
            Returns validated positive timeout value.
        Raises:
            ValueError: When timeout is zero or negative.
        """

        if value <= 0:
            raise ValueError("pi_coding_agent_timeout_seconds must be > 0")
        return value


class ReviewRunResult(BaseModel):
    """Represent the final output payload from one review runtime invocation.

    Purpose:
        Return deterministic success/failure state, validated report payload,
        and captured agent diagnostics for worker persistence.
    """

    success: bool
    failure_reason: str | None = None
    hard_failure: bool = False
    verdict: ReviewVerdict | None = None
    review_report_path: str
    review_report: ReviewReport | None = None
    selected_yaml_path: str | None = None
    selected_tex_path: str | None = None
    selected_pdf_path: str | None = None
    agent_stdout: str | None = None
    agent_stderr: str | None = None


__all__ = [
    "DEFAULT_REVIEW_MAX_ITERATIONS",
    "DEFAULT_REVIEW_PI_TIMEOUT_SECONDS",
    "LatexLogAnalysis",
    "PdfComparisonResult",
    "PdfGeometryMetrics",
    "PdfTextSignals",
    "ReviewInvocationContract",
    "ReviewJobRef",
    "ReviewProfileLabel",
    "ReviewReport",
    "ReviewRunResult",
    "ReviewVerdict",
]
