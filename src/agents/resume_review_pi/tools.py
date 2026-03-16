"""Deterministic analysis tools for the pi-mono resume review workflow.

Purpose:
    Provide geometry, compare-to-base, log, text, and report-write primitives
    used by the high-agency review agent.
"""

from __future__ import annotations

import json
import math
import re
import subprocess
import tempfile
import xml.etree.ElementTree as element_tree
from pathlib import Path

from src.agents.resume_tailor_pi.tools import get_page_count_tool

from .schemas import LatexLogAnalysis
from .schemas import PdfComparisonResult
from .schemas import PdfGeometryMetrics
from .schemas import PdfTextSignals
from .schemas import ReviewProfileLabel
from .schemas import ReviewReport

DEFAULT_GEOMETRY_DPI = 150
DEFAULT_WHITE_THRESHOLD_RATIO = 0.98
SPARSE_INK_DELTA = 0.01
SPARSE_VERT_COVERAGE_DELTA = 0.03
DENSE_INK_DELTA = 0.01
DENSE_VERT_COVERAGE_DELTA = 0.03
MARGIN_BALANCE_DELTA_PT = 4.0


class ReviewToolError(RuntimeError):
    """Represent a deterministic review-tool command failure."""


def _local_tag_name(raw_tag: str) -> str:
    """Extract a namespace-free XML tag name.

    Purpose:
        Normalize XML element tags from `pdftotext -bbox-layout` output so the
        parser works across namespaced and non-namespaced payloads.
    Args:
        raw_tag: Raw XML tag value from ElementTree.
    Output:
        Returns the trailing local tag name.
    """

    if "}" in raw_tag:
        return raw_tag.split("}", maxsplit=1)[1]
    return raw_tag


def _parse_pdf_page_size_pt(pdf_path: Path) -> tuple[float, float]:
    """Parse first-page width and height in points using `pdfinfo`.

    Purpose:
        Provide stable page dimensions for geometry normalization.
    Args:
        pdf_path: Absolute PDF path to inspect.
    Output:
        Returns `(page_width_pt, page_height_pt)`.
    Raises:
        ReviewToolError: When `pdfinfo` is unavailable or page-size parsing
            fails.
    """

    try:
        completed_process = subprocess.run(
            ["pdfinfo", str(pdf_path)],
            check=False,
            text=True,
            capture_output=True,
        )
    except FileNotFoundError as exc:
        raise ReviewToolError("pdfinfo not found in PATH") from exc

    if completed_process.returncode != 0:
        raise ReviewToolError(
            "pdfinfo failed for geometry parsing. "
            f"stderr={completed_process.stderr.strip()}"
        )

    size_match = re.search(
        r"Page\s+size:\s+([0-9]+(?:\.[0-9]+)?)\s+x\s+([0-9]+(?:\.[0-9]+)?)\s+pts",
        completed_process.stdout,
    )
    if size_match is None:
        raise ReviewToolError("Could not parse page size from pdfinfo output")

    return float(size_match.group(1)), float(size_match.group(2))


def _read_next_pgm_token(payload: bytes, start_index: int) -> tuple[bytes, int]:
    """Read one PGM token while skipping whitespace and comment lines.

    Purpose:
        Parse binary PGM headers without third-party imaging dependencies.
    Args:
        payload: Full file byte payload.
        start_index: Current parse index.
    Output:
        Returns `(token, next_index)` after consuming one header token.
    Raises:
        ReviewToolError: When token parsing fails due to truncated payload.
    """

    index = start_index
    payload_length = len(payload)

    while index < payload_length:
        current_byte = payload[index]
        if chr(current_byte).isspace():
            index += 1
            continue

        if current_byte == ord("#"):
            while index < payload_length and payload[index] != ord("\n"):
                index += 1
            continue

        break

    if index >= payload_length:
        raise ReviewToolError("PGM header parsing reached end-of-file unexpectedly")

    token_start = index
    while index < payload_length and not chr(payload[index]).isspace():
        index += 1

    token = payload[token_start:index]
    if token == b"":
        raise ReviewToolError("PGM header token parsing failed")
    return token, index


