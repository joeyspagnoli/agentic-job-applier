"""Compile the user's base resume `.tex` to PDF with content-hash caching.

Purpose:
    Back the "skip tailoring" apply flow. When a user clicks "Apply
    anyways" on a job that has no SUCCESS review, the apply router needs
    a real on-disk PDF to upload. The source of truth is
    ``config/resume.tex``; recompiling on every click is wasteful and
    keeping a pre-compiled ``config/resume.pdf`` on disk risks drift.
    This module hashes the `.tex` bytes and caches the compiled PDF
    keyed by that hash so a cache hit is near-instantaneous and a cache
    miss invalidates automatically when the source changes.
"""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

from src.agents.resume_tailor.compiler import (
    ResumeCompileError,
    compile_resume_tex,
)
from src.utils.paths import resolve_repo_root

DEFAULT_BASE_RESUME_CACHE_DIR: Path = (
    resolve_repo_root() / "data" / "base_resume"
)


async def compile_base_resume_pdf(
    *,
    tex_path: Path,
    cache_dir: Path | None = None,
) -> Path:
    """Compile ``tex_path`` to PDF, caching by sha256 of the `.tex` bytes.

    Purpose:
        Provide an idempotent, side-effect-free way to obtain a compiled
        base-resume PDF for the synthetic apply path. The cache key is
        the sha256 digest of the source `.tex` bytes so any edit to
        ``config/resume.tex`` produces a new cache entry on the next
        call.
    Args:
        tex_path: Filesystem path to the user's base resume `.tex`.
        cache_dir: Directory used to store compiled PDFs keyed by
            content hash. Defaults to ``<repo>/data/base_resume`` when
            ``None``.
    Output:
        Returns the absolute path of the cached PDF.
    Raises:
        FileNotFoundError: When ``tex_path`` does not exist.
        ResumeCompileError: When the underlying tectonic compile fails.
    """

    resolved_tex_path = Path(tex_path)
    if not resolved_tex_path.exists():
        raise FileNotFoundError(
            f"Base resume .tex not found at {resolved_tex_path}"
        )

    resolved_cache_dir = (
        Path(cache_dir) if cache_dir is not None else DEFAULT_BASE_RESUME_CACHE_DIR
    )
    resolved_cache_dir.mkdir(parents=True, exist_ok=True)

    tex_bytes = resolved_tex_path.read_bytes()
    digest = hashlib.sha256(tex_bytes).hexdigest()
    cached_pdf_path = resolved_cache_dir / f"{digest}.pdf"
    if cached_pdf_path.exists():
        return cached_pdf_path.resolve()

    # ``compile_resume_tex`` is a blocking subprocess call (tectonic /
    # latexmk) — offload to a thread so we never block the event loop.
    try:
        compiled_pdf_path = await asyncio.to_thread(
            compile_resume_tex,
            tex_path=resolved_tex_path,
            pdf_output_path=cached_pdf_path,
        )
    except ResumeCompileError:
        # Best-effort cleanup so a partial file does not poison the cache.
        if cached_pdf_path.exists():
            cached_pdf_path.unlink(missing_ok=True)
        raise

    return Path(compiled_pdf_path).resolve()
