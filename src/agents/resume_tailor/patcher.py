"""Byte-offset bullet patcher for the tailor pipeline.

Purpose:
    Take a list of `(byte_start, byte_end, new_text)` triples produced
    from a `BulletManifest` + tailor LLM output, and splice them into
    the user's `.tex` in-memory. Applies patches in **descending
    `byte_start` order** so earlier offsets remain valid as we mutate
    the back half of the string. Atomic file-write helper mirrors the
    pattern used by `compile_resume_tex`.

This module is the only place that mutates a copy of `config/resume.tex`
in the tailor flow. The on-disk file is never edited directly — the
pipeline writes the patched text to a temp file, runs tectonic against
it, then `os.replace`s into the per-run artifact dir.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from pydantic import BaseModel, Field

from .latex_sanitize import latex_safe


class BulletPatch(BaseModel):
    """One bullet body replacement requested by the pipeline.

    Purpose:
        Wire shape that pairs the manifest's byte span with the LLM's
        replacement text. The pipeline resolves `bullet_id` to
        `(byte_start, byte_end)` via the manifest before constructing
        this — the patcher itself is offset-only.
    Args:
        bullet_id: Stable manifest identifier for traceability.
        byte_start: Inclusive start of the body span to replace.
        byte_end: Exclusive end of the body span to replace.
        new_text: Replacement body text. Sanitized by `latex_safe`
            inside `apply_patches` before splicing.
    Output:
        Pydantic model carrying the four fields above.
    """

    bullet_id: str = Field(description="Stable manifest bullet ID.")
    byte_start: int = Field(ge=0, description="Body start offset (inclusive).")
    byte_end: int = Field(ge=0, description="Body end offset (exclusive).")
    new_text: str = Field(description="Raw LLM replacement body text.")


def apply_patches(tex_text: str, patches: list[BulletPatch]) -> str:
    """Splice every patch into `tex_text` and return the result.

    Purpose:
        Mutate the source text in-memory so the pipeline can recompile
        the patched variant without touching the on-disk `.tex`. Each
        patch's `new_text` is run through `latex_safe` first to escape
        any bare LaTeX-active characters the LLM emitted.
    Args:
        tex_text: Full text of the user's `.tex`.
        patches: Unordered list of `BulletPatch`. Empty list is a no-op.
    Output:
        The post-splice `.tex` text. Returns `tex_text` unchanged when
        `patches` is empty.
    Raises:
        ValueError: When two patches overlap, or when a patch span is
            inside-out (`byte_end < byte_start`), or when offsets fall
            outside the document. These would silently corrupt the
            text, so we fail loud instead.
    """

    if not patches:
        return tex_text

    sorted_patches = _validate_and_sort_patches(tex_text=tex_text, patches=patches)

    result = tex_text
    for patch in sorted_patches:
        sanitized = latex_safe(patch.new_text)
        result = result[: patch.byte_start] + sanitized + result[patch.byte_end :]

    return result


def _validate_and_sort_patches(
    *,
    tex_text: str,
    patches: list[BulletPatch],
) -> list[BulletPatch]:
    """Validate patch bounds + ordering, return desc-sorted copy.

    Purpose:
        Catch overlap / inverted-span / out-of-bounds patches at the
        patcher boundary so the pipeline gets a deterministic error
        instead of a silently truncated `.tex`. Sorting descending by
        `byte_start` keeps earlier offsets valid as we mutate the back.
    Args:
        tex_text: Full source text — used for bounds checks only.
        patches: Caller-provided patches.
    Output:
        New list, sorted by `byte_start` descending.
    Raises:
        ValueError: see `apply_patches`.
    """

    document_length = len(tex_text)
    for patch in patches:
        if patch.byte_end < patch.byte_start:
            raise ValueError(
                f"Patch {patch.bullet_id!r} has byte_end ({patch.byte_end}) "
                f"< byte_start ({patch.byte_start})"
            )
        if patch.byte_end > document_length:
            raise ValueError(
                f"Patch {patch.bullet_id!r} byte_end ({patch.byte_end}) "
                f"exceeds document length ({document_length})"
            )

    ascending_patches = sorted(patches, key=lambda p: p.byte_start)
    for previous_patch, next_patch in zip(ascending_patches, ascending_patches[1:]):
        if next_patch.byte_start < previous_patch.byte_end:
            raise ValueError(
                f"Patches overlap: {previous_patch.bullet_id!r} "
                f"({previous_patch.byte_start}, {previous_patch.byte_end}) and "
                f"{next_patch.bullet_id!r} "
                f"({next_patch.byte_start}, {next_patch.byte_end})"
            )

    return sorted(patches, key=lambda p: p.byte_start, reverse=True)


def write_patched_tex_atomically(
    *,
    tex_text: str,
    target_path: Path | str,
) -> Path:
    """Write `tex_text` to `target_path` atomically via temp + os.replace.

    Purpose:
        Mirror the compiler's atomic-rename pattern so a crash mid-write
        can't leave a half-written `.tex` for the next tailor run to
        pick up. The pipeline uses this for the patched-variant write
        before invoking tectonic.
    Args:
        tex_text: Final patched text to write.
        target_path: Destination path. Parent directories are created
            as needed.
    Output:
        Resolved absolute path of the written file.
    """

    target = Path(target_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    # NamedTemporaryFile + os.replace pattern: write to the same
    # directory so `os.replace` is a same-filesystem rename (atomic on
    # POSIX). `delete=False` lets us close the handle before the rename.
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
        delete=False,
    ) as temp_file:
        temp_file.write(tex_text)
        temp_path = Path(temp_file.name)

    os.replace(temp_path, target)
    return target


__all__ = [
    "BulletPatch",
    "apply_patches",
    "write_patched_tex_atomically",
]
