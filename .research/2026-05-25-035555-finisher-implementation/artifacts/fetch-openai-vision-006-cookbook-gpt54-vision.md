# Fetch 006 — OpenAI Cookbook: Getting the Most out of GPT-5.4 for Vision

**URL:** https://developers.openai.com/cookbook/examples/multimodal/document_and_multimodal_understanding_tips
**Date fetched:** 2026-05-25

## Full extracted content

### Minimal Responses API example

```python
response = client.responses.create(
    model="gpt-5.4",
    input=[
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "Extract the total amount due."},
                {
                    "type": "input_image",
                    "image_url": "data:image/png;base64,...",
                    "detail": "auto",
                },
            ],
        }
    ],
)
```

**Setup:**
- `export OPENAI_API_KEY="your_api_key_here"`
- `pip install --upgrade openai pillow`

### Detail recommendation for click-accuracy / localization

The cookbook explicitly recommends **`detail="original"`** when:
- Text is tiny
- Handwritten content
- Scan is low-quality
- Localization / bounding boxes / computer-use tasks

For dense forms with small buttons, `detail="original"` is the right default.

### Tool calling combined with image input

The cookbook shows a Code Interpreter example combined with vision (different tool than function calling, but proves multi-tool turns with images work):

```python
tools=[
    {
        "type": "code_interpreter",
        "container": {"type": "auto", "memory_limit": "4g", "file_ids": [uploaded_file.id]},
    }
]
```

Guidance: *"Use Code Interpreter for multi-pass inspection and bounding-box [tasks], particularly when the page is dense and evidence is spread across multiple regions."*

This implies that **mixing custom function tools with image input on the same turn is supported by gpt-5.4 / gpt-5.4-mini** — tool calling and vision are not mutually exclusive.

### Localization contract guidance

> "For localization tasks (including bounding boxes), provide access to code interpreter as well as a strict coordinate contract like `[x_min, y_min, x_max, y_max]`"

Implication for our finisher: if we want the model to point at a specific clickable element from a screenshot, define a strict tool schema with normalized 0–1 coordinates or pixel coordinates, and pass the screenshot at `detail="original"`.
