"""Payload registry — maps scenario+experiment to HTML file + ground truth facts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from .models import Fact

_REGISTRY_PATH = Path(__file__).resolve().parent / "payload_test" / "registry.json"
_PAYLOAD_DIR = Path(__file__).resolve().parent / "payload_test"

_registry_cache: Optional[dict] = None


def _load() -> dict:
    global _registry_cache
    if _registry_cache is None:
        with open(_REGISTRY_PATH, encoding="utf-8") as f:
            _registry_cache = json.load(f)
    return _registry_cache


def get_payload_path(scenario: str, experiment: str) -> Optional[Path]:
    """Return absolute path to the HTML payload file, or None."""
    reg = _load()
    try:
        relative = reg[scenario]["experiments"][experiment]["html_file"]
        return _PAYLOAD_DIR / relative.split("/", 1)[1] if "/" in relative else _PAYLOAD_DIR / relative
    except KeyError:
        return None


def get_pure_page_path(scenario: str) -> Optional[Path]:
    """Return absolute path to the clean reference page, or None."""
    reg = _load()
    try:
        relative = reg[scenario]["page_pure"]
        return _PAYLOAD_DIR / relative.split("/", 1)[1] if "/" in relative else _PAYLOAD_DIR / relative
    except KeyError:
        return None


def get_facts(scenario: str, experiment: str) -> List[Fact]:
    """Return ground-truth Fact objects for a scenario+experiment."""
    reg = _load()
    facts_data = reg[scenario]["experiments"][experiment]["facts"]
    return [Fact(**f) for f in facts_data]


def list_available() -> Dict[str, List[str]]:
    """Return {scenario_slug: [experiment_names]} for all registered payloads."""
    reg = _load()
    return {s: list(data["experiments"].keys()) for s, data in reg.items()}


def list_scenarios() -> List[str]:
    return list(_load().keys())


def has_payload(scenario: str, experiment: str) -> bool:
    reg = _load()
    return scenario in reg and experiment in reg[scenario].get("experiments", {})