def _load_pgm_grayscale_values(pgm_path: Path) -> tuple[int, int, int, bytes]:
    """Load binary PGM dimensions, max value, and grayscale payload bytes.

    Purpose:
        Convert `pdftoppm -pgm` output into deterministic pixel arrays used for
        whitespace and margin measurements.
    Args:
        pgm_path: Absolute path to `.pgm` raster artifact.
    Output:
        Returns `(width_px, height_px, max_gray_value, pixel_bytes)`.
    Raises:
        ReviewToolError: When file format is invalid or payload size mismatches
            header dimensions.
    """

    payload = pgm_path.read_bytes()
    if not payload.startswith(b"P5"):
        raise ReviewToolError(f"Unsupported PGM format for file: {pgm_path}")

    index = 2
    width_token, index = _read_next_pgm_token(payload, index)
    height_token, index = _read_next_pgm_token(payload, index)
    max_value_token, index = _read_next_pgm_token(payload, index)

    width_px = int(width_token.decode("ascii"))
    height_px = int(height_token.decode("ascii"))
    max_value = int(max_value_token.decode("ascii"))

    while index < len(payload) and chr(payload[index]).isspace():
        index += 1

    bytes_per_pixel = 1 if max_value <= 255 else 2
    expected_payload_size = width_px * height_px * bytes_per_pixel
    pixel_bytes = payload[index:]

    if len(pixel_bytes) != expected_payload_size:
        raise ReviewToolError(
            "PGM pixel payload size mismatch: "
            f"expected={expected_payload_size} actual={len(pixel_bytes)}"
        )

    return width_px, height_px, max_value, pixel_bytes


def _to_gray_value(pixel_bytes: bytes, pixel_index: int, max_value: int) -> int:
    """Convert one pixel from raw PGM bytes into an integer grayscale value.

    Purpose:
        Support both 8-bit and 16-bit PGM payload variants in raster scoring.
    Args:
        pixel_bytes: Raw PGM pixel payload.
        pixel_index: Zero-based pixel index.
        max_value: Header max gray value.
    Output:
        Returns one grayscale intensity value.
    """

    if max_value <= 255:
        return pixel_bytes[pixel_index]

    byte_offset = pixel_index * 2
    return int.from_bytes(pixel_bytes[byte_offset : byte_offset + 2], "big")


