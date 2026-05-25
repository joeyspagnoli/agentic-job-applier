"""Structural assertions on the rendered apply-finisher system prompt.

Locks down the XML-tag layout, the verified-CLI field-table entries,
and the mandatory contracts so a future edit can't silently drop a
load-bearing section. None of these tests touch the LLM — they only
inspect the rendered string.
"""

from __future__ import annotations

import pytest

from src.agents.apply_finisher.prompts import BASE, build_system_prompt

# XML sections the base prompt MUST contain. Adding a tag here forces
# the next prompt revision to keep it.
_REQUIRED_XML_TAGS: tuple[str, ...] = (
    "<role>",
    "<objective>",
    "<execution_contract>",
    "<tool_catalog>",
    "<step_patterns>",
    "<verification_contract>",
    "<tier_model>",
    "<safety>",
    "<stop_conditions>",
)

# Tool names the prompt MUST teach. If a name changes in tools.py, the
# prompt rewrite must follow.
_REQUIRED_TOOL_NAMES: tuple[str, ...] = (
    "agent_browser(args)",
    "open_combobox(field_id)",
    "type_combobox_filter(field_id, text)",
    "pick_option(option_text",
    "verify_combobox_filled(field_id)",
    "dispatch_async_typeahead_query(field_id, query)",
    "lookup_cached_answer(label)",
    "defer(ref",
    "flag_for_verify(ref",
    "complete_apply",
)

# Label-keyed semantic rows the Greenhouse fragment must teach (one
# per question class we've seen in the wild). Keyed by a substring of
# the label and a substring of the verified target option text so the
# tests work on ANY Greenhouse posting, not just Cloudflare's question
# IDs.
_GREENHOUSE_LABEL_SEMANTICS: tuple[tuple[str, str], ...] = (
    ("country", "United States +1"),
    ("city", "candidate-location"),
    ("relocate", "I am willing to relocate"),
    ("sponsorship", "No"),
    ("enrolled", "Yes"),
    ("degree", "Bachelor's"),
    ("start", "Need to return to school and available upon graduation"),
    ("Python", "Yes"),
)


@pytest.mark.parametrize("tag", _REQUIRED_XML_TAGS)
def test_base_prompt_contains_required_xml_tag(tag: str) -> None:
    """Each required XML section opener appears in the base prompt."""

    assert tag in BASE, f"missing required XML tag {tag!r}"


@pytest.mark.parametrize("tool_signature_excerpt", _REQUIRED_TOOL_NAMES)
def test_base_prompt_names_every_registered_tool(
    tool_signature_excerpt: str,
) -> None:
    """Every tool the model can call appears in the prompt's tool_catalog."""

    assert tool_signature_excerpt in BASE, (
        f"prompt missing tool signature snippet {tool_signature_excerpt!r}"
    )


def test_execution_contract_locks_one_tool_call_per_turn() -> None:
    """The execution_contract enforces sequential tool calls."""

    assert "ONE tool call per assistant turn" in BASE


def test_verification_contract_requires_verify_helper() -> None:
    """The verification_contract names the verifier tool by signature."""

    assert "verify_combobox_filled(field_id)" in BASE
    assert "EMPTY" in BASE


def test_safety_section_forbids_submit_click() -> None:
    """Safety section enumerates the submit-button accessible-name prefixes."""

    for prefix in ("Submit", "Apply", "Send"):
        assert prefix in BASE, f"safety section missing forbidden prefix {prefix!r}"


def test_prompt_carries_no_placeholder_tokens() -> None:
    """No `<FIELD_ID...>`-style placeholders leak into the rendered prompt."""

    for bad in (
        "<FIELD_ID>",
        "<FIELD_ID_HERE>",
        "<field_id_here>",
        "<COUNTRY_REF>",
        "<OPTION_REF>",
        "<PHONE_REF>",
    ):
        assert bad not in BASE, (
            f"prompt still contains placeholder {bad!r} that gpt-5 treats literally"
        )


@pytest.mark.parametrize(("label_substr", "target_excerpt"), _GREENHOUSE_LABEL_SEMANTICS)
def test_greenhouse_label_semantics_row_present(
    label_substr: str, target_excerpt: str
) -> None:
    """Greenhouse fragment maps each known label semantic to a verified target."""

    rendered = build_system_prompt("greenhouse")
    assert label_substr in rendered, (
        f"missing label semantic substring {label_substr!r}"
    )
    assert target_excerpt in rendered, (
        f"missing target excerpt {target_excerpt!r} for label {label_substr!r}"
    )


def test_greenhouse_fragment_does_not_hardcode_cloudflare_ids() -> None:
    """The classifier teaches by label semantics, not Cloudflare-only IDs.

    The Cloudflare worked-example block names question_66747918 as a
    concrete analogy, but the primary classifier (which the model
    consults for every field) MUST be label-driven so the prompt
    works on any Greenhouse posting whose question_NNNNNNN ids
    differ.
    """

    rendered = build_system_prompt("greenhouse")
    cloudflare_only_ids = (
        "question_66747919",
        "question_66747921",
        "question_66747923",
        "question_66747924",
        "question_66747925",
    )
    for ghid in cloudflare_only_ids:
        assert ghid not in rendered, (
            f"prompt still hardcodes Cloudflare-only id {ghid!r} — "
            "must be classified by label semantics instead"
        )


def test_greenhouse_eeo_block_present() -> None:
    """Greenhouse fragment teaches the EEO fieldset is Tier 1, not Tier 3."""

    rendered = build_system_prompt("greenhouse")
    assert "<greenhouse_eeo>" in rendered
    assert "apply_prefs.eeo_defaults" in rendered


def test_async_typeahead_block_teaches_native_value_setter_route() -> None:
    """Async typeahead block names the helper that wraps the native setter."""

    assert "<async_typeahead>" in BASE
    assert "dispatch_async_typeahead_query" in BASE


def test_country_phone_pair_block_uses_verified_option_text() -> None:
    """Country/phone block references the verified `"United States +1"` label."""

    assert "<country_phone_pair>" in BASE
    assert "United States +1" in BASE


def test_built_prompt_under_target_length() -> None:
    """Composed prompt stays under the ~150-line target so the model can read it."""

    rendered = build_system_prompt("greenhouse")
    # 200 is the hard upper bound; aim was 150 for the base. Anything beyond
    # 200 means the prompt is bloating again.
    assert rendered.count("\n") < 200, (
        f"rendered prompt is {rendered.count(chr(10))} lines; bloat regression"
    )
