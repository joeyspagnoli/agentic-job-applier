"""Compile generated resume LaTeX and extract deterministic page counts.

Purpose:
    Provide compile and page-count primitives for the resume-tailor one-page
    enforcement loop.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

DEFAULT_LATEX_TIMEOUT_SECONDS = 120


class ResumeCompileError(RuntimeError):
    """Represent failures while compiling LaTeX into PDF artifacts."""


def compile_resume_tex(
    *,
    tex_path: str | Path,
    pdf_output_path: str | Path | None = None,
    timeout_seconds: int = DEFAULT_LATEX_TIMEOUT_SECONDS,
) -> Path:
    """Compile one resume `.tex` file into a PDF using `tectonic`.

    Purpose:
        Provide deterministic local PDF compilation with actionable errors for
        the resume-tailor workflow. Tectonic is a self-contained LaTeX engine
        that resolves missing packages on demand from CTAN and caches them in
        XDG_CACHE_HOME/Tectonic, so the runtime image stays small and free of
        TeX Live packaging gaps.
    Args:
        tex_path: Source LaTeX file path to compile.
        pdf_output_path: Optional destination PDF path to copy the compiled
            artifact to after successful build.
        timeout_seconds: Maximum allowed compile duration before timeout.
    Output:
        Returns the absolute path of the compiled PDF artifact.
    Raises:
        ResumeCompileError: When `tectonic` is missing, times out, returns
            non-zero, or fails to produce a PDF file.
    """

    source_tex_path = Path(tex_path).resolve()
    if not source_tex_path.exists():
        raise ResumeCompileError(f"LaTeX source file not found: {source_tex_path}")

    output_directory = source_tex_path.parent
    tectonic_command = [
        "tectonic",
        "--keep-logs",
        "--keep-intermediates",
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
            cwd=output_directory,
        )
    except FileNotFoundError as exc:
        raise ResumeCompileError(
            "tectonic is not available in PATH; install the tectonic LaTeX engine"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ResumeCompileError(
            f"tectonic timed out after {timeout_seconds} seconds"
        ) from exc

    if completed_process.returncode != 0:
        error_message = (
            "tectonic failed with non-zero exit code. "
            f"stdout:\n{completed_process.stdout}\n"
            f"stderr:\n{completed_process.stderr}"
        )
        raise ResumeCompileError(error_message)

    generated_pdf_path = output_directory / f"{source_tex_path.stem}.pdf"
    if not generated_pdf_path.exists():
        raise ResumeCompileError(
            f"tectonic completed but PDF was not found at {generated_pdf_path}"
        )

    if pdf_output_path is None:
        return generated_pdf_path.resolve()

    target_pdf_path = Path(pdf_output_path).resolve()
    target_pdf_path.parent.mkdir(parents=True, exist_ok=True)
    if target_pdf_path != generated_pdf_path.resolve():
        shutil.copy2(generated_pdf_path, target_pdf_path)

    return target_pdf_path


def extract_page_count_from_pdfinfo_output(output_text: str) -> int | None:
    """Extract page count from `pdfinfo` command output.

    Purpose:
        Keep `pdfinfo` parsing isolated and testable for reliable page-count
        extraction.
    Args:
        output_text: Raw stdout string produced by `pdfinfo`.
    Output:
        Returns the parsed page count, or `None` when no page line exists.
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
        Recover page count even when `pdfinfo` is unavailable by parsing the
        `Output written on ... (N page(s), ...)` line from LaTeX logs.
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
        Provide deterministic one-page checks while supporting environments
        where `pdfinfo` may be unavailable.
    Args:
        pdf_path: Filesystem path to the compiled PDF artifact.
        log_path: Optional LaTeX log path for fallback page-count parsing.
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
        completed_process = subprocess.run(
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