def _compute_raster_metrics(
    *,
    pdf_path: Path,
    dpi: int,
) -> tuple[float, float, float, float, float, float, float]:
    """Compute first-page raster metrics from PDF content.

    Purpose:
        Calculate deterministic whitespace/coverage signals from rendered pixels
        without relying on model interpretation.
    Args:
        pdf_path: Absolute PDF path to analyze.
        dpi: Rasterization DPI used for `pdftoppm`.
    Output:
        Returns tuple:
            `(margin_top_pt, margin_bottom_pt, margin_left_pt, margin_right_pt,
              vert_cov, horiz_cov, ink_ratio)`.
    Raises:
        ReviewToolError: When rasterization or parsing fails.
    """

    with tempfile.TemporaryDirectory() as temporary_dir:
        temp_dir_path = Path(temporary_dir)
        raster_prefix = temp_dir_path / "first_page"
        raster_command = [
            "pdftoppm",
            "-f",
            "1",
            "-singlefile",
            "-gray",
            "-r",
            str(dpi),
            str(pdf_path),
            str(raster_prefix),
        ]

        try:
            completed_process = subprocess.run(
                raster_command,
                check=False,
                text=True,
                capture_output=True,
            )
        except FileNotFoundError as exc:
            raise ReviewToolError("pdftoppm not found in PATH") from exc

        if completed_process.returncode != 0:
            raise ReviewToolError(
                "pdftoppm failed during raster analysis. "
                f"stderr={completed_process.stderr.strip()}"
            )

        pgm_path = raster_prefix.with_suffix(".pgm")
        if not pgm_path.exists():
            raise ReviewToolError(
                f"Expected raster artifact not found after pdftoppm: {pgm_path}"
            )

        width_px, height_px, max_value, pixel_bytes = _load_pgm_grayscale_values(
            pgm_path
        )

    total_pixels = width_px * height_px
    white_threshold = max(1, math.floor(max_value * DEFAULT_WHITE_THRESHOLD_RATIO))

    nonwhite_count = 0
    top = height_px
    bottom = -1
    left = width_px
    right = -1

    for row_index in range(height_px):
        for col_index in range(width_px):
            pixel_index = row_index * width_px + col_index
            gray_value = _to_gray_value(pixel_bytes, pixel_index, max_value)
            if gray_value >= white_threshold:
                continue

            nonwhite_count += 1
            if row_index < top:
                top = row_index
            if row_index > bottom:
                bottom = row_index
            if col_index < left:
                left = col_index
            if col_index > right:
                right = col_index

    points_per_pixel = 72.0 / float(dpi)

    if nonwhite_count == 0:
        margin_top_pt = float(height_px) * points_per_pixel
        margin_bottom_pt = 0.0
        margin_left_pt = float(width_px) * points_per_pixel
        margin_right_pt = 0.0
        return (
            margin_top_pt,
            margin_bottom_pt,
            margin_left_pt,
            margin_right_pt,
            0.0,
            0.0,
            0.0,
        )

    nonwhite_height_px = (bottom - top) + 1
    nonwhite_width_px = (right - left) + 1
    margin_top_px = float(top)
    margin_bottom_px = float((height_px - 1) - bottom)
    margin_left_px = float(left)
    margin_right_px = float((width_px - 1) - right)

    margin_top_pt = margin_top_px * points_per_pixel
    margin_bottom_pt = margin_bottom_px * points_per_pixel
    margin_left_pt = margin_left_px * points_per_pixel
    margin_right_pt = margin_right_px * points_per_pixel
    vert_cov = float(nonwhite_height_px) / float(height_px)
    horiz_cov = float(nonwhite_width_px) / float(width_px)
    ink_ratio = float(nonwhite_count) / float(total_pixels)

    return (
        margin_top_pt,
        margin_bottom_pt,
        margin_left_pt,
        margin_right_pt,
        vert_cov,
        horiz_cov,
        ink_ratio,
    )


def _extract_bbox_metrics(pdf_path: Path) -> tuple[float, int]:
    """Extract vector-bbox coverage and text-block count from first PDF page.

    Purpose:
        Compute deterministic vector-space density metrics from `pdftotext`
        geometry output.
    Args:
        pdf_path: Absolute PDF path to analyze.
    Output:
        Returns `(bbox_cov, text_block_count)`.
    Raises:
        ReviewToolError: When bbox extraction or XML parsing fails.
    """

    bbox_command = [
        "pdftotext",
        "-f",
        "1",
        "-l",
        "1",
        "-bbox-layout",
        str(pdf_path),
        "-",
    ]

    try:
        completed_process = subprocess.run(
            bbox_command,
            check=False,
            text=True,
            capture_output=True,
        )
    except FileNotFoundError as exc:
        raise ReviewToolError("pdftotext not found in PATH") from exc

    if completed_process.returncode != 0:
        raise ReviewToolError(
            f"pdftotext -bbox-layout failed. stderr={completed_process.stderr.strip()}"
        )

    xml_payload = completed_process.stdout.strip()
    if xml_payload == "":
        raise ReviewToolError("Empty bbox-layout payload from pdftotext")

    try:
        root = element_tree.fromstring(xml_payload)
    except element_tree.ParseError as exc:
        raise ReviewToolError(f"Failed to parse bbox-layout XML: {exc}") from exc

    page_width = None
    page_height = None
    word_boxes: list[tuple[float, float, float, float]] = []
    text_block_count = 0

    for element in root.iter():
        local_name = _local_tag_name(element.tag)

        if local_name == "page" and page_width is None:
            page_width = float(element.attrib.get("width", "0") or "0")
            page_height = float(element.attrib.get("height", "0") or "0")

        if local_name == "block":
            text_block_count += 1

        if local_name != "word":
            continue

        try:
            x_min = float(element.attrib["xMin"])
            y_min = float(element.attrib["yMin"])
            x_max = float(element.attrib["xMax"])
            y_max = float(element.attrib["yMax"])
        except (KeyError, ValueError):
            continue

        if x_max <= x_min or y_max <= y_min:
            continue
        word_boxes.append((x_min, y_min, x_max, y_max))

    if page_width is None or page_height is None or page_width <= 0 or page_height <= 0:
        raise ReviewToolError("bbox-layout did not include valid page dimensions")

    if not word_boxes:
        return 0.0, text_block_count

    min_x = min(box[0] for box in word_boxes)
    min_y = min(box[1] for box in word_boxes)
    max_x = max(box[2] for box in word_boxes)
    max_y = max(box[3] for box in word_boxes)
    bbox_area = max((max_x - min_x) * (max_y - min_y), 0.0)
    page_area = page_width * page_height
    if page_area <= 0:
        return 0.0, text_block_count

    return bbox_area / page_area, text_block_count


