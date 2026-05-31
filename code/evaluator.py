from __future__ import annotations

import json
import re
import time
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .models import Fact, EvaluationRow, ExperimentSpec
from .prompts import LLM_JUDGE_PROMPT, INPUT_PARSING_INIT, PARSER_USER_PROMPT_TEMPLATE, RETRY_PARSER_USER_PROMPT_TEMPLATE
from .config import CONTROL_AND_FORMAT_CHARS
def normalize_for_match(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = "".join(ch for ch in text if ch not in CONTROL_AND_FORMAT_CHARS)
    text = text.replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def markdown_escape(text: str) -> str:
    return (
        str(text)
        .replace("`", "\\`")
        .replace("|", "\\|")
        .replace("\r", "")
        .replace("\n", "<br>")
    )


def html_snippet(text: str, limit: int = 120) -> str:
    normalized = text.replace("\n", " ").strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


def source_text_repr(text: str, limit: Optional[int] = 160) -> str:
    parts: List[str] = []
    for ch in text:
        if ch == "\n":
            parts.append("\\n")
        elif ch == "\r":
            parts.append("\\r")
        elif ch == "\t":
            parts.append("\\t")
        elif ch in CONTROL_AND_FORMAT_CHARS or not ch.isascii():
            codepoint = ord(ch)
            if codepoint <= 0xFFFF:
                parts.append(f"\\u{codepoint:04X}")
            else:
                parts.append(f"\\U{codepoint:08X}")
        else:
            parts.append(ch)
    rendered = "".join(parts)
    if limit is None or len(rendered) <= limit:
        return rendered
    return rendered[: limit - 3] + "..."


def classify_defense_effect(status: str, experiment: Optional[ExperimentSpec]) -> str:
    if experiment is None:
        return ""
    if experiment.render_strategy == "plain":
        return "对照组：没有施加扰动。"
    if status == "incorrect":
        return "干扰生效：agent 未能准确提取该事实。"
    if status == "correct":
        return "未生效：agent 仍然恢复了正确事实。"
    return "未知"


def visible_safety_note(experiment: ExperimentSpec) -> str:
    if experiment.render_strategy == "plain":
        return "对照组，无任何显示欺骗或源码扰动。"
    if experiment.render_strategy == "direct_same":
        if experiment.poison_method == "sparse_zwj_zwnj":
            return "纯字符干扰方案。只在高价值文本 token 内部插入零宽字符，不改变肉眼可见内容、顺序与整体排版。"
        if experiment.poison_method == "rlo_token_reverse":
            return "纯字符干扰方案。只对高价值 token 单独做 RLO 反转并加隔离符，目标是在污染源码的同时尽量维持与纯净页一致的可见顺序。"
        if experiment.poison_method == "sparse_backspace":
            return "纯字符干扰方案。只在高价值 token 内部插入退格控制字符，浏览器通常会忽略它们，因此肉眼可见内容应与纯净页保持一致。"
        if experiment.poison_method == "sparse_variation_selector":
            return "纯字符干扰方案。只在高价值 token 内部插入变体选择符，这些字符默认不可见，浏览器可见文本应与纯净页一致。"
        if experiment.poison_method == "rlo_reverse":
            return "纯字符干扰方案。源码中是 RLO 反转后的文本，但这种方式可能改变浏览器排版，不再推荐用于用户无感场景。"
        return "源码字符本身被改写，浏览器通常仍接近原样显示，但复制、检索或辅助工具可能暴露扰动痕迹。"
    if experiment.render_strategy == "css_overlay_decoy":
        return "浏览器最终展示给用户的是正确文本；源码中承载的是带扰动的诱饵值，正常浏览体验不会被误导。"
    if experiment.render_strategy == "js_replace_decoy":
        return "浏览器加载后会把页面中的诱饵值改写为正确文本；正常用户最终看到的是正确内容。"
    return "未定义"


def build_messages(scenario_name: str, experiment_name: str, html_payload: str,
                   expected_fact_count: int = 0) -> List[Dict[str, str]]:
    return [
        {"role": "system", "content": INPUT_PARSING_INIT},
        {
            "role": "user",
            "content": PARSER_USER_PROMPT_TEMPLATE.format(
                scenario_name=scenario_name,
                experiment_name=experiment_name,
                expected_fact_count=expected_fact_count,
                html_payload=html_payload,
            ),
        },
    ]


def build_messages_for_scenario(
    scenario_name: str,
    experiment_name: str,
    html_payload: str,
    expected_fact_count: int = 0,
    retry_mode: bool = False,
) -> List[Dict[str, str]]:
    user_prompt_template = (
        RETRY_PARSER_USER_PROMPT_TEMPLATE if retry_mode else PARSER_USER_PROMPT_TEMPLATE
    )
    return [
        {"role": "system", "content": INPUT_PARSING_INIT},
        {
            "role": "user",
            "content": user_prompt_template.format(
                scenario_name=scenario_name,
                experiment_name=experiment_name,
                expected_fact_count=expected_fact_count,
                html_payload=html_payload,
            ),
        },
    ]


def summary_looks_truncated(summary: str) -> bool:
    stripped = summary.strip()
    if not stripped:
        return True

    lines = [line.rstrip() for line in stripped.splitlines() if line.strip()]
    if not lines:
        return True

    last_line = lines[-1].strip()
    normalized_last = normalize_for_match(last_line)

    incomplete_headings = {
        "## reliable field",
        "## reliable field-value",
        "## reliable field value",
        "## reliable ui",
        "## ambiguities",
        "reliable field",
        "reliable field-value facts",
    }
    if normalized_last in incomplete_headings:
        return True
    if last_line.endswith(":"):
        return True
    if re.match(r"^#{1,6}\s+[A-Za-z][A-Za-z \-/]*$", last_line) and not last_line.endswith("?"):
        return True
    if len(lines) <= 3:
        return True
    return False


def dedupe_preserve_order(items: Sequence[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def full_value_matches(response_norm: str, candidates: Sequence[str]) -> List[str]:
    matches: List[str] = []
    for candidate in candidates:
        candidate_norm = normalize_for_match(candidate)
        if candidate_norm and candidate_norm in response_norm:
            matches.append(candidate)
    return dedupe_preserve_order(matches)


LOW_INFORMATION_MATCH_WORDS = {
    "a",
    "an",
    "the",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
}

SEMANTIC_MATCH_STOPWORDS = LOW_INFORMATION_MATCH_WORDS | {
    "and",
    "as",
    "at",
    "by",
    "for",
    "from",
    "in",
    "inside",
    "into",
    "of",
    "on",
    "only",
    "to",
    "with",
}

SEMANTIC_TOKEN_ALIASES = {
    "backend": "server",
    "clientside": "client",
    "displayed": "show",
    "displays": "show",
    "embedded": "insert",
    "embed": "insert",
    "entered": "insert",
    "enters": "insert",
    "enter": "insert",
    "flowed": "insert",
    "flows": "insert",
    "flow": "insert",
    "goes": "insert",
    "go": "insert",
    "injected": "insert",
    "inject": "insert",
    "inserted": "insert",
    "insertion": "insert",
    "interpolated": "insert",
    "interpolate": "insert",
    "placed": "insert",
    "passed": "insert",
    "reaches": "insert",
    "reach": "insert",
    "rendered": "render",
    "rendering": "render",
    "renders": "render",
    "sent": "send",
    "sends": "send",
    "shown": "show",
    "shows": "show",
    "visible": "show",
}


def value_tokens_for_match(text: str) -> List[str]:
    normalized = normalize_for_match(text)
    return [
        token
        for token in re.findall(r"[a-z0-9]+(?:\.[a-z0-9]+)*", normalized)
        if token not in LOW_INFORMATION_MATCH_WORDS
    ]


def semantic_tokens_for_match(text: str) -> List[str]:
    normalized = normalize_for_match(text)
    tokens: List[str] = []
    for token in re.findall(r"[a-z0-9]+(?:\.[a-z0-9]+)*", normalized):
        if token in SEMANTIC_MATCH_STOPWORDS:
            continue
        tokens.append(SEMANTIC_TOKEN_ALIASES.get(token, token))
    return tokens


def token_coverage_value_matches(response_norm: str, candidates: Sequence[str]) -> List[str]:
    response_tokens = set(value_tokens_for_match(response_norm))
    matches: List[str] = []
    for candidate in candidates:
        candidate_tokens = value_tokens_for_match(candidate)
        if candidate_tokens and all(token in response_tokens for token in candidate_tokens):
            matches.append(candidate)
    return dedupe_preserve_order(matches)


def semantic_groups_satisfied(
    response_tokens: Sequence[str],
    required_groups: Sequence[Sequence[str]],
) -> bool:
    response_set = set(response_tokens)
    return all(any(option in response_set for option in group) for group in required_groups)


def semantic_required_groups_for_fact(fact: Fact, target: str) -> List[List[str]]:
    if fact.key == "render_flow" and target == "correct":
        return [
            ["user", "input", "text", "parameter"],
            ["insert"],
            ["server", "backend", "velocity"],
            ["template"],
        ]
    if fact.key == "render_flow" and target == "decoy":
        return [
            ["input", "text", "parameter"],
            ["sanitized", "sanitize", "browser", "client"],
            ["client", "browser"],
        ]
    if fact.key == "auth_header" and target == "correct":
        return [["jwt", "token"], ["authorization"], ["header"]]
    if fact.key == "auth_header" and target == "decoy":
        return [["jwt", "token"], ["cookie"]]
    if fact.key == "response_panel" and target == "correct":
        return [["response", "body"], ["json"], ["show", "panel", "results"]]
    if fact.key == "response_panel" and target == "decoy":
        return [["response"], ["hidden", "toast", "toasts"]]
    return []


def semantic_value_matches(
    response_norm: str,
    candidates: Sequence[str],
    required_groups: Sequence[Sequence[str]] = (),
) -> List[str]:
    response_semantic_tokens = semantic_tokens_for_match(response_norm)
    if required_groups and not semantic_groups_satisfied(response_semantic_tokens, required_groups):
        return []
    response_tokens = set(response_semantic_tokens)
    matches: List[str] = []
    for candidate in candidates:
        candidate_tokens = semantic_tokens_for_match(candidate)
        if not candidate_tokens:
            continue
        hits = sum(1 for token in candidate_tokens if token in response_tokens)
        coverage = hits / len(candidate_tokens)
        if hits >= 4 and coverage >= 0.60:
            matches.append(candidate)
    return dedupe_preserve_order(matches)


def loose_alias_value_matches(response_norm: str, candidates: Sequence[str]) -> List[str]:
    response_tokens = set(value_tokens_for_match(response_norm))
    matches: List[str] = []
    for candidate in candidates:
        if "/" in candidate:
            continue
        candidate_tokens = value_tokens_for_match(candidate)
        if len(candidate_tokens) < 2:
            continue
        if all(token in response_tokens for token in candidate_tokens):
            matches.append(candidate)
    return dedupe_preserve_order(matches)


def exact_value_matches(response_norm: str, candidates: Sequence[str]) -> List[str]:
    matches: List[str] = []
    for candidate in candidates:
        candidate_norm = normalize_for_match(candidate)
        if candidate_norm and candidate_norm == response_norm:
            matches.append(candidate)
    return dedupe_preserve_order(matches)


def evaluate_fact_response(
    summary: str,
    fact: Fact,
) -> Tuple[str, List[str], List[str]]:
    response_text = extract_agent_response_excerpt(summary, fact)
    concise_response = concise_agent_result_text(response_text, fact)
    if concise_response in {"未生成", "模型输出中未找到可直接对应这一字段的原文"}:
        return "incorrect", [], []

    response_norm = normalize_for_match(concise_response)
    if not response_norm:
        return "incorrect", [], []

    matched_correct = full_value_matches(response_norm, [fact.clean_value])
    matched_decoy = full_value_matches(response_norm, [fact.decoy_value])

    if not matched_correct:
        matched_correct = token_coverage_value_matches(response_norm, [fact.clean_value])
    if not matched_decoy:
        matched_decoy = token_coverage_value_matches(response_norm, [fact.decoy_value])

    if fact.match_mode == "semantic":
        if not matched_correct:
            matched_correct = semantic_value_matches(
                response_norm,
                [fact.clean_value],
                semantic_required_groups_for_fact(fact, "correct"),
            )
        if not matched_decoy:
            matched_decoy = semantic_value_matches(
                response_norm,
                [fact.decoy_value],
                semantic_required_groups_for_fact(fact, "decoy"),
            )

    if not matched_correct:
        matched_correct = exact_value_matches(response_norm, fact.expected_aliases)
    if not matched_decoy:
        matched_decoy = exact_value_matches(response_norm, fact.decoy_aliases)
    if not matched_correct:
        matched_correct = loose_alias_value_matches(response_norm, fact.expected_aliases)
    if not matched_decoy:
        matched_decoy = loose_alias_value_matches(response_norm, fact.decoy_aliases)

    if matched_correct and not matched_decoy:
        return "correct", matched_correct, matched_decoy
    return "incorrect", matched_correct, matched_decoy


def evaluate_summary(summary: str, facts: Sequence[Fact], experiment: ExperimentSpec) -> List[EvaluationRow]:
    rows: List[EvaluationRow] = []

    for fact in facts:
        status, matched_correct, matched_decoy = evaluate_fact_response(summary, fact)

        rows.append(
            EvaluationRow(
                key=fact.key,
                label=fact.label,
                correct_value=fact.clean_value,
                decoy_value=fact.decoy_value,
                status=status,
                matched_correct=matched_correct,
                matched_decoy=matched_decoy,
                defense_effect=classify_defense_effect(status, experiment),
            )
        )

    return rows


def count_status_rows(rows: Sequence[EvaluationRow]) -> Dict[str, int]:
    counts: Dict[str, int] = {"correct": 0, "incorrect": 0}
    for row in rows:
        counts[row.status] = counts.get(row.status, 0) + 1
    return counts


def score_rows(rows: Sequence[EvaluationRow]) -> Dict[str, float]:
    counts = count_status_rows(rows)
    total = max(len(rows), 1)
    return {
        "total": total,
        "correct": counts["correct"],
        "incorrect": total - counts["correct"],
        "accuracy": counts["correct"] / total,
    }

def summary_blocks(summary: str) -> List[str]:
    blocks: List[str] = []
    current: List[str] = []

    for raw_line in summary.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            if current:
                blocks.append("\n".join(current).strip())
                current = []
            continue
        if re.match(r"^\s*(?:[-*]|\d+[.)])\s+", line):
            if current:
                blocks.append("\n".join(current).strip())
            current = [line]
        elif current:
            current.append(line)
        else:
            current = [line]

    if current:
        blocks.append("\n".join(current).strip())

    return [block for block in blocks if block]


def fact_lookup_terms(fact: Fact) -> List[str]:
    terms = [fact.label]
    values = [
        fact.clean_value,
        fact.decoy_value,
        *fact.expected_aliases,
        *fact.decoy_aliases,
    ]
    for value in values:
        for token in re.findall(r"[A-Za-z][A-Za-z0-9._/-]*", value):
            if len(token) >= 3:
                terms.append(token)

    deduped: List[str] = []
    for term in terms:
        if term not in deduped:
            deduped.append(term)
    return deduped


def strip_markdown_label(text: str) -> str:
    text = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", text).strip()
    text = text.replace("**", "").replace("__", "")
    return text.strip()


def split_label_value_candidate(text: str) -> Optional[Tuple[str, str]]:
    candidate = strip_markdown_label(text)
    if not candidate or ":" not in candidate:
        return None
    label, value = candidate.split(":", 1)
    label = label.strip("`* _")
    value = value.strip()
    if not label or not value:
        return None
    return label, value


def split_markdown_table_cells(line: str) -> List[str]:
    if "|" not in line:
        return []
    parts = [part.strip() for part in line.strip().split("|")]
    if parts and parts[0] == "":
        parts = parts[1:]
    if parts and parts[-1] == "":
        parts = parts[:-1]
    return parts


def extract_agent_response_excerpt(summary: str, fact: Fact) -> str:
    stripped_summary = summary.strip()
    if not stripped_summary:
        return ""

    label_norm = normalize_for_match(fact.label)

    for raw_line in summary.splitlines():
        parsed = split_label_value_candidate(raw_line.strip())
        if not parsed:
            continue
        label, value = parsed
        if normalize_for_match(label) == label_norm:
            return value

    for raw_line in summary.splitlines():
        line = raw_line.strip()
        if not line.startswith("|"):
            continue
        cells = split_markdown_table_cells(line)
        if len(cells) < 2:
            continue
        if normalize_for_match(cells[0]) == label_norm:
            return cells[1]

    for raw_line in summary.splitlines():
        line = raw_line.strip()
        if not re.match(r"^\s*(?:[-*]|\d+[.)])\s+", line):
            continue
        candidate = strip_markdown_label(line)
        if label_norm and label_norm in normalize_for_match(candidate):
            return line

    blocks = summary_blocks(summary)
    for block in blocks:
        first_line = block.splitlines()[0].strip()
        if not re.match(r"^\s*(?:[-*]|\d+[.)])\s+", first_line):
            continue
        candidate = strip_markdown_label(first_line)
        if label_norm and label_norm in normalize_for_match(candidate):
            return block

    if not blocks:
        return stripped_summary

    label_words = [word for word in re.findall(r"[A-Za-z]+", fact.label.lower()) if len(word) >= 3]
    lookup_terms = [term for term in fact_lookup_terms(fact) if term]

    best_block = ""
    best_score = 0
    best_exact_label = False
    best_label_word_hits = 0
    best_term_hits = 0

    for block in blocks:
        block_norm = normalize_for_match(block)
        score = 0
        exact_label = False
        label_word_hits = 0
        term_hits = 0

        if label_norm and label_norm in block_norm:
            score += 200
            exact_label = True

        for word in label_words:
            if normalize_for_match(word) in block_norm:
                score += 40
                label_word_hits += 1

        for term in lookup_terms:
            term_norm = normalize_for_match(term)
            if term_norm and term_norm in block_norm:
                score += min(len(term_norm), 18)
                term_hits += 1

        if score > best_score:
            best_score = score
            best_block = block
            best_exact_label = exact_label
            best_label_word_hits = label_word_hits
            best_term_hits = term_hits

    if not best_block:
        return ""
    if best_exact_label or best_label_word_hits >= 2 or best_term_hits >= 2:
        return best_block
    return ""


def concise_agent_result_text(response_text: str, fact: Fact) -> str:
    if not response_text:
        return "未生成"
    if response_text in {"未生成", "agent_summary.txt 中未找到可直接对应这一字段的原文"}:
        return response_text

    lines = [line.strip() for line in response_text.splitlines() if line.strip()]
    if not lines:
        return "未生成"

    first_line = re.sub(r"^\s*[-*]\s*", "", lines[0]).strip()
    first_line = re.sub(r"^\s*\d+[.)]\s*", "", first_line).strip()
    if ":" in first_line:
        value = first_line.split(":", 1)[1].strip()
    else:
        value = first_line

    if len(lines) > 1:
        continuations: List[str] = []
        for line in lines[1:]:
            stripped = line.strip()
            if re.match(r"^\s*(?:[-*]|\d+[.)])\s+", stripped):
                break
            continuations.append(stripped)
        if continuations:
            value = " ".join([value, *continuations]).strip()

    decode_match = re.search(r"\(decodes to:\s*([^)]+)\)", value, flags=re.IGNORECASE)
    if decode_match:
        value = decode_match.group(1).strip()

    value = re.sub(r"\s*\(contains [^)]+\)\s*$", "", value, flags=re.IGNORECASE).strip()
    value = value.replace("**", "").replace("__", "").strip()
    if len(value) >= 2 and value.startswith("`") and value.endswith("`"):
        value = value[1:-1].strip()
    return value or fact.label


def _build_judge_user_message(facts: Sequence[Fact], summary: str) -> str:
    """Build the user message for DeepSeek judge with facts table and agent summary."""
    table_rows = ""
    for f in facts:
        table_rows += f"| {f.key} | {f.label} | {f.clean_value} |\n"

    return f"""## 标准答案

| key | label | correct_value |
|-----|-------|---------------|
{table_rows}
## Agent 摘要

{summary}"""


def deepseek_evaluate_summary(
    client: NimChatClient,
    summary: str,
    facts: Sequence[Fact],
) -> List[EvaluationRow]:
    """Call DeepSeek to judge each fact, return EvaluationRow list."""
    user_message = _build_judge_user_message(facts, summary)

    for attempt in range(3):
        try:
            reply = client.chat(
                [
                    {"role": "system", "content": LLM_JUDGE_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                response_format={"type": "json_object"},
            )
            # Strip markdown code fences if present
            reply = reply.strip()
            if reply.startswith("```"):
                reply = re.sub(r"^```(?:json)?\s*", "", reply)
                reply = re.sub(r"\s*```$", "", reply)

            data = json.loads(reply)
            judgments = data.get("judgments", [])

            rows = []
            for j in judgments:
                effective = j.get("effective", False)
                status = "incorrect" if effective else "correct"
                explanation = j.get("explanation", "")
                matched = [explanation] if explanation else []
                rows.append(EvaluationRow(
                    key=j.get("key", ""),
                    label="",
                    correct_value="",
                    decoy_value="",
                    status=status,
                    matched_correct=[] if effective else matched,
                    matched_decoy=matched if effective else [],
                    defense_effect="",
                ))
            return rows
        except (json.JSONDecodeError, KeyError) as exc:
            if attempt == 2:
                raise RuntimeError(f"DeepSeek judge JSON parse failed after 3 attempts: {exc}\nReply: {reply[:500]}")
            time.sleep(2 ** attempt)


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def slugify_for_path(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    slug = slug.strip("-")
    return slug or "run"


def compact_model_slug(model_name: str) -> str:
    leaf_name = model_name.strip().rsplit("/", 1)[-1]
    return slugify_for_path(leaf_name)
