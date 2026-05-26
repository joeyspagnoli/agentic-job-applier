"""Unit tests for the content-hash-cached base-resume compile helper.

Purpose:
    Lock the cache-hit / cache-miss behavior of
    :func:`src.agents.resume_tailor.base_compile.compile_base_resume_pdf`
    without invoking tectonic. The underlying compile function is
    monkeypatched to a deterministic stub that creates an empty PDF and
    counts invocations.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from src.agents.resume_tailor import base_compile
from src.agents.resume_tailor.compiler import ResumeCompileError


def _write_base_tex(tmp_path: Path, contents: str = "\\documentclass{article}") -> Path:
    """Drop a minimal `.tex` file and return its path."""

    tex_path = tmp_path / "resume.tex"
    tex_path.write_text(contents, encoding="utf-8")
    return tex_path


def test_compile_base_resume_pdf_produces_pdf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A first call invokes the compiler and stores a PDF in the cache."""

    tex_path = _write_base_tex(tmp_path)
    cache_dir = tmp_path / "cache"

    def _fake_compile(
        *,
        tex_path: Path,
        pdf_output_path: Path,
        timeout_seconds: int | None = None,
    ) -> Path:
        Path(pdf_output_path).write_bytes(b"%PDF-fake")
        return Path(pdf_output_path)

    monkeypatch.setattr(base_compile, "compile_resume_tex", _fake_compile)

    result = asyncio.run(
        base_compile.compile_base_resume_pdf(tex_path=tex_path, cache_dir=cache_dir)
    )

    assert result.exists()
    assert result.parent == cache_dir.resolve()
    assert result.read_bytes() == b"%PDF-fake"


def test_compile_base_resume_pdf_cache_hit_skips_recompile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A second call with identical `.tex` bytes does not recompile."""

    tex_path = _write_base_tex(tmp_path)
    cache_dir = tmp_path / "cache"

    invocation_count = {"value": 0}

    def _counting_compile(
        *,
        tex_path: Path,
        pdf_output_path: Path,
        timeout_seconds: int | None = None,
    ) -> Path:
        invocation_count["value"] += 1
        Path(pdf_output_path).write_bytes(b"%PDF-fake")
        return Path(pdf_output_path)

    monkeypatch.setattr(base_compile, "compile_resume_tex", _counting_compile)

    first = asyncio.run(
        base_compile.compile_base_resume_pdf(tex_path=tex_path, cache_dir=cache_dir)
    )
    second = asyncio.run(
        base_compile.compile_base_resume_pdf(tex_path=tex_path, cache_dir=cache_dir)
    )

    assert first == second
    assert invocation_count["value"] == 1


def test_compile_base_resume_pdf_recompiles_on_content_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Editing the source `.tex` produces a different cache entry."""

    tex_path = _write_base_tex(tmp_path, contents="version-a")
    cache_dir = tmp_path / "cache"
    invocation_count = {"value": 0}

    def _counting_compile(
        *,
        tex_path: Path,
        pdf_output_path: Path,
        timeout_seconds: int | None = None,
    ) -> Path:
        invocation_count["value"] += 1
        Path(pdf_output_path).write_bytes(b"%PDF-fake")
        return Path(pdf_output_path)

    monkeypatch.setattr(base_compile, "compile_resume_tex", _counting_compile)

    first = asyncio.run(
        base_compile.compile_base_resume_pdf(tex_path=tex_path, cache_dir=cache_dir)
    )

    tex_path.write_text("version-b", encoding="utf-8")
    second = asyncio.run(
        base_compile.compile_base_resume_pdf(tex_path=tex_path, cache_dir=cache_dir)
    )

    assert first != second
    assert invocation_count["value"] == 2


def test_compile_base_resume_pdf_raises_when_tex_missing(
    tmp_path: Path,
) -> None:
    """A missing source `.tex` path raises FileNotFoundError."""

    missing_path = tmp_path / "does_not_exist.tex"
    cache_dir = tmp_path / "cache"

    with pytest.raises(FileNotFoundError):
        asyncio.run(
            base_compile.compile_base_resume_pdf(
                tex_path=missing_path, cache_dir=cache_dir
            )
        )


def test_compile_base_resume_pdf_clears_partial_artifact_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed compile must not poison the cache with a partial PDF."""

    tex_path = _write_base_tex(tmp_path)
    cache_dir = tmp_path / "cache"

    def _failing_compile(
        *,
        tex_path: Path,
        pdf_output_path: Path,
        timeout_seconds: int | None = None,
    ) -> Path:
        Path(pdf_output_path).write_bytes(b"partial")
        raise ResumeCompileError("boom")

    monkeypatch.setattr(base_compile, "compile_resume_tex", _failing_compile)

    with pytest.raises(ResumeCompileError):
        asyncio.run(
            base_compile.compile_base_resume_pdf(
                tex_path=tex_path, cache_dir=cache_dir
            )
        )

    # No cached PDF should remain.
    assert list(cache_dir.glob("*.pdf")) == []