def analyze_pdf_geometry_tool(
    *, pdf_path: str | Path, dpi: int = DEFAULT_GEOMETRY_DPI
) -> PdfGeometryMetrics:
    """Compute deterministic first-page geometry metrics for a PDF.

    Purpose:
        Provide layout and density metrics used by the review agent for visual
        quality judgments and candidate-versus-base comparisons.
    Args:
        pdf_path: PDF artifact path to analyze.
        dpi: Rasterization DPI used for margin and ink computations.
    Output:
        Returns validated `PdfGeometryMetrics` payload.
    Raises:
        FileNotFoundError: When the provided PDF path does not exist.
        ReviewToolError: When analysis commands fail.
    """

    resolved_pdf_path = Path(pdf_path).resolve()
    if not resolved_pdf_path.exists():
        raise FileNotFoundError(
            f"PDF not found for geometry analysis: {resolved_pdf_path}"
        )

    if dpi <= 0:
        raise ValueError(f"dpi must be > 0, got {dpi}")

    page_count = get_page_count_tool(pdf_path=resolved_pdf_path, log_path=None)
    page_width_pt, page_height_pt = _parse_pdf_page_size_pt(resolved_pdf_path)
    (
        margin_top_pt,
        margin_bottom_pt,
        margin_left_pt,
        margin_right_pt,
        vert_cov,
        horiz_cov,
        ink_ratio,
    ) = _compute_raster_metrics(pdf_path=resolved_pdf_path, dpi=dpi)
    bbox_cov, text_block_count = _extract_bbox_metrics(resolved_pdf_path)

    return PdfGeometryMetrics(
        page_count=page_count,
        page_width_pt=page_width_pt,
        page_height_pt=page_height_pt,
        margin_top_pt=margin_top_pt,
        margin_bottom_pt=margin_bottom_pt,
        margin_left_pt=margin_left_pt,
        margin_right_pt=margin_right_pt,
        vert_cov=vert_cov,
        horiz_cov=horiz_cov,
        ink_ratio=ink_ratio,
        bbox_cov=bbox_cov,
        text_block_count=text_block_count,
    )


def _load_geometry_model_from_json_file(json_path: Path) -> PdfGeometryMetrics:
    """Load a geometry metrics payload from a JSON file.

    Purpose:
        Reuse precomputed base metrics from disk when compare calls provide a
        cached JSON artifact path.
    Args:
        json_path: JSON file path containing geometry metrics fields.
    Output:
        Returns validated `PdfGeometryMetrics` instance.
    Raises:
        FileNotFoundError: When the JSON path does not exist.
        ReviewToolError: When JSON decoding fails.
    """

    if not json_path.exists():
        raise FileNotFoundError(f"Base geometry JSON not found: {json_path}")

    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReviewToolError(
            f"Could not decode base geometry JSON file {json_path}: {exc}"
        ) from exc

    if (
        isinstance(payload, dict)
        and "result" in payload
        and isinstance(payload["result"], dict)
    ):
        result_payload = payload["result"]
        if isinstance(result_payload.get("metrics"), dict):
            return PdfGeometryMetrics.model_validate(result_payload["metrics"])

    if isinstance(payload, dict) and isinstance(payload.get("metrics"), dict):
        return PdfGeometryMetrics.model_validate(payload["metrics"])

    return PdfGeometryMetrics.model_validate(payload)


