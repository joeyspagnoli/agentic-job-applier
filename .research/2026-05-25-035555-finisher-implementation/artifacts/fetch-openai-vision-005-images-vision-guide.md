# Fetch 005 — Images and vision guide

**URL:** https://developers.openai.com/api/docs/guides/images-vision
**Date fetched:** 2026-05-25
**Extraction prompt:** complete Python example, messages shape, base64 vs URL, detail param, image token cost, SDK methods, preferred API for 2026

## Full extracted content

### API choice — Responses API is the 2026 preferred path

- **Chat Completions API (legacy but supported):** `client.chat.completions.create(...)`
- **Responses API (current preferred):** `client.responses.create(...)`

The doc positions the Responses API as the modern approach; it appears first in the overview and supports both image input AND image generation in a single API. Chat Completions remains supported for backwards compatibility.

### Message / input shape

**Chat Completions API:**
```python
messages=[{
    "role": "user",
    "content": [
        {"type": "text", "text": "what's in this image?"},
        {"type": "image_url", "image_url": {"url": "..."}}
    ]
}]
```

**Responses API:**
```python
input=[{
    "role": "user",
    "content": [
        {"type": "input_text", "text": "what's in this image?"},
        {"type": "input_image", "image_url": "..."}
    ]
}]
```

Key naming difference: `text` vs `input_text`, `image_url` (dict) vs `input_image` (with `image_url` as a string field).

### Image format options

**URL form:**
```python
{"type": "input_image", "image_url": "https://example.com/foo.jpg"}
```

**Base64 inline form:**
```python
{"type": "input_image", "image_url": f"data:image/png;base64,{base64_image}"}
```

Same data URI scheme works for both APIs.

### Detail parameter

| Level | Description |
|---|---|
| `low` | Fast, low-cost understanding when fine visual detail is not important |
| `high` | Standard high-fidelity image understanding |
| `original` | **Large, dense, spatially sensitive, or computer-use images** — recommended for click-accuracy on gpt-5.4 and successors |
| `auto` | Automatic detail selection |

### Image token cost (patch-based tokenization)

- Images are split into **32px × 32px patches**.
- Each patch counts as a token, multiplied by a **model-specific factor of 1.62–2.46**.
- "Image inputs are metered and charged in token units similar to text inputs" — i.e., images are billed at the standard text input rate of that model.
- A community thread surfaced at https://community.openai.com/t/gpt-5-mini-image-input-token-calculation-discrepancy-with-official-faq-formula/1344040 reports there has been some real-world drift from the documented formula; cost should be measured empirically once shipped.

## Cost estimate — 1024x1024 PNG screenshot

A 1024x1024 image at 32px patches = 32 patches × 32 patches = **1,024 patches**.

With a multiplier of ~2.0 (middle of the 1.62–2.46 range), that's roughly **~2,048 image input tokens**.

At gpt-5.4-mini input rate of $0.75/Mtok: ~2,048 × $0.75/1,000,000 = **~$0.0015 per screenshot** (a tenth of a cent).
At gpt-5-mini input rate of $0.25/Mtok: **~$0.0005 per screenshot**.
At gpt-5.4 input rate of $2.50/Mtok: **~$0.0051 per screenshot**.

These are dwarfed by the prompt+completion text token costs in a typical finisher turn.

`detail="original"` increases the patch count substantially for high-resolution images and should be expected to roughly double or triple the image-token cost. Reserve for cases where button localization actually requires it; default to `auto`.
