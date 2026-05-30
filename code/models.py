from __future__ import annotations

import re
import time
import json
import unicodedata
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

@dataclass
class Fact:
    key: str
    label: str
    clean_value: str  # 用户应该看到的正确关键信息
    decoy_value: str  # 想喂给 agent 的错误关键信息
    section: str
    match_mode: str = "strict"
    attackable: bool = True
    expected_aliases: List[str] = field(default_factory=list)
    decoy_aliases: List[str] = field(default_factory=list)
    why_high_value: str = ""
    agent_need: str = ""
    position_hint: str = ""

    def correct_candidates(self) -> List[str]:
        return [self.clean_value, *self.expected_aliases]

    def decoy_candidates(self) -> List[str]:
        return [self.decoy_value, *self.decoy_aliases]


@dataclass
class Scenario:
    slug: str
    page_title: str
    hero_title: str
    task_description: str
    actual_vulnerability: str
    hero_subtitle: str
    intro_lines: List[str]
    form_heading: str
    form_label: str
    input_placeholder: str
    button_label: str
    footer_note: str
    facts: List[Fact]
    template: str = "generic"  # "generic" or "corpnet_dashboard"


@dataclass
class ExperimentSpec:
    name: str
    render_strategy: str
    poison_method: str = "none"
    description: str = ""


@dataclass
class RenderedFact:
    fact: Fact
    html_value: str
    source_text: str
    visible_text: str
    strategy_name: str
    extra_css_rules: List[str] = field(default_factory=list)
    needs_js_rewrite: bool = False
    poison_method: str = "none"
    source_basis: str = "clean"
    technique_summary: str = ""


@dataclass
class EvaluationRow:
    key: str
    label: str
    correct_value: str
    decoy_value: str
    status: str
    matched_correct: List[str] = field(default_factory=list)
    matched_decoy: List[str] = field(default_factory=list)
    defense_effect: str = ""