def _classify_relative_profile(
    *,
    candidate_metrics: PdfGeometryMetrics,
    base_metrics: PdfGeometryMetrics,
) -> list[ReviewProfileLabel]:
    """Classify relative candidate-versus-base profile labels.

    Purpose:
        Translate raw metric deltas into stable profile labels that guide the
        agent's review/edit decisions.
    Args:
        candidate_metrics: Geometry metrics for the tailored candidate PDF.
        base_metrics: Geometry metrics for the baseline reference PDF.
    Output:
        Returns ordered list of profile labels.
    """

    labels: list[ReviewProfileLabel] = []

    if (
        candidate_metrics.ink_ratio + SPARSE_INK_DELTA < base_metrics.ink_ratio
        or candidate_metrics.vert_cov + SPARSE_VERT_COVERAGE_DELTA
        < base_metrics.vert_cov
    ):
        labels.append(ReviewProfileLabel.SPARSER_THAN_BASE)

    if (
        candidate_metrics.ink_ratio > base_metrics.ink_ratio + DENSE_INK_DELTA
        or candidate_metrics.vert_cov
        > base_metrics.vert_cov + DENSE_VERT_COVERAGE_DELTA
    ):
        labels.append(ReviewProfileLabel.DENSER_THAN_BASE)

    candidate_vertical_imbalance = abs(
        candidate_metrics.margin_top_pt - candidate_metrics.margin_bottom_pt
    )
    base_vertical_imbalance = abs(
        base_metrics.margin_top_pt - base_metrics.margin_bottom_pt
    )
    candidate_horizontal_imbalance = abs(
        candidate_metrics.margin_left_pt - candidate_metrics.margin_right_pt
    )
    base_horizontal_imbalance = abs(
        base_metrics.margin_left_pt - base_metrics.margin_right_pt
    )

    if (
        candidate_vertical_imbalance > base_vertical_imbalance + MARGIN_BALANCE_DELTA_PT
        or candidate_horizontal_imbalance
        > base_horizontal_imbalance + MARGIN_BALANCE_DELTA_PT
    ):
        labels.append(ReviewProfileLabel.MARGIN_IMBALANCE)

    if not labels:
        labels.append(ReviewProfileLabel.SIMILAR_TO_BASE)

    return labels


def compare_pdf_to_base_tool(
    *,
    candidate_pdf: str | Path,
    base_pdf: str | Path,
    base_geometry_json: str | Path | None = None,
) -> PdfComparisonResult:
    """Compare candidate PDF metrics to baseline PDF metrics.

    Purpose:
        Produce deterministic metric deltas and profile labels for review-agent
        quality judgments.
    Args:
        candidate_pdf: Candidate tailored PDF path.
        base_pdf: Base reference PDF path.
        base_geometry_json: Optional JSON path containing cached base metrics.
    Output:
        Returns validated `PdfComparisonResult` payload.
    Raises:
        ReviewToolError: When analysis or parsing fails.
    """

    candidate_metrics = analyze_pdf_geometry_tool(pdf_path=candidate_pdf)

    if base_geometry_json is not None:
        base_metrics = _load_geometry_model_from_json_file(
            Path(base_geometry_json).resolve()
        )
    else:
        base_metrics = analyze_pdf_geometry_tool(pdf_path=base_pdf)

    candidate_payload = candidate_metrics.model_dump()
    base_payload = base_metrics.model_dump()
    delta: dict[str, float] = {}

    for metric_name, candidate_value in candidate_payload.items():
        base_value = base_payload[metric_name]
        delta[metric_name] = float(candidate_value) - float(base_value)

    relative_profile = _classify_relative_profile(
        candidate_metrics=candidate_metrics,
        base_metrics=base_metrics,
    )

    return PdfComparisonResult(
        candidate_metrics=candidate_metrics,
        base_metrics=base_metrics,
        delta=delta,
        relative_profile=relative_profile,
    )


