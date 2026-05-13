# CLAUDE.md

本文件为 Claude Code（claude.ai/code）在此仓库中工作提供指引。

## 目标

研究特殊字符扰动能否在不影响人类用户在浏览器中所见内容的前提下，干扰 LLM 渗透测试 agent。扰动只有满足以下条件才视为适用：agent 读取的是 `page_perturbation.html`；`page_pure.html` 仅作为干净的人类参考页；扰动页面的渲染效果应尽可能与干净页一致；系统提示和页面副本不得向 agent 透露特殊字符防御的存在；日志保持简洁可读。

## 架构

单文件 Python 脚本 `pentest_agent_poison_sim.py`（约 3600 行）。核心类型与流程：

- **`Fact`** — 一条高价值信息（clean_value 正确值、decoy_value 诱饵值、match_mode 匹配模式）。
- **`Scenario`** — 一个合成网页，包含标题、UI 文案和一组 Fact。目前有两个场景：`Labyrinth_Linguist`（SSTI 主题翻译页面）和 `locktalk_docs`（含认证链路的 API 文档）。
- **`ExperimentSpec`** — 扰动方法 + 渲染策略。 **`APPLICABLE_EXPERIMENT_NAMES`** 是当前适用实验的白名单。
- **`NimChatClient`** — NVIDIA NIM OpenAI 兼容聊天 API 的轻量封装。

**执行流程：** `main()` → 逐个实验调用 `run_experiment()` → `render_scenario_html()` 生成投毒 HTML → agent 模型进行摘要 → `evaluate_summary()` 对照预期事实评分 → `write_scenario_summary_markdown()` 生成汇总表格。

**扰动管线：** `apply_poison(text, method)` 分发到具体投毒函数。对于含版本号的值（如 `Spring Boot 1.5.10`），`apply_poison_to_numeric_versions()` 只扰动版本号子串，不动框架名/产品名。

## 场景

| Slug | 主题 | 风险类型 |
|------|------|----------|
| `Labyrinth_Linguist` | 翻译控制台，含 SSTI 线索 | 服务端模板注入 |
| `locktalk_docs` | 内部 API 文档，含认证端点 | 认证绕过 / 权限提升 |

## 命令

```bash
# 运行所有适用实验（使用 APPLICABLE_EXPERIMENT_NAMES 白名单）
python3 cheat_simulation/pentest_agent_poison_sim.py --scenario Labyrinth_Linguist --experiments all

# 运行指定实验
python3 cheat_simulation/pentest_agent_poison_sim.py --scenario Labyrinth_Linguist --experiments zero_width_space zero_width_binary

# 只生成 HTML，不调用 API（离线开发）
python3 cheat_simulation/pentest_agent_poison_sim.py --scenario Labyrinth_Linguist --experiments all --generate-only

# 启用 LLM 语义裁判（速度更慢）
python3 cheat_simulation/pentest_agent_poison_sim.py --scenario Labyrinth_Linguist --experiments all --llm-judge

# 列出可用场景 / 实验
python3 cheat_simulation/pentest_agent_poison_sim.py --list-scenarios
python3 cheat_simulation/pentest_agent_poison_sim.py --list-experiments

# 编辑后语法检查
python3 -m py_compile cheat_simulation/pentest_agent_poison_sim.py
```

## 环境配置

NVIDIA NIM 的 API Key 从仓库根目录的 `.env` 文件读取——检查环境变量：`NVIDIA_API_KEY`、`NVIDIA_NIM_API_KEY`、`NIM_API_KEY`。也可通过 `--api-key` 传入。默认模型：`minimaxai/minimax-m2.7`。无 API Key 时脚本自动降级为 `--generate-only` 模式。

## 日志结构

```
cheat_simulation/log/YYYYMMDD_HHMMSS_<model-slug>/
  └── <Scenario>/
        ├── page_pure.html                  # 干净参考页（场景级）
        ├── <Scenario>_summary.md           # 完整结果表
        ├── <Scenario>_success_summary.md   # 仅成功子集
        └── <experiment_name>/
              ├── page_perturbation.html    # 投毒 HTML
              └── agent_summary.txt         # agent 提取的事实
```

不要在日志中产生多余的杂文件，除非确有必要。

## 当前适用实验

`--experiments all` 只运行 `APPLICABLE_EXPERIMENT_NAMES` 中的实验——这些实验不应明显改变渲染输出。目前共 23 项：`zero_width_space`、`zero_width_non_joiner`、`zero_width_joiner`、`zero_width`、`word_joiner`、`byte_order_mark`、`unicode_tags`、`cyrillic_a_homoglyph`、`left_to_right_mark`、`right_to_left_mark`、`pop_directional_formatting`、`left_to_right_embedding`、`right_to_left_embedding`、`left_to_right_isolate`、`right_to_left_isolate`、`pop_directional_isolate`、`backspace`、`function_application`、`invisible_times`、`zero_width_binary`、`left_to_right_override`、`right_to_left_override`、`variation_selector`。

已排除：`aggressive_homoglyph`、`delete_control`，以及文档中标为不适用的所有可见性破坏类编码/碎片化/空格方案。

## 文档文件

- `document/特殊字符调研.md` — 两张表（适用于本实验 / 不适用于本实验）。特殊字符列格式：中文名 + 英文 log 名，如 `零宽空格（zero_width_space）`。
- `document/特殊字符渲染效果.html` — 按适用/不适用分组渲染。**如果在两组之间移动条目，必须同步更新两个文件。**

## 验证检查清单

修改摘要生成、评分或响应提取逻辑后：

1. `_summary.md` 中每行与对应的 `agent_summary.txt` 一致
2. Agent 响应提取是字段级别的，不是整段 dump
3. Markdown 表格不被反引号或竖线破坏
4. `accuracy` 值与 `agent_summary.txt` 实际内容吻合
5. 实验目录集合与 `APPLICABLE_EXPERIMENT_NAMES` 一致
