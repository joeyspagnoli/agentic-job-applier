"""Validate deterministic helper behavior for resume review tools.

Purpose:
    Cover report persistence, log parsing, compare-to-base labeling, and text
    signal extraction behavior for the review tool surface.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from src.agents.resume_review_pi import tools as review_tools
from src.agents.resume_review_pi.schemas import PdfGeometryMetrics


def test_write_review_report_tool_persists_valid_json(tmp_path: Path) -> None:
    """Verify report tool validates and writes canonical report JSON.

    Purpose:
        Ensure agent completion handshake writes schema-valid JSON artifact that
        runtime can parse deterministically.
    Args:
        tmp_path: Pytest temporary directory fixture.
    Output:
        Returns `None`; test passes when file contains expected verdict fields.
    """

    report_path = tmp_path / "review_report.json"
    report_payload = {
        "verdict": "BASE",
        "summary": "Base resume chosen after review.",
        "iteration_count": 2,
        "selected_yaml_path": str(tmp_path / "resume_base.yaml"),
        "selected_tex_path": str(tmp_path / "resume_base.tex"),
        "selected_pdf_path": str(tmp_path / "resume_base.pdf"),
    }

    written_path = review_tools.write_review_report_tool(
        path=report_path,
        report_payload=report_payload,
    )

    assert written_path == str(report_path.resolve())
    stored_payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert stored_payload["verdict"] == "BASE"
    assert stored_payload["selected_pdf_path"] == str(tmp_path / "resume_base.pdf")


def test_analyze_latex_log_tool_counts_warnings_and_errors(tmp_path: Path) -> None:
    """Verify LaTeX log parser returns deterministic warning/error counters.

    Purpose:
        Protect structured compile diagnostics used by review decisions.
    Args:
        tmp_path: Pytest temporary directory fixture.
    Output:
        Returns `None`; test passes when counts match fixture log text.
    """

    log_path = tmp_path / "resume.log"
    log_path.write_text(
        "\n".join(
            [
                "Overfull \\hbox (12.0pt too wide) in paragraph at lines 10--12",
                "Underfull \\hbox (badness 10000) in paragraph at lines 20--22",
                "LaTeX Warning: Label(s) may have changed.",
                "! Undefined control sequence.",
                "Fatal error occurred, no output PDF file produced!",
            ]
        ),
        encoding="utf-8",
    )

    analysis = review_tools.analyze_latex_log_tool(log_path=log_path)

    assert analysis.overfull_count == 1
    assert analysis.underfull_count == 1
    assert analysis.latex_errors == 1
    assert analysis.warnings >= 1
    assert analysis.has_fatal_error is True


def test_compare_pdf_to_base_tool_uses_cached_base_metrics(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verify compare tool supports precomputed base geometry JSON input.

    Purpose:
        Ensure review comparisons can reuse cached base metrics without
        re-running expensive geometry analysis on every call.
    Args:
        monkeypatch: Pytest monkeypatch fixture.
        tmp_path: Pytest temporary directory fixture.
    Output:
        Returns `None`; test passes when cached base metrics are honored.
    """

    candidate_pdf = tmp_path / "candidate.pdf"
    base_pdf = tmp_path / "base.pdf"
    candidate_pdf.write_text("stub", encoding="utf-8")
    base_pdf.write_text("stub", encoding="utf-8")

    candidate_metrics = PdfGeometryMetrics(
        page_count=1,
        page_width_pt=612,
        page_height_pt=792,
        margin_top_pt=30,
        margin_bottom_pt=40,
        margin_left_pt=72,
        margin_right_pt=72,
        vert_cov=0.80,
        horiz_cov=0.76,
        ink_ratio=0.11,
        bbox_cov=0.78,
        text_block_count=24,
    )

    base_metrics = PdfGeometryMetrics(
        page_count=1,
        page_width_pt=612,
        page_height_pt=792,
        margin_top_pt=32,
        margin_bottom_pt=32,
        margin_left_pt=72,
        margin_right_pt=72,
        vert_cov=0.86,
        horiz_cov=0.76,
        ink_ratio=0.12,
        bbox_cov=0.80,
        text_block_count=25,
    )

    base_geometry_path = tmp_path / "base_geometry.json"
    base_geometry_path.write_text(
        json.dumps({"metrics": base_metrics.model_dump(mode="json")}),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        review_tools,
        "analyze_pdf_geometry_tool",
        lambda pdf_path, dpi=150: candidate_metrics,
    )

    comparison = review_tools.compare_pdf_to_base_tool(
        candidate_pdf=candidate_pdf,
        base_pdf=base_pdf,
        base_geometry_json=base_geometry_path,
    )

    assert comparison.base_metrics.ink_ratio == pytest.approx(0.12)
    assert comparison.delta["ink_ratio"] == pytest.approx(-0.01)
    assert "SPARSER_THAN_BASE" in [label.value for label in comparison.relative_profile]


def test_extract_pdf_text_signals_tool_counts_lines_and_bullets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verify text-signal extraction computes expected counters.

    Purpose:
        Ensure textual quality helper remains deterministic when parsing
        pdftotext output.
    Args:
        monkeypatch: Pytest monkeypatch fixture.
        tmp_path: Pytest temporary directory fixture.
    Output:
        Returns `None`; test passes when counters match fixture payload.
    """

    pdf_path = tmp_path / "resume.pdf"
    pdf_path.write_text("stub", encoding="utf-8")

    expected_stdout = "\n".join(
        [
            "John Doe",
            "- Built feature A",
            "* Improved API latency",
            "Experience",
        ]
    )

    def fake_run(*_: object, **__: object) -> subprocess.CompletedProcess[str]:
        """Return deterministic pdftotext output for text-signal tests.

        Purpose:
            Remove external command dependency and stabilize text parsing tests.
        Args:
            *_: Ignored positional args.
            **__: Ignored keyword args.
        Output:
            Returns successful completed process with fixture stdout.
        """

        return subprocess.CompletedProcess(
            args=["pdftotext"],
            returncode=0,
            stdout=expected_stdout,
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    signals = review_tools.extract_pdf_text_signals_tool(pdf_path=pdf_path)

    assert signals.word_count >= 6
    assert signals.nonempty_line_count == 4
    assert signals.bullet_line_count == 2


def test_analyze_pdf_geometry_tool_aggregates_metrics(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verify geometry tool combines page, raster, and bbox signals.

    Purpose:
        Ensure top-level geometry tool returns expected fields from helper
        sub-calculations.
    Args:
        monkeypatch: Pytest monkeypatch fixture.
        tmp_path: Pytest temporary directory fixture.
    Output:
        Returns `None`; test passes when merged metrics are returned.
    """

    pdf_path = tmp_path / "resume.pdf"
    pdf_path.write_text("stub", encoding="utf-8")

    monkeypatch.setattr(review_tools, "get_page_count_tool", lambda **_: 1)
    monkeypatch.setattr(
        review_tools, "_parse_pdf_page_size_pt", lambda _: (612.0, 792.0)
    )
    monkeypatch.setattr(
        review_tools,
        "_compute_raster_metrics",
        lambda pdf_path, dpi: (30.0, 40.0, 70.0, 70.0, 0.81, 0.75, 0.115),
    )
    monkeypatch.setattr(review_tools, "_extract_bbox_metrics", lambda _: (0.79, 26))

    metrics = review_tools.analyze_pdf_geometry_tool(pdf_path=pdf_path)

    assert metrics.page_count == 1
    assert metrics.margin_bottom_pt == pytest.approx(40.0)
    assert metrics.ink_ratio == pytest.approx(0.115)
    assert metrics.text_block_count == 26
