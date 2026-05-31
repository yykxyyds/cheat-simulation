"""CLI entry point + experiment orchestration (pre-built payload mode)."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .config import (
    SCRIPT_DIR,
    NIM_BASE_URL_DEFAULT,
    DEFAULT_TIMEOUT,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODELS,
    DEFAULT_ENV_FILE,
    NIM_API_KEY_ENV_VARS,
    MODEL_PROVIDER_CONFIG,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    GLM_BASE_URL,
    GLM_MODEL,
)
from .prompts import LLM_JUDGE_PROMPT, SUMMARY_SYSTEM_PROMPT
from .client import NimChatClient
from .evaluator import (
    evaluate_summary,
    score_rows,
    deepseek_evaluate_summary,
    summary_looks_truncated,
    build_messages,
    build_messages_for_scenario,
    compact_model_slug,
)
from . import registry

# Log directory at project root
PROJECT_ROOT = SCRIPT_DIR.parent if SCRIPT_DIR.name == "code" else SCRIPT_DIR
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "log"


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------

def _parse_dotenv_value(raw_value: str) -> str:
    value = raw_value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_dotenv_fallback(dotenv_path: Path, override: bool = False) -> None:
    if not dotenv_path.exists():
        return
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        if not override and key in os.environ:
            continue
        os.environ[key] = _parse_dotenv_value(value)


def _load_runtime_env(env_file: Optional[str]) -> Optional[Path]:
    if env_file:
        dotenv_path = Path(env_file)
    else:
        dotenv_path = Path(os.environ.get("ENV_FILE", DEFAULT_ENV_FILE))
    if not dotenv_path.is_absolute():
        dotenv_path = PROJECT_ROOT / dotenv_path

    if dotenv_path.exists():
        try:
            from dotenv import load_dotenv as _load
            _load(dotenv_path=dotenv_path, override=True)
            return dotenv_path
        except ImportError:
            pass
        load_dotenv_fallback(dotenv_path, override=True)
        return dotenv_path
    return None


def resolve_api_key(cli_value: Optional[str]) -> Optional[str]:
    if cli_value:
        return cli_value
    for var in NIM_API_KEY_ENV_VARS:
        val = os.environ.get(var, "").strip()
        if val:
            return val
    return None


def _resolve_provider_config(model_name: str, cli_api_key: Optional[str],
                             cli_base_url: str) -> dict:
    """Return {base_url, api_key} for the given model."""
    cfg = MODEL_PROVIDER_CONFIG.get(model_name)
    if cfg:
        base_url = cfg["base_url"]
        api_key = ""
        for var in cfg["api_key_env_vars"]:
            api_key = os.environ.get(var, "").strip()
            if api_key:
                break
    else:
        base_url = cli_base_url
        api_key = cli_api_key or ""
    if not api_key:
        api_key = cli_api_key or ""
    return {"base_url": base_url, "api_key": api_key}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run pentest agent poisoning experiments with pre-built HTML payloads."
    )
    parser.add_argument("--scenario", nargs="*", default=["Labyrinth"],
                        help="Scenario slugs. Use 'all' for all registered scenarios.")
    parser.add_argument("--experiments", nargs="*", default=[],
                        help="Experiment names. Default runs registered defaults. Use 'all' for all registered.")
    parser.add_argument("--api-key", default=None, help="API key override.")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE),
                        help="Path to .env file.")
    parser.add_argument("--model", default="minimaxai/minimax-m2.7",
                        help="Single model name.")
    parser.add_argument("--models", nargs="+", default=None,
                        help="Multiple models. Overrides --model.")
    parser.add_argument("--base-url", default=NIM_BASE_URL_DEFAULT,
                        help="OpenAI-compatible base URL.")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                        help="Read timeout in seconds.")
    parser.add_argument("--connect-timeout", type=int, default=10)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR),
                        help="Base directory for timestamped run output.")
    parser.add_argument("--generate-only", action="store_true",
                        help="Only validate payload files exist, skip API calls.")
    parser.add_argument("--no-llm-judge", action="store_true",
                        help="Disable DeepSeek LLM judge (use rule-based evaluation instead).")
    parser.add_argument("--list-scenarios", action="store_true")
    parser.add_argument("--list-experiments", action="store_true")
    return parser.parse_args(argv)


def _print_registry_info() -> None:
    print("Registered scenarios & experiments (pre-built payloads):")
    for scenario, experiments in registry.list_available().items():
        print(f"  {scenario}: {', '.join(experiments)}")


def _resolve_scenarios(args: List[str]) -> List[str]:
    registered = registry.list_scenarios()
    if args == ["all"]:
        return registered
    return [s for s in args if s in registered]


def _resolve_experiments(args: List[str]) -> List[str]:
    """Resolve experiment names from CLI args, using registered defaults."""
    available: Dict[str, List[str]] = registry.list_available()
    all_exps = sorted(set(e for exps in available.values() for e in exps))
    if not args:
        return ["right_to_left_override", "mixed_homoglyph", "mixed_homoglyph_rlo"]
    if args == ["all"]:
        return all_exps
    return [e for e in args if e in all_exps]


# ---------------------------------------------------------------------------
# Experiment runner
# ---------------------------------------------------------------------------

def _build_timestamped_output_root(base_dir: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path(base_dir) / ts


def _slugify(value: str) -> str:
    return value.replace("/", "-").replace(" ", "_").lower()


def run_experiment(
    scenario_slug: str,
    experiment_name: str,
    model_name: str,
    output_root: Path,
    *,
    generate_only: bool = False,
    llm_judge: bool = False,
    api_key: Optional[str] = None,
    base_url: str = NIM_BASE_URL_DEFAULT,
    timeout: int = DEFAULT_TIMEOUT,
    connect_timeout: int = 10,
    retries: int = 1,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = 0.0,
    top_p: float = 0.9,
    deepseek_client: Optional[NimChatClient] = None,
) -> dict:
    """Run a single experiment×model trial. Returns result dict for summary."""
    payload_path = registry.get_payload_path(scenario_slug, experiment_name)
    facts = registry.get_facts(scenario_slug, experiment_name)
    if payload_path is None or not payload_path.exists():
        raise FileNotFoundError(f"Payload not found: {payload_path}")

    html_payload = payload_path.read_text(encoding="utf-8")
    model_slug = compact_model_slug(model_name)
    run_dir = output_root / scenario_slug / experiment_name
    run_dir.mkdir(parents=True, exist_ok=True)

    result = {
        "scenario": scenario_slug,
        "experiment": experiment_name,
        "model_name": model_name,
        "score": {},
        "analysis_rows": [],
    }
    error_message: Optional[str] = None

    if generate_only:
        result["score"] = {"accuracy": float("nan"), "correct": 0, "total": len(facts)}
        return result

    provider = _resolve_provider_config(model_name, api_key, base_url)

    client = NimChatClient(
        api_key=provider["api_key"],
        model_name=model_name,
        base_url=provider["base_url"],
        timeout=timeout,
        connect_timeout=connect_timeout,
        retries=retries,
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
    )

    start = time.time()
    messages = build_messages(scenario_slug, experiment_name, html_payload,
                              expected_fact_count=len(facts))
    summary = ""
    retry_note: Optional[str] = None

    try:
        summary = client.chat(messages)

        # Auto-retry if output looks truncated
        needs_retry = summary_looks_truncated(summary)
        if not needs_retry and experiment_name == "plain":
            rows = evaluate_summary(summary, facts, None)
            sc = score_rows(rows)
            if sc.get("correct", 0) == 0:
                needs_retry = True

        if needs_retry:
            retry_messages = build_messages_for_scenario(
                scenario_slug, experiment_name, html_payload,
                expected_fact_count=len(facts), retry_mode=True,
            )
            retry_summary = client.chat(retry_messages)
            if retry_summary.strip():
                summary = retry_summary
                retry_note = (
                    "The initial model reply looked truncated or failed to extract "
                    "field-value facts, so the script retried once with a stricter prompt."
                )
    except Exception as exc:
        error_message = str(exc)
        summary = ""

    elapsed = time.time() - start

    # Write agent response to .txt
    model_slug = compact_model_slug(model_name)
    summary_path = run_dir / f"{model_slug}.txt"
    summary_path.write_text(summary.rstrip() + "\n", encoding="utf-8")

    # Evaluate
    if llm_judge and deepseek_client is not None and summary.strip():
        try:
            evaluation_rows = deepseek_evaluate_summary(deepseek_client, summary, facts)
        except Exception as exc:
            print(f"    [WARN] DeepSeek judge failed, falling back to rule-based: {exc}", file=sys.stderr)
            evaluation_rows = evaluate_summary(summary, facts, None)
    else:
        evaluation_rows = evaluate_summary(summary, facts, None)

    sc = score_rows(evaluation_rows)
    result["score"] = sc

    # Save evaluation JSON
    eval_data = [
        {
            "key": r.key,
            "status": r.status,
            "matched_correct": r.matched_correct,
            "matched_decoy": r.matched_decoy,
        }
        for r in evaluation_rows
    ]
    eval_path = run_dir / f"{model_slug}_evaluation.json"
    import json
    eval_path.write_text(json.dumps(eval_data, ensure_ascii=False, indent=2), encoding="utf-8")

    if error_message:
        error_path = run_dir / "error.txt"
        error_path.write_text(error_message + "\n", encoding="utf-8")

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)

    if args.list_scenarios:
        _print_registry_info()
        return 0
    if args.list_experiments:
        _print_registry_info()
        return 0

    # Resolve scenarios and experiments
    scenarios = _resolve_scenarios(args.scenario)
    experiments = _resolve_experiments(args.experiments)
    models = args.models or [args.model]

    if not scenarios:
        print(f"Error: no registered scenarios match {args.scenario}", file=sys.stderr)
        _print_registry_info()
        return 1
    if not experiments:
        print("Error: no matching experiments found", file=sys.stderr)
        _print_registry_info()
        return 1

    # Load env
    _load_runtime_env(args.env_file)
    api_key = resolve_api_key(args.api_key)

    # DeepSeek judge: auto-enable when API key is available
    deepseek_client: Optional[NimChatClient] = None
    if not args.no_llm_judge:
        ds_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if ds_key:
            deepseek_client = NimChatClient(
                api_key=ds_key, model_name=DEEPSEEK_MODEL, base_url=DEEPSEEK_BASE_URL,
                max_tokens=4096,  # LLM judge: short JSON responses
            )
            summary_client = NimChatClient(
                api_key=ds_key, model_name=DEEPSEEK_MODEL, base_url=DEEPSEEK_BASE_URL,
                max_tokens=16384,  # summary: 30+ experiments need more tokens
            )
            llm_judge = True
        else:
            llm_judge = False
    else:
        llm_judge = False

    if args.generate_only and not api_key:
        print("Info: no API key found, running in generate-only mode")
        args.generate_only = True

    output_root = _build_timestamped_output_root(args.output_dir)
    print(f"Output: {output_root}")
    print(f"Scenarios: {scenarios}")
    print(f"Experiments: {experiments}")
    print(f"Models: {models}")

    all_results: List[dict] = []

    for scenario_slug in scenarios:
        for experiment_name in experiments:
            if not registry.has_payload(scenario_slug, experiment_name):
                print(f"  Skip {scenario_slug}/{experiment_name}: no payload registered")
                continue

            for model_name in models:
                print(f"  Running: {scenario_slug}/{experiment_name} @ {compact_model_slug(model_name)}")
                result = run_experiment(
                    scenario_slug=scenario_slug,
                    experiment_name=experiment_name,
                    model_name=model_name,
                    output_root=output_root,
                    generate_only=args.generate_only,
                    llm_judge=llm_judge,
                    api_key=api_key,
                    base_url=args.base_url,
                    timeout=args.timeout,
                    connect_timeout=args.connect_timeout,
                    retries=args.retries,
                    max_tokens=args.max_tokens,
                    temperature=args.temperature,
                    top_p=args.top_p,
                    deepseek_client=deepseek_client,
                )
                all_results.append(result)

    # Write combined summaries per scenario via DeepSeek
    if deepseek_client is not None:
        for scenario_slug in scenarios:
            scenario_dir = output_root / scenario_slug
            generate_summary_with_deepseek(summary_client, scenario_dir, scenario_slug)

    print("Done.")
    return 0


# ---------------------------------------------------------------------------
# DeepSeek summary generation
# ---------------------------------------------------------------------------

def generate_summary_with_deepseek(
    client: NimChatClient,
    scenario_dir: Path,
    scenario_slug: str,
) -> None:
    """Use DeepSeek to generate summary Markdown from raw .txt and .json files."""
    # Collect all experiment data
    user_parts: List[str] = [f"## 场景：{scenario_slug}\n"]
    for exp_dir in sorted(scenario_dir.iterdir()):
        if not exp_dir.is_dir():
            continue
        exp_name = exp_dir.name
        # Load ground truth facts for this experiment
        facts = registry.get_facts(scenario_slug, exp_name)
        if facts:
            facts_table = "| key | label | correct_value |\n|-----|-------|---------------|\n"
            facts_table += "\n".join(
                f"| {f.key} | {f.label} | {f.clean_value} |" for f in facts
            )
        else:
            facts_table = "(无标准答案)"

        for txt_file in sorted(exp_dir.glob("*.txt")):
            if txt_file.name == "error.txt":
                continue
            model_slug = txt_file.stem
            json_file = exp_dir / f"{model_slug}_evaluation.json"

            agent_response = txt_file.read_text(encoding="utf-8").strip()
            eval_json = json_file.read_text(encoding="utf-8") if json_file.exists() else "[]"

            user_parts.append(f"### 实验：{exp_name} | 模型：{model_slug}\n")
            user_parts.append("标准答案：\n" + facts_table + "\n")
            user_parts.append("Agent 原始响应：\n```\n" + agent_response + "\n```\n")
            user_parts.append("DeepSeek 评估结果 (JSON)：\n```json\n" + eval_json + "\n```\n")

            # Precompute accuracy (correct/total) so DeepSeek doesn't miscount
            try:
                ed = json.loads(eval_json)
                t = len(ed)
                c = sum(1 for d in ed if d.get("status") == "correct")
                user_parts.append(f"预计算 accuracy: {c}/{t} = {c/t:.2f}\n")
            except Exception:
                pass

    user_message = "\n".join(user_parts)

    # Generate summary
    summary_path = scenario_dir / f"{scenario_slug}_summary.md"
    _call_deepseek_summary(client, SUMMARY_SYSTEM_PROMPT, user_message, summary_path)


def _call_deepseek_summary(
    client: NimChatClient,
    system_prompt: str,
    user_message: str,
    output_path: Path,
) -> None:
    """Call DeepSeek to generate a summary markdown file."""
    import sys as _sys
    try:
        reply = client.chat([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ])
        # Strip code fences if present
        reply = reply.strip()
        if reply.startswith("```"):
            reply = reply[reply.find("\n") + 1:]
        if reply.endswith("```"):
            reply = reply[:reply.rfind("```")].rstrip()
        output_path.write_text(reply.strip() + "\n", encoding="utf-8")
    except Exception as exc:
        print(f"  [ERROR] DeepSeek summary failed for {output_path}: {exc}", file=_sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
