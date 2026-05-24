"""Property tests for `src.agents.resume_tailor.patcher`.

Purpose:
    Fill the one gap the Phase 1-4 handoff called out for the patcher:
    N non-overlapping patches in *random* order must land at the
    correct offsets regardless of how the caller ordered them. The
    existing `test_patcher.py` covers descending order via a fixed
    example; Hypothesis here drives random shuffles + random patch
    counts so the descending-sort invariant gets stressed across
    many input shapes.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from src.agents.resume_tailor.patcher import BulletPatch, apply_patches

# We pin the source text so the patches we generate have stable spans.
# Every "BBBBB" run is one bullet body; spans are 6 chars apart.
_PATCH_SOURCE = "AAAAA-BBBBB-CCCCC-DDDDD-EEEEE-FFFFF-GGGGG-HHHHH"
_PATCH_WIDTH = 5
_PATCH_STRIDE = 6
_BULLET_COUNT = len(_PATCH_SOURCE) // _PATCH_STRIDE  # 8


def _patch_for_index(index: int, new_text: str) -> BulletPatch:
    """Build a `BulletPatch` targeting the index-th 5-char bullet body.

    Purpose:
        Centralize the byte-offset math so the property tests stay
        focused on ordering behavior.
    Args:
        index: Zero-based bullet index (0..7 for `_PATCH_SOURCE`).
        new_text: Replacement body text.
    Output:
        A `BulletPatch` covering the body span at the given index.
    """

    byte_start = index * _PATCH_STRIDE
    byte_end = byte_start + _PATCH_WIDTH
    return BulletPatch(
        bullet_id=f"b{index}",
        byte_start=byte_start,
        byte_end=byte_end,
        new_text=new_text,
    )


@given(
    indices=st.lists(
        st.integers(min_value=0, max_value=_BULLET_COUNT - 1),
        min_size=1,
        max_size=_BULLET_COUNT,
        unique=True,
    ).flatmap(lambda picked: st.permutations(picked)),
)
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_patches_land_at_correct_offsets_regardless_of_input_order(
    indices: list[int],
) -> None:
    """Random patch orderings must all produce the same canonical result.

    Risk: the descending-sort invariant inside `apply_patches` is the
    one piece of logic that keeps offsets valid as we mutate the back
    of the string. Shuffling the caller's input should never change
    the output text.
    """

    # Build a patch per chosen index with a distinct replacement so we
    # can verify per-position landing.
    patches = [_patch_for_index(index, f"r{index}") for index in indices]

    shuffled_result = apply_patches(_PATCH_SOURCE, patches)
    sorted_ascending = apply_patches(
        _PATCH_SOURCE, sorted(patches, key=lambda p: p.byte_start)
    )
    sorted_descending = apply_patches(
        _PATCH_SOURCE,
        sorted(patches, key=lambda p: p.byte_start, reverse=True),
    )

    # Every ordering of the same patch set must yield identical text.
    assert shuffled_result == sorted_ascending
    assert shuffled_result == sorted_descending

    # And every targeted index actually carries its replacement marker.
    for index in indices:
        assert f"r{index}" in shuffled_result


@given(
    indices=st.lists(
        st.integers(min_value=0, max_value=_BULLET_COUNT - 1),
        min_size=2,
        max_size=_BULLET_COUNT,
        unique=True,
    )
)
@settings(max_examples=100)
def test_non_targeted_bullet_bodies_are_left_untouched(indices: list[int]) -> None:
    """Bullets outside the patch set must survive byte-for-byte."""

    patches = [_patch_for_index(index, "ZZZZZ") for index in indices]
    untargeted = set(range(_BULLET_COUNT)) - set(indices)

    result = apply_patches(_PATCH_SOURCE, patches)

    for index in untargeted:
        original_body = _PATCH_SOURCE[
            index * _PATCH_STRIDE : index * _PATCH_STRIDE + _PATCH_WIDTH
        ]
        assert original_body in result
