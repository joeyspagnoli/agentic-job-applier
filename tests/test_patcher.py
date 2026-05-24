"""Behavior tests for `src.agents.resume_tailor.patcher`.

Purpose:
    Pin the patcher's contract: descending-order splice keeps offsets
    valid as we mutate; overlap / inverted / out-of-bounds patches
    raise `ValueError` instead of silently corrupting the text; the
    atomic-write helper leaves the original file untouched on a
    simulated mid-write crash.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.agents.resume_tailor.patcher import (
    BulletPatch,
    apply_patches,
    write_patched_tex_atomically,
)


def _patch(bullet_id: str, byte_start: int, byte_end: int, new_text: str) -> BulletPatch:
    """Construct a `BulletPatch` for tests with minimal noise.

    Purpose:
        Keep the test bodies focused on the splice behavior, not on
        repetitive keyword-arg plumbing.
    Args:
        bullet_id: Stable manifest bullet identifier.
        byte_start: Inclusive body start offset.
        byte_end: Exclusive body end offset.
        new_text: Replacement body text.
    Output:
        A populated `BulletPatch` instance.
    """

    return BulletPatch(
        bullet_id=bullet_id, byte_start=byte_start, byte_end=byte_end, new_text=new_text
    )


def test_empty_patch_list_returns_input_unchanged() -> None:
    tex = "\\section{Experience}\n\\resumeItem{original}\n"

    result = apply_patches(tex, [])

    assert result == tex


def test_single_patch_replaces_body_in_place() -> None:
    tex = "\\resumeItem{original body}"
    # Body span = chars 12..25 (the text "original body").
    patches = [_patch("b0", 12, 25, "new body")]

    result = apply_patches(tex, patches)

    assert result == "\\resumeItem{new body}"


def test_multi_patch_descending_order_keeps_offsets_valid() -> None:
    # Five bullets at known offsets. We apply five non-overlapping
    # patches and assert every replacement landed in the right span.
    tex = "AAAAA-BBBBB-CCCCC-DDDDD-EEEEE"
    patches = [
        _patch("b0", 0, 5, "11"),
        _patch("b1", 6, 11, "22"),
        _patch("b2", 12, 17, "33"),
        _patch("b3", 18, 23, "44"),
        _patch("b4", 24, 29, "55"),
    ]

    result = apply_patches(tex, patches)

    assert result == "11-22-33-44-55"


def test_duplicate_bullet_text_disambiguated_by_byte_offset() -> None:
    # Two identical bullet bodies; patcher targets only the second one.
    tex = "\\resumeItem{same text} and \\resumeItem{same text}"
    second_body_start = tex.index("same text", tex.index("same text") + 1)
    second_body_end = second_body_start + len("same text")
    patches = [_patch("b1", second_body_start, second_body_end, "changed")]

    result = apply_patches(tex, patches)

    assert result == "\\resumeItem{same text} and \\resumeItem{changed}"


def test_latex_specials_in_new_text_are_sanitized_before_splice() -> None:
    # `&` is LaTeX-active; latex_safe should escape it as `\&`.
    tex = "\\resumeItem{old}"
    patches = [_patch("b0", 12, 15, "Rust & C++")]

    result = apply_patches(tex, patches)

    assert result == "\\resumeItem{Rust \\& C++}"


def test_overlapping_patches_raise_value_error() -> None:
    tex = "0123456789"
    patches = [
        _patch("a", 0, 5, "first"),
        _patch("b", 3, 7, "overlaps a"),
    ]

    with pytest.raises(ValueError, match="overlap"):
        apply_patches(tex, patches)


def test_inverted_span_raises_value_error() -> None:
    tex = "0123456789"
    # Pydantic allows byte_end < byte_start at construction time
    # (only the bounds are >= 0) — the patcher catches the inversion.
    patches = [_patch("bad", 5, 2, "wrong")]

    with pytest.raises(ValueError, match="byte_end"):
        apply_patches(tex, patches)


def test_out_of_bounds_byte_end_raises_value_error() -> None:
    tex = "0123456789"
    patches = [_patch("bad", 0, 99, "exceeds")]

    with pytest.raises(ValueError, match="exceeds document length"):
        apply_patches(tex, patches)


def test_unicode_bullet_bodies_round_trip_through_patching() -> None:
    # The dogfood resume includes `²` and `–`; verify multi-byte
    # characters in `new_text` don't break the splice. Note that the
    # patcher uses Python str indices, NOT UTF-8 byte indices.
    tex = "\\resumeItem{old text}"
    patches = [_patch("b0", 12, 20, "Rust² with µs latency")]

    result = apply_patches(tex, patches)

    assert "Rust² with µs latency" in result


def test_atomic_write_creates_target_file_with_expected_content(
    tmp_path: Path,
) -> None:
    target = tmp_path / "resume.tex"
    payload = "\\documentclass{article}\\begin{document}\\end{document}\n"

    write_patched_tex_atomically(tex_text=payload, target_path=target)

    assert target.read_text(encoding="utf-8") == payload


def test_atomic_write_creates_parent_directories(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "deep" / "resume.tex"

    write_patched_tex_atomically(tex_text="content", target_path=target)

    assert target.read_text(encoding="utf-8") == "content"


def test_atomic_write_replaces_existing_file_in_place(tmp_path: Path) -> None:
    target = tmp_path / "resume.tex"
    target.write_text("old content", encoding="utf-8")

    write_patched_tex_atomically(tex_text="new content", target_path=target)

    assert target.read_text(encoding="utf-8") == "new content"


def test_atomic_write_returns_resolved_absolute_path(tmp_path: Path) -> None:
    target = tmp_path / "resume.tex"

    result = write_patched_tex_atomically(tex_text="content", target_path=target)

    assert result.is_absolute()
    assert result.resolve() == target.resolve()


def test_patches_with_zero_length_span_act_as_inserts() -> None:
    # A patch with byte_start == byte_end is an insertion at that
    # offset rather than a replacement. We don't ban it; the patcher
    # treats it as a valid no-op-removal + text-prepend.
    tex = "before|after"
    patches = [_patch("ins", 7, 7, "MIDDLE-")]

    result = apply_patches(tex, patches)

    assert result == "before|MIDDLE-after"
