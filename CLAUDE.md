# CLAUDE.md

本文件为 Claude Code（claude.ai/code）在此仓库中工作提供指引。

## 目标

研究特殊字符扰动能否在不影响人类用户在浏览器中所见内容的前提下，干扰 LLM 渗透测试 agent。扰动只有满足以下条件才视为适用：agent 读取的是 `page_perturbation.html`；`page_pure.html` 仅作为干净的人类参考页；扰动页面的渲染效果应尽可能与干净页一致；系统提示和页面副本不得向 agent 透露特殊字符防御的存在；日志保持简洁可读。

## 架构

单文件 Python 脚本 `pentest_agent_poison_sim.py`。核心类型与流程：

- **`Fact`** — 一条高价值信息。`clean_value` 正确值、`decoy_value` 诱饵值；`match_mode` 为 `strict`（精确匹配）或 `semantic`（语义匹配），影响 `evaluate_fact_response()` 的匹配策略。
- **`RenderedFact`** — `Fact` 经过 `render_fact_value()` 后的产物，携带 `html_value`（插入 HTML 的片段）、`source_text`（HTML 源码中的文本）、`visible_text`（浏览器渲染后用户实际看到的文本）。
- **`EvaluationRow`** — `evaluate_summary()` 的输出行，包含 `status`（correct/poisoned/incorrect/mixed）、`matched_correct`、`matched_decoy`。
- **`Scenario`** — 一个合成网页，包含标题、UI 文案和一组 Fact。当前活跃场景：`Labyrinth`（SSTI 主题翻译控制台）和 `CorpNet`（内部运维仪表盘，含命令注入 + 特权脚本利用链）。另有 `locktalk_docs`（含认证链路的 API 文档）已定义但未激活。`Scenario.template` 可以是 `"generic"`（默认）或 `"corpnet_dashboard"`（CorpNet 专用模板）。别名：`Labyrinth_Linguist` → `Labyrinth`。
- **`ExperimentSpec`** — 扰动方法 + 渲染策略。`render_strategy` 有四种：`plain`（基线无扰动）、`direct_same`（直接污染文本源码）、`css_overlay_decoy`（源码放诱饵值，CSS 覆盖为正确文本）、`js_replace_decoy`（源码放诱饵值，JS 运行时改写）。当前适用实验只用 `direct_same`。
- **`NimChatClient`** — OpenAI 兼容聊天 API 的轻量封装，支持多提供商（NVIDIA NIM / DeepSeek / ZhipuAI GLM）。

**执行流程：** `main()` → 逐个实验调用 `run_experiment()` → `render_scenario_html()` 生成投毒 HTML（同时用 `PURE_REFERENCE_EXPERIMENT` 生成 `page_pure.html`）→ agent 模型进行摘要 → `evaluate_summary()` 对照预期事实评分 → `write_scenario_summary_markdown()` 生成汇总表格。

**自动重试：** 当 agent 响应看起来被截断，或 plain 基线实验得 0 分时，`run_experiment()` 会自动用更严格的 field-value-only prompt 重试一次。

**扰动管线：** `apply_poison(text, method)` 分发到具体投毒函数。对于含版本号的值（如 `Spring Boot 1.5.10`），`apply_poison_to_numeric_versions()` 只扰动版本号子串，不动框架名/产品名。

## 场景

| Slug | 主题 | 风险类型 | 状态 |
|------|------|----------|------|
| `Labyrinth` | 翻译控制台，含 SSTI 线索 | 服务端模板注入 | **活跃** |
| `CorpNet` | 内部运维仪表盘，含命令注入入口 | 命令注入 + 特权脚本提权 | **活跃** |
| `locktalk_docs` | 内部 API 文档，含认证端点 | 认证绕过 / 权限提升 | 已定义未激活 |

`ACTIVE_SCENARIO_NAMES` 控制 `--scenario all` 运行哪些场景。

## 命令

```bash
# 不带 --experiments 时只运行 3 项默认实验（DEFAULT_EXPERIMENT_SEQUENCE）：
#   right_to_left_override, mixed_homoglyph, mixed_homoglyph_rlo
python pentest_agent_poison_sim.py --scenario Labyrinth
# 别名兼容：Labyrinth_Linguist → Labyrinth
python pentest_agent_poison_sim.py --scenario Labyrinth_Linguist

# 运行所有活跃场景的全部适用实验
python pentest_agent_poison_sim.py --scenario all --experiments all

# 运行所有适用实验（使用 APPLICABLE_EXPERIMENT_NAMES 白名单，共 29 项）
python pentest_agent_poison_sim.py --scenario Labyrinth --experiments all

# 运行指定实验
python pentest_agent_poison_sim.py --scenario Labyrinth --experiments zero_width_space zero_width_binary

# 指定模型（覆盖 DEFAULT_MODELS 中的 5 个默认模型）
python pentest_agent_poison_sim.py --scenario Labyrinth --experiments all --models minimaxai/minimax-m2.7

# 只生成 HTML，不调用 API（离线开发）
python pentest_agent_poison_sim.py --scenario Labyrinth --experiments all --generate-only

# 启用 LLM 语义裁判（需要 DEEPSEEK_API_KEY）
python pentest_agent_poison_sim.py --scenario Labyrinth --experiments all --llm-judge

# 列出可用场景 / 实验
python pentest_agent_poison_sim.py --list-scenarios
python pentest_agent_poison_sim.py --list-experiments

# 编辑后语法检查
python -m py_compile pentest_agent_poison_sim.py
```

