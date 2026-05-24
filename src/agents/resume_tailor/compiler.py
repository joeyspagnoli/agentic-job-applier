"""Compile generated resume LaTeX and extract deterministic page counts.

Purpose:
    Provide compile and page-count primitives for the resume-tailor
    one-page enforcement loop. Tectonic is the default compiler so the
    Docker image can ship a single self-contained binary with the CTAN
    cache pre-warmed; `latexmk` is kept behind an env-var escape hatch
    for users who still have a system TeX Live installation.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Literal

# Default timeout for tectonic — first compiles populate the CTAN cache
# and can run long; subsequent compiles hit the cache and finish quickly.
DEFAULT_TECTONIC_TIMEOUT_SECONDS = 240

# Legacy default for the latexmk path. The plan keeps the latexmk
# escape hatch behind `RESUME_COMPILER=latexmk` while the rest of the
# Phase 1 rollout moves to tectonic.
DEFAULT_LATEXMK_TIMEOUT_SECONDS = 120

# Backwards-compat alias for existing imports — points at the latexmk
# timeout because that's what the constant referred to historically.
DEFAULT_LATEX_TIMEOUT_SECONDS = DEFAULT_LATEXMK_TIMEOUT_SECONDS

# Env var the operator flips to keep the old behavior. Anything other
# than `tectonic` falls back to `latexmk`.
COMPILER_ENV_VAR = "RESUME_COMPILER"
TECTONIC_TIMEOUT_ENV_VAR = "TECTONIC_TIMEOUT_SECONDS"

CompilerKind = Literal["tectonic", "latexmk"]


class ResumeCompileError(RuntimeError):
    """Represent failures while compiling LaTeX into PDF artifacts."""


def compile_resume_tex(
    *,
    tex_path: str | Path,
    pdf_output_path: str | Path | None = None,
    timeout_seconds: int | None = None,
) -> Path:
    """Compile one resume `.tex` file into a PDF.

    Purpose:
        Provide deterministic local PDF compilation with actionable
        errors for the resume-tailor workflow. Routes to tectonic by
        default, latexmk when `RESUME_COMPILER=latexmk` is set.
    Args:
        tex_path: Source LaTeX file path to compile.
        pdf_output_path: Optional destination PDF path to copy the
            compiled artifact to after a successful build.
        timeout_seconds: Maximum allowed compile duration. When `None`,
            the per-compiler default applies (240s for tectonic, 120s
            for latexmk); tectonic also honors `TECTONIC_TIMEOUT_SECONDS`.
    Output:
        Returns the absolute path of the compiled PDF artifact.
    Raises:
        ResumeCompileError: When the compiler is missing, times out,
            returns non-zero, or fails to produce a PDF file.
    """

    source_tex_path = Path(tex_path).resolve()
    if not source_tex_path.exists():
        raise ResumeCompileError(f"LaTeX source file not found: {source_tex_path}")

    compiler = _resolve_compiler()
    if compiler == "tectonic":
        effective_timeout = timeout_seconds or _resolve_tectonic_timeout()
        return _compile_with_tectonic(
            source_tex_path=source_tex_path,
            pdf_output_path=pdf_output_path,
            timeout_seconds=effective_timeout,
        )
    effective_timeout = timeout_seconds or DEFAULT_LATEXMK_TIMEOUT_SECONDS
    return _compile_with_latexmk(
        source_tex_path=source_tex_path,
        pdf_output_path=pdf_output_path,
        timeout_seconds=effective_timeout,
    )


def _resolve_compiler() -> CompilerKind:
    """Decide which compiler this invocation should use.

    Purpose:
        Encapsulate the env-var dispatch so callers stay simple. The
        plan ships tectonic as the default with a documented escape
        hatch for users on the legacy latexmk path.
    Output:
        `"tectonic"` unless `RESUME_COMPILER=latexmk` is set.
    """

    value = os.environ.get(COMPILER_ENV_VAR, "").strip().lower()
    if value == "latexmk":
        return "latexmk"
    return "tectonic"


def _resolve_tectonic_timeout() -> int:
    """Read the tectonic timeout from the environment or fall back.

    Purpose:
        Let operators raise the timeout for resumes with heavy CTAN
        package needs without touching code.
    Output:
        Positive integer timeout in seconds.
    """

    raw = os.environ.get(TECTONIC_TIMEOUT_ENV_VAR, "").strip()
    if not raw:
        return DEFAULT_TECTONIC_TIMEOUT_SECONDS
    try:
        parsed = int(raw)
    except ValueError:
        return DEFAULT_TECTONIC_TIMEOUT_SECONDS
    return parsed if parsed > 0 else DEFAULT_TECTONIC_TIMEOUT_SECONDS


def _compile_with_tectonic(
    *,
    source_tex_path: Path,
    pdf_output_path: str | Path | None,
    timeout_seconds: int,
) -> Path:
    """Compile via `tectonic -X compile --keep-logs --outfmt pdf`.

    Purpose:
        Run tectonic with the flags the plan §3.2 / §8.1 settled on:
        bundled-resolver mode (`-X compile`), kept log file for error
        extraction, and an explicit `--outdir` so artifacts land where
        the caller expects.
    Args:
        source_tex_path: Resolved `.tex` source path.
        pdf_output_path: Optional copy destination for the compiled PDF.
        timeout_seconds: Tectonic process timeout.
    Output:
        Resolved absolute path of the compiled PDF artifact.
    Raises:
        ResumeCompileError: When tectonic is missing, times out, exits
            non-zero, or fails to produce a PDF.
    """

    if shutil.which("tectonic") is None:
        raise ResumeCompileError(
            "tectonic is not available in PATH; install tectonic or set "
            f"{COMPILER_ENV_VAR}=latexmk to use the legacy compiler"
        )

    output_directory = source_tex_path.parent
    tectonic_command = [
        "tectonic",
        "-X",
        "compile",
        "--keep-logs",
        "--outfmt",
        "pdf",
        "--outdir",
        str(output_directory),
        str(source_tex_path),
    ]

    try:
        completed_process = subprocess.run(
            tectonic_command,
            check=False,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise ResumeCompileError(
            f"tectonic timed out after {timeout_seconds} seconds"
        ) from exc

    generated_pdf_path = output_directory / f"{source_tex_path.stem}.pdf"
    log_path = output_directory / f"{source_tex_path.stem}.log"

    if completed_process.returncode != 0:
        # Prefer the log file (richer detail) over stderr; fall back to
        # the captured streams when the log is missing.
        if log_path.exists():
            log_content = log_path.read_text(encoding="utf-8", errors="ignore")
            first_error_line = _extract_first_error_line(log_content)
            raise ResumeCompileError(
                "tectonic failed with non-zero exit code. First error: "
                f"{first_error_line}"
            )
        raise ResumeCompileError(
            "tectonic failed with non-zero exit code. "
            f"stdout:\n{completed_process.stdout}\n"
            f"stderr:\n{completed_process.stderr}"
        )

    if not generated_pdf_path.exists():
        raise ResumeCompileError(
            f"tectonic completed but PDF was not found at {generated_pdf_path}"
        )

    return _maybe_copy_pdf(
        generated_pdf_path=generated_pdf_path, pdf_output_path=pdf_output_path
    )


def _compile_with_latexmk(
    *,
    source_tex_path: Path,
    pdf_output_path: str | Path | None,
    timeout_seconds: int,
) -> Path:
    """Compile via `latexmk -pdf` — the pre-Phase-1 default path.

    Purpose:
        Preserve the legacy compile behavior so operators with a
        working system TeX Live can keep using it via
        `RESUME_COMPILER=latexmk`.
    Args:
        source_tex_path: Resolved `.tex` source path.
        pdf_output_path: Optional copy destination for the compiled PDF.
        timeout_seconds: latexmk process timeout.
    Output:
        Resolved absolute path of the compiled PDF artifact.
    Raises:
        ResumeCompileError: When latexmk is missing, times out, exits
            non-zero, or fails to produce a PDF.
    """

    output_directory = source_tex_path.parent
    latexmk_command = [
        "latexmk",
        "-pdf",
        "-interaction=nonstopmode",
        "-halt-on-error",
        "-file-line-error",
        source_tex_path.name,
    ]

    try:
        completed_process = subprocess.run(
            latexmk_command,
            check=False,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            cwd=output_directory,
        )
    except FileNotFoundError as exc:
        raise ResumeCompileError(
            "latexmk is not available in PATH; install TeX Live latexmk"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ResumeCompileError(
            f"latexmk timed out after {timeout_seconds} seconds"
        ) from exc

    if completed_process.returncode != 0:
        error_message = (
            "latexmk failed with non-zero exit code. "
            f"stdout:\n{completed_process.stdout}\n"
            f"stderr:\n{completed_process.stderr}"
        )
        raise ResumeCompileError(error_message)

    generated_pdf_path = output_directory / f"{source_tex_path.stem}.pdf"
    if not generated_pdf_path.exists():
        raise ResumeCompileError(
            f"latexmk completed but PDF was not found at {generated_pdf_path}"
        )

    return _maybe_copy_pdf(
        generated_pdf_path=generated_pdf_path, pdf_output_path=pdf_output_path
    )


def _maybe_copy_pdf(
    *,
    generated_pdf_path: Path,
    pdf_output_path: str | Path | None,
) -> Path:
    """Copy the compiled PDF to a destination path if one was provided.

    Purpose:
        Shared exit logic for both compiler backends — keeps the
        copy-or-don't path identical to the pre-Phase-1 behavior.
    Args:
        generated_pdf_path: Where the compiler dropped the PDF.
        pdf_output_path: Optional copy target. `None` returns the
            generated path unchanged.
    Output:
        Resolved absolute path of the final PDF (copy target when
        provided, otherwise the generated path).
    """

    if pdf_output_path is None:
        return generated_pdf_path.resolve()

    target_pdf_path = Path(pdf_output_path).resolve()
    target_pdf_path.parent.mkdir(parents=True, exist_ok=True)
    if target_pdf_path != generated_pdf_path.resolve():
        shutil.copy2(generated_pdf_path, target_pdf_path)
    return target_pdf_path


def _extract_first_error_line(log_text: str) -> str:
    """Return a short summary of the first LaTeX error in `log_text`.

    Purpose:
        Surface the most actionable line of the tectonic log to the
        caller's `ResumeCompileError` message. Falls back to the first
        non-blank line when no `!` error preamble is present.
    Args:
        log_text: Raw content of the tectonic `.log` file.
    Output:
        Single-line error summary, truncated to ~400 chars.
    """

    bang_index = log_text.find("\n!")
    if bang_index != -1:
        snippet = log_text[bang_index : bang_index + 400].splitlines()
        joined = " ".join(line.strip() for line in snippet if line.strip())
        return joined[:400]

    for line in log_text.splitlines():
        if line.strip():
            return line.strip()[:400]
    return "(empty log)"


def extract_page_count_from_pdfinfo_output(output_text: str) -> int | None:
    """Extract page count from `pdfinfo` command output.

    Purpose:
        Keep `pdfinfo` parsing isolated and testable for reliable
        page-count extraction.
    Args:
        output_text: Raw stdout string produced by `pdfinfo`.
    Output:
        Returns the parsed page count, or `None` when no page line
        exists.
    """

    for output_line in output_text.splitlines():
        normalized_line = output_line.strip()
        if not normalized_line.startswith("Pages:"):
            continue

        _, raw_value = normalized_line.split(":", maxsplit=1)
        stripped_value = raw_value.strip()
        if stripped_value.isdigit():
            return int(stripped_value)
    return None


def extract_page_count_from_latex_log(log_text: str) -> int | None:
    """Extract page count from LaTeX log text as fallback behavior.

    Purpose:
        Recover page count even when `pdfinfo` is unavailable by
        parsing the `Output written on ... (N page(s), ...)` line from
        LaTeX logs.
    Args:
        log_text: Raw text content from a LaTeX log file.
    Output:
        Returns the parsed page count, or `None` when no match is found.
    """

    page_match = re.search(r"Output written on .*\((\d+) page", log_text)
    if page_match is None:
        return None
    return int(page_match.group(1))


def get_pdf_page_count(
    *, pdf_path: str | Path, log_path: str | Path | None = None
) -> int:
    """Get page count with `pdfinfo` primary and log-parse fallback.

    Purpose:
        Provide deterministic one-page checks while supporting
        environments where `pdfinfo` may be unavailable.
    Args:
        pdf_path: Filesystem path to the compiled PDF artifact.
        log_path: Optional LaTeX log path for fallback page-count
            parsing.
    Output:
        Returns the parsed integer page count.
    Raises:
        RuntimeError: When both `pdfinfo` parsing and log fallback fail.
    """

    resolved_pdf_path = Path(pdf_path).resolve()
    if not resolved_pdf_path.exists():
        raise RuntimeError(
            f"PDF artifact not found for page count check: {resolved_pdf_path}"
        )

    try:
        completed_process: subprocess.CompletedProcess[str] | None = subprocess.run(
            ["pdfinfo", str(resolved_pdf_path)],
            check=False,
            text=True,
            capture_output=True,
        )
    except FileNotFoundError:
        completed_process = None

    if completed_process is not None:
        parsed_page_count = extract_page_count_from_pdfinfo_output(
            completed_process.stdout
        )
        if parsed_page_count is not None:
            return parsed_page_count

    if log_path is not None:
        resolved_log_path = Path(log_path).resolve()
        if resolved_log_path.exists():
            with open(
                resolved_log_path, "r", encoding="utf-8", errors="ignore"
            ) as log_file:
                log_content = log_file.read()
            parsed_page_count = extract_page_count_from_latex_log(log_content)
            if parsed_page_count is not None:
                return parsed_page_count

    raise RuntimeError(
        "Could not determine PDF page count from pdfinfo output or LaTeX log"
    )
