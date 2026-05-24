"""Pydantic models for the deterministic bullet manifest.

Purpose:
    Define the wire shape of `build_bullet_manifest()`'s output. The
    manifest is what the tailor LLM sees (filtered down to experience +
    projects entries) and what the patcher uses to splice byte-offset
    replacements back into the user's `.tex`.

Two consumers share these models — the locator (which produces them)
and the validator (which embeds a preview into `ValidatorReport`).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class BulletItem(BaseModel):
    """One bullet in an experience or project entry.

    Purpose:
        Carry the stable identifier and byte span the patcher splices
        into, plus the original body text so the tailor LLM can decide
        whether to keep or rewrite the bullet.
    Args:
        id: Stable bullet identifier (slug).
        text: Original body text inside the macro arg.
        byte_start: Byte offset of body start (inclusive) in the
            source `.tex`.
        byte_end: Byte offset of body end (exclusive) in the source
            `.tex`.
    Output:
        Pydantic model instance carrying the four fields above.
    """

    id: str = Field(description="Stable bullet identifier (slug).")
    text: str = Field(description="Original body text inside the macro arg.")
    byte_start: int = Field(description="Byte offset of body start (inclusive).")
    byte_end: int = Field(description="Byte offset of body end (exclusive).")


class BulletEntry(BaseModel):
    """One role or project — the container for a bullet group.

    Purpose:
        Group bullets under the entry header the LLM should treat as
        ground truth for what the role is about. `role_context` is
        intentionally the literal header line so we never lossy-summarize
        the user's own wording before showing it to the model.
    """

    id: str = Field(description="Stable entry identifier (slug).")
    role_context: str = Field(
        description="Literal entry-header line; never LLM-summarized.",
    )
    header_byte_start: int = Field(
        description="Byte offset of the entry-header line start.",
    )
    bullets: list[BulletItem] = Field(default_factory=list)


class BulletSection(BaseModel):
    """One experience or projects section.

    Purpose:
        Carry the section heading and its entries through the manifest.
        Sections of any other kind (skills, education, summary, etc.)
        do not appear in the manifest at all — the locator filters them
        out before emitting.
    """

    id: str = Field(description="Stable section identifier.")
    kind: Literal["experience", "projects"] = Field(
        description="Semantic section kind for tailor routing.",
    )
    heading: str = Field(
        description="Original \\section{...} heading text, stripped.",
    )
    entries: list[BulletEntry] = Field(default_factory=list)


class BulletManifest(BaseModel):
    """Full deterministic manifest emitted by the locator.

    Purpose:
        Hand the tailor LLM the exact bullets-with-context it is allowed
        to rewrite, plus the byte offsets the patcher needs. Same `.tex`
        in → same manifest out; IDs are stable within a single `.tex`
        version but never persisted across user edits.
    """

    sections: list[BulletSection] = Field(default_factory=list)

    def bullet_count(self) -> int:
        """Return the total number of bullets across all sections.

        Purpose:
            Convenience helper for the audit script + validator preview
            so we don't repeat the nested sum at every call site.
        Output:
            Integer count of bullets in the manifest.
        """

        return sum(
            len(entry.bullets) for section in self.sections for entry in section.entries
        )

    def entry_count(self) -> int:
        """Return the total number of entries across all sections.

        Purpose:
            Same role as `bullet_count` — surface a small computed view
            without repeating the comprehension.
        Output:
            Integer count of entries in the manifest.
        """

        return sum(len(section.entries) for section in self.sections)


__all__ = [
    "BulletEntry",
    "BulletItem",
    "BulletManifest",
    "BulletSection",
]