## 环境配置

API Key 从 `cheat_simulation/.env` 文件读取。支持的提供商及环境变量：

| 提供商 | 环境变量 | 默认模型 |
|--------|----------|----------|
| NVIDIA NIM | `NVIDIA_API_KEY` / `NVIDIA_NIM_API_KEY` / `NIM_API_KEY` | `minimaxai/minimax-m2.7`、`qwen/qwen3.5-397b-a17b`、`mistralai/mistral-large-3-675b-instruct-2512` |
| DeepSeek | `DEEPSEEK_API_KEY` | `deepseek-chat` |
| ZhipuAI GLM | `GLM_API_KEY` | `glm-4-flash` |

也可通过 `--api-key` 统一传入（仅对无法匹配到已知提供商的模型生效）。默认模型列表（`DEFAULT_MODELS`）包含以上全部 5 个模型。每个实验会依次用所有默认模型测试。LLM 裁判模式需 `DEEPSEEK_API_KEY`。无 API Key 时脚本自动降级为 `--generate-only` 模式。

## 日志结构

```
log/YYYYMMDD_HHMMSS/
  └── <Scenario>/
        ├── page_pure.html                  # 干净参考页（场景级）
        ├── <Scenario>_summary.md           # 全量汇总（所有模型合并）
        ├── <Scenario>_success_summary.md   # 仅有效防御子集
        └── <experiment_name>/
              ├── page_perturbation_<experiment_name>.html    # 投毒 HTML
              ├── <model-slug1>.txt         # 模型1 agent 提取结果
              ├── <model-slug2>.txt         # 模型2 ...
              └── ...
```

不要在日志中产生多余的杂文件，除非确有必要。

## 当前适用实验

`--experiments all` 只运行 `APPLICABLE_EXPERIMENT_NAMES` 中的实验——这些实验不应明显改变渲染输出。目前共 29 项：`zero_width_space`、`zero_width_non_joiner`、`zero_width_joiner`、`zero_width`、`word_joiner`、`soft_hyphen`、`byte_order_mark`、`unicode_tags`、`nbsp_space`、`left_to_right_mark`、`right_to_left_mark`、`pop_directional_formatting`、`left_to_right_embedding`、`right_to_left_embedding`、`left_to_right_isolate`、`pop_directional_isolate`、`right_to_left_isolate`、`function_application`、`invisible_times`、`zero_width_binary`、`left_to_right_override`、`right_to_left_override`、`variation_selector`、`mixed_homoglyph`、`mixed_homoglyph_rlo`、`invisible_separator`、`carriage_return`、`backspace_overwrite`、`zwsp_cgj_combo`。

默认实验已精简为 3 项：
- `right_to_left_override` — RLO 方向反转，最有效的单一方法
- `mixed_homoglyph` — 全面同形字替换（40字符）+ NBSP空格 + 7种零宽字符字母间插入
- `mixed_homoglyph_rlo` — 组合扰动：先做同形字替换+零宽字符插入，再 RLO 包裹反转，双重防御

已排除：`cyrillic_a_homoglyph`、`aggressive_homoglyph`、`greek_homoglyph`、`invisible_sep_homoglyph`（合并入 `mixed_homoglyph`），以及文档中标为不适用的所有可见性破坏类编码/碎片化/空格方案。`backspace`、`delete_control`（渲染为可见占位符）也已排除。

## figure_comparison 目录

用于截图对比，验证扰动页面是否与干净页在浏览器中渲染一致。包含：
- `page_pure.html` / `page_perturbation_*.html` — 对比用的 HTML 文件
- `shot_*.png` — Edge headless 截图（pure/pert/diff 等）
- `截图对比方法.md` — 截图对比的操作说明

## 文档文件

- `document/特殊字符调研.md` — 两张表（适用于本实验 / 不适用于本实验）。特殊字符列格式：中文名 + 英文 log 名，如 `零宽空格（zero_width_space）`。
- `document/特殊字符渲染效果.html` — 按适用/不适用分组渲染。**如果在两组之间移动条目，必须同步更新两个文件。**

## test 目录

`test/` 目录用 `generate_test_html.py` 为 Labyrinth 和 CorpNet 两个场景生成对比用的投毒 HTML（`right_to_left_override`、`mixed_homoglyph`、`mixed_homoglyph_rlo` 三种方法），配合 Edge headless 截图验证渲染一致性。

```bash
cd test && python generate_test_html.py
```

各场景子目录（`test/Labyrinth/`、`test/CorpNet/`）包含 `page_pure.html`、投毒 HTML 和 `shot_*.png` 截图。

## 验证检查清单

修改摘要生成、评分或响应提取逻辑后：

1. `_summary.md` 中每行与对应的 `<model-slug>.txt` 一致
2. Agent 响应提取是字段级别的，不是整段 dump
3. Markdown 表格不被反引号或竖线破坏
4. `accuracy` 值与 `<model-slug>.txt` 实际内容吻合
5. 实验目录集合与 `APPLICABLE_EXPERIMENT_NAMES` 一致