def analyze_latex_log_tool(*, log_path: str | Path) -> LatexLogAnalysis:
    """Analyze LaTeX log output and return structured warning/error counts.

    Purpose:
        Provide deterministic compile-quality signals for review decisions.
    Args:
        log_path: LaTeX `.log` file path to parse.
    Output:
        Returns validated `LatexLogAnalysis` payload.
    Raises:
        FileNotFoundError: When the provided log file does not exist.
    """

    resolved_log_path = Path(log_path).resolve()
    if not resolved_log_path.exists():
        raise FileNotFoundError(
            f"LaTeX log not found for analysis: {resolved_log_path}"
        )

    log_text = resolved_log_path.read_text(encoding="utf-8", errors="ignore")
    overfull_count = len(re.findall(r"Overfull \\hbox|Overfull \\vbox", log_text))
    underfull_count = len(re.findall(r"Underfull \\hbox|Underfull \\vbox", log_text))
    latex_errors = len(re.findall(r"^! ", log_text, flags=re.MULTILINE))
    warnings = len(re.findall(r"Warning", log_text))
    has_fatal_error = (
        "Fatal error occurred" in log_text
        or "Emergency stop" in log_text
        or latex_errors > 0
    )

    return LatexLogAnalysis(
        overfull_count=overfull_count,
        underfull_count=underfull_count,
        latex_errors=latex_errors,
        warnings=warnings,
        has_fatal_error=has_fatal_error,
    )


def extract_pdf_text_signals_tool(*, pdf_path: str | Path) -> PdfTextSignals:
    """Extract deterministic text-level signals from first-page PDF text.

    Purpose:
        Provide simple textual quality heuristics to complement geometry and log
        analysis signals during review.
    Args:
        pdf_path: PDF path to inspect.
    Output:
        Returns validated `PdfTextSignals` payload.
    Raises:
        FileNotFoundError: When the provided PDF path does not exist.
        ReviewToolError: When `pdftotext` fails.
    """

    resolved_pdf_path = Path(pdf_path).resolve()
    if not resolved_pdf_path.exists():
        raise FileNotFoundError(
            f"PDF not found for text extraction: {resolved_pdf_path}"
        )

    text_command = [
        "pdftotext",
        "-f",
        "1",
        "-l",
        "1",
        str(resolved_pdf_path),
        "-",
    ]

    try:
        completed_process = subprocess.run(
            text_command,
            check=False,
            text=True,
            capture_output=True,
        )
    except FileNotFoundError as exc:
        raise ReviewToolError("pdftotext not found in PATH") from exc

    if completed_process.returncode != 0:
        raise ReviewToolError(
            "pdftotext failed while extracting text signals. "
            f"stderr={completed_process.stderr.strip()}"
        )

    text_payload = completed_process.stdout
    lines = text_payload.splitlines()
    nonempty_lines = [line for line in lines if line.strip() != ""]
    words = re.findall(r"\b\w+\b", text_payload)
    bullet_line_count = len(
        [line for line in nonempty_lines if line.lstrip().startswith(("-", "*", "•"))]
    )

    return PdfTextSignals(
        text_length_chars=len(text_payload),
        word_count=len(words),
        nonempty_line_count=len(nonempty_lines),
        bullet_line_count=bullet_line_count,
    )


def write_review_report_tool(
    *,
    path: str | Path,
    report_payload: dict[str, object],
) -> str:
    """Validate and write the canonical review report JSON artifact.

    Purpose:
        Provide the strict completion handshake consumed by runtime and worker
        persistence logic.
    Args:
        path: Destination review-report JSON path.
        report_payload: Raw review report payload to validate and persist.
    Output:
        Returns absolute report path string.
    Raises:
        ValidationError: When report payload fails schema validation.
    """

    report_model = ReviewReport.model_validate(report_payload)
    report_path = Path(path).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        report_model.model_dump_json(indent=2),
        encoding="utf-8",
    )
    return str(report_path)


__all__ = [
    "DEFAULT_GEOMETRY_DPI",
    "ReviewToolError",
    "analyze_latex_log_tool",
    "analyze_pdf_geometry_tool",
    "compare_pdf_to_base_tool",
    "extract_pdf_text_signals_tool",
    "write_review_report_tool",
]
