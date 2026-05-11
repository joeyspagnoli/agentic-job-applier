"""Read and write the YAML-canonical resume document.

Purpose:
    Provide deterministic YAML loading/saving helpers with schema validation so
    runtime tools can fail fast on malformed resume artifacts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .schemas import ResumeContent
from .schemas import validate_locked_structure


def load_resume_yaml(path: str | Path) -> ResumeContent:
    """Load, parse, and validate a canonical resume YAML file.

    Purpose:
        Give runtime tools one strict entry point for reading resume content so
        schema and lock issues are surfaced before rendering or compile steps.
    Args:
        path: Filesystem path to the canonical YAML resume file.
    Output:
        Returns a validated `ResumeContent` object.
    Raises:
        FileNotFoundError: When the YAML file does not exist.
        ValueError: When the file does not contain a mapping root or violates
            schema/lock requirements.
    """

    yaml_path = Path(path)
    if not yaml_path.exists():
        raise FileNotFoundError(f"Resume YAML file not found: {yaml_path}")

    with open(yaml_path, "r", encoding="utf-8") as yaml_file:
        loaded_data = yaml.safe_load(yaml_file)

    if not isinstance(loaded_data, dict):
        raise ValueError("Resume YAML root must be a mapping")

    resume_content = ResumeContent.model_validate(loaded_data)
    validate_locked_structure(resume_content)
    return resume_content


def save_resume_yaml(
    *,
    path: str | Path,
    resume_content: ResumeContent,
) -> None:
    """Persist a canonical resume object to YAML with stable formatting.

    Purpose:
        Keep YAML writes deterministic for git diffs and tool interoperability.
    Args:
        path: Destination YAML filesystem path.
        resume_content: Canonical resume model to serialize.
    Output:
        Returns `None` after writing YAML content to disk.
    """

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    dumped_data = resume_content.model_dump(mode="json")
    with open(output_path, "w", encoding="utf-8") as yaml_file:
        yaml.safe_dump(
            dumped_data,
            yaml_file,
            sort_keys=False,
            allow_unicode=False,
            width=120,
        )


def load_resume_yaml_dict(path: str | Path) -> dict[str, Any]:
    """Load canonical YAML and return it as a JSON-serializable dictionary.

    Purpose:
        Support tool-style responses that need plain mappings instead of typed
        Pydantic models.
    Args:
        path: Filesystem path to the canonical YAML file.
    Output:
        Returns a dictionary representation of the validated resume content.
    """

    resume_content = load_resume_yaml(path)
    return resume_content.model_dump(mode="json")


def save_resume_yaml_dict(*, path: str | Path, payload: dict[str, Any]) -> None:
    """Validate and persist a dictionary payload as canonical resume YAML.

    Purpose:
        Provide a safe write path for external tools that submit plain JSON/YAML
        mappings rather than typed `ResumeContent` objects.
    Args:
        path: Destination YAML filesystem path.
        payload: Mapping payload representing a full resume document.
    Output:
        Returns `None` after validating and writing the payload.
    """

    resume_content = ResumeContent.model_validate(payload)
    validate_locked_structure(resume_content)
    save_resume_yaml(path=path, resume_content=resume_content)
