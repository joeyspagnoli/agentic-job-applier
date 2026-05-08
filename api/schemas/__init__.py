"""Pydantic request/response models for the API surface.

Schemas are split by domain into submodules:
- `common`: cross-cutting request payloads (reviewer actions, YAML uploads,
  budget, API key, service tier, AI provider, manual job import).
- `candidate`: structured candidate-profile payloads used by the guided
  settings forms.
"""

from __future__ import annotations
