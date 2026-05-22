"""Renderer-level integration tests for the issue #54 sanitizer.

Purpose:
    Prove the three render sites that route through `latex_safe`
    (experience bullets, project bullets, skills_achievements rows)
    actually emit safe text, and prove the locked render sites
    (personal section, education bullets, listing subheading fields)
    remain unsanitized so user-managed markup keeps its meaning. A
    final skip-if-unavailable test invokes `latexmk` on an adversarial
    document to confirm the whole stack compiles end-to-end.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from src.agents.resume_tailor.renderer import render_resume_tex
from src.agents.resume_tailor.schemas import EducationEntry
from src.agents.resume_tailor.schemas import EducationSection
from src.agents.resume_tailor.schemas import ExperienceListing
from src.agents.resume_tailor.schemas import ExperienceSection
from src.agents.resume_tailor.schemas import PersonalSection
from src.agents.resume_tailor.schemas import ProjectListing
from src.agents.resume_tailor.schemas import ProjectsSection
from src.agents.resume_tailor.schemas import ResumeBullet
from src.agents.resume_tailor.schemas import ResumeContent
from src.agents.resume_tailor.schemas import ResumeLink
from src.agents.resume_tailor.schemas import SkillListing
from src.agents.resume_tailor.schemas import SkillsAchievementsSection


# Adversarial bullets that cover the issue #54 policy rows the renderer
# is most likely to receive from a real LLM call. Each comment names the
# row from the sanitizer policy table.
ADVERSARIAL_EXPERIENCE_BULLETS: tuple[ResumeBullet, ...] = (
    # Issue #54 OP failure case — unknown command in running text.
    ResumeBullet(id="bullet_etc", text="Shipped multi-agent tools th\\ETC."),
    # Bare LaTeX-active characters.
    ResumeBullet(id="bullet_amp", text="Built Q&A pipeline reducing latency by 20%"),
    # Pre-escaped specials must survive unchanged.
    ResumeBullet(id="bullet_preescaped", text="Drove cost down by \\$1{,}200"),
    # Well-formed emphasis must round-trip.
    ResumeBullet(id="bullet_emph", text="Led \\textbf{five engineers} on launch"),
    # Unbalanced emphasis must not break compile.
    ResumeBullet(id="bullet_unbalanced", text="Owned \\textbf{the rollout"),
    # `\\\\` and trailing backslash must be stripped.
    ResumeBullet(id="bullet_doublebs", text="line one\\\\line two"),
)


def _build_adversarial_resume(
    *,
    personal_name: str = "Test Person",
    education_bullet_text: str = "Coursework in algorithms and data structures",
) -> ResumeContent:
    """Build a `ResumeContent` whose LLM-editable fields are adversarial.

    Purpose:
        Concentrate fixture wiring so each renderer test reads as one
        scenario. Locked fields default to LaTeX-safe text so the
        end-to-end compile test passes; the locked-field-policy tests
        pass adversarial values explicitly to prove those fields are
        emitted verbatim rather than sanitized.

    Args:
        personal_name: Value to put in the locked `personal.name` slot.
        education_bullet_text: Body for the locked education bullet.

    Returns:
        A schema-valid `ResumeContent` populated with adversarial bullet
        text in every section the renderer routes through `latex_safe`.
    """

    return ResumeContent(
        personal=PersonalSection(
            name=personal_name,
            phone="555-555-0000",
            email="test@example.com",
            links=[
                ResumeLink(
                    id="github_link",
                    label="github/test",
                    url="https://example.com",
                )
            ],
        ),
        education=EducationSection(
            entries=[
                EducationEntry(
                    id="edu_a",
                    institution="Test University",
                    date_range="2020 - 2024",
                    degree="B.S. Computer Science",
                    detail="GPA 4.0",
                    bullets=[
                        ResumeBullet(
                            id="edu_a_bullet_0",
                            text=education_bullet_text,
                        )
                    ],
                )
            ]
        ),
        experience=ExperienceSection(
            listings=[
                ExperienceListing(
                    id="exp_a",
                    title="Senior Engineer",
                    date_range="2024 - 2025",
                    organization="ACME Corp",
                    bullets=list(ADVERSARIAL_EXPERIENCE_BULLETS),
                )
            ]
        ),
        projects=ProjectsSection(
            listings=[
                ProjectListing(
                    id="proj_a",
                    title="Project A",
                    tech_stack="Python, Rust",
                    date_range="2024",
                    bullets=[
                        ResumeBullet(
                            id="proj_bullet_unknown",
                            text="Used \\sum operator across 100% of inputs",
                        )
                    ],
                )
            ]
        ),
        skills_achievements=SkillsAchievementsSection(
            listings=[
                SkillListing(
                    id="skill_langs",
                    category="Languages",
                    text="Python, Rust & TypeScript with 95% coverage",
                )
            ]
        ),
    )


def test_renderer_strips_unknown_command_from_experience_bullet() -> None:
    """The OP failure case `\\ETC` is rewritten before reaching `\\resumeItem`."""

    resume_content = _build_adversarial_resume()

    rendered_tex = render_resume_tex(resume_content)

    assert "\\ETC" not in rendered_tex
    assert "th\\resumeItem" not in rendered_tex
    assert "\\resumeItem{Shipped multi-agent tools thETC.}" in rendered_tex


def test_renderer_escapes_bare_specials_in_experience_bullet() -> None:
    """Bare `&` and `%` in an experience bullet become `\\&` and `\\%`."""

    resume_content = _build_adversarial_resume()

    rendered_tex = render_resume_tex(resume_content)

    assert (
        "\\resumeItem{Built Q\\&A pipeline reducing latency by 20\\%}" in rendered_tex
    )


def test_renderer_preserves_preescaped_specials_in_experience_bullet() -> None:
    """`\\$` and bare braces in a bullet survive a single sanitize pass."""

    resume_content = _build_adversarial_resume()

    rendered_tex = render_resume_tex(resume_content)

    assert "\\resumeItem{Drove cost down by \\$1\\{,\\}200}" in rendered_tex


def test_renderer_preserves_wellformed_textbf_in_experience_bullet() -> None:
    """`\\textbf{...}` emphasis is kept intact when the braces balance."""

    resume_content = _build_adversarial_resume()

    rendered_tex = render_resume_tex(resume_content)

    assert (
        "\\resumeItem{Led \\textbf{five engineers} on launch}" in rendered_tex
    )


def test_renderer_strips_unbalanced_textbf_in_experience_bullet() -> None:
    """Unbalanced `\\textbf{...` drops the wrapper rather than aborting compile."""

    resume_content = _build_adversarial_resume()

    rendered_tex = render_resume_tex(resume_content)

    assert "\\resumeItem{Owned the rollout}" in rendered_tex


def test_renderer_strips_double_backslash_in_experience_bullet() -> None:
    """`\\\\` is stripped so it cannot inject a surprise line break."""

    resume_content = _build_adversarial_resume()

    rendered_tex = render_resume_tex(resume_content)

    assert "\\resumeItem{line oneline two}" in rendered_tex


def test_renderer_sanitizes_project_bullets() -> None:
    """Project bullets also flow through `latex_safe` (renderer site #2)."""

    resume_content = _build_adversarial_resume()

    rendered_tex = render_resume_tex(resume_content)

    assert "\\sum" not in rendered_tex
    assert "\\resumeItem{Used sum operator across 100\\% of inputs}" in rendered_tex


def test_renderer_sanitizes_skill_listing_text() -> None:
    """Skill row `text` is sanitized but the `category` label stays locked."""

    resume_content = _build_adversarial_resume()

    rendered_tex = render_resume_tex(resume_content)

    # `category` is locked and must appear verbatim inside the `\textbf{}`.
    # The `text` half is LLM-editable and therefore sanitized.
    assert (
        "\\item{\\textbf{Languages}: Python, Rust \\& TypeScript with 95\\% coverage}"
        in rendered_tex
    )


def test_renderer_leaves_personal_name_unsanitized() -> None:
    """Locked `personal.name` keeps a bare `&` because it is never LLM-edited."""

    resume_content = _build_adversarial_resume(personal_name="Smith & Jones")

    rendered_tex = render_resume_tex(resume_content)

    # The literal `&` must survive verbatim — the locked-field policy is
    # that user-managed fields are never routed through `latex_safe`. If
    # this regresses the user can no longer put ampersands in their name.
    assert "Smith & Jones" in rendered_tex


def test_renderer_leaves_education_bullet_unsanitized() -> None:
    """Locked education bullets keep bare `&` (they are not LLM-edited)."""

    resume_content = _build_adversarial_resume(
        education_bullet_text="Coursework in algorithms & data structures",
    )

    rendered_tex = render_resume_tex(resume_content)

    # Education bullets are rendered with `\item ...`, not `\resumeItem{}`,
    # and the renderer does NOT route them through the sanitizer. The
    # bare `&` in the bullet text must therefore appear verbatim.
    assert "\\item Coursework in algorithms & data structures" in rendered_tex


@pytest.mark.skipif(
    shutil.which("latexmk") is None,
    reason="latexmk not installed; skipping end-to-end compile check",
)
def test_adversarial_resume_compiles_under_latexmk(tmp_path: Path) -> None:
    """The adversarial document compiles cleanly into a one-page PDF."""

    resume_content = _build_adversarial_resume()
    rendered_tex = render_resume_tex(resume_content)
    tex_path = tmp_path / "adversarial.tex"
    tex_path.write_text(rendered_tex, encoding="utf-8")

    completed_process = subprocess.run(
        [
            "latexmk",
            "-pdf",
            "-interaction=nonstopmode",
            "-halt-on-error",
            f"-output-directory={tmp_path}",
            str(tex_path),
        ],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        check=False,
    )

    pdf_path = tmp_path / "adversarial.pdf"
    assert completed_process.returncode == 0, (
        f"latexmk failed (stdout: {completed_process.stdout!r}, "
        f"stderr: {completed_process.stderr!r})"
    )
    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 0
