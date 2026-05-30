# CLAUDE.md

本文件为 Claude Code（claude.ai/code）在此仓库中工作提供指引。

## 目标

研究特殊字符扰动能否在不影响人类用户在浏览器中所见内容的前提下，干扰 LLM 渗透测试 agent。扰动只有满足以下条件才视为适用：agent 读取的是预置的扰动 HTML payload；`page_pure.html` 仅作为干净的人类参考页；扰动页面的渲染效果应尽可能与干净页一致；系统提示和页面副本不得向 agent 透露特殊字符防御的存在；日志保持简洁可读。

## 架构

模块化 Python 项目，代码在 `code/` 目录下。核心模块与流程：

- **`code/models.py`** — 数据类：`Fact`、`Scenario`、`ExperimentSpec`、`RenderedFact`、`EvaluationRow`。
- **`code/config.py`** — 常量、字符映射表（同形字、零宽字符等）、模型提供商配置。
- **`code/prompts.py`** — 所有提示词常量（Agent 解析 + DeepSeek 评估）。
- **`code/client.py`** — `NimChatClient`，OpenAI 兼容聊天 API 封装，支持 NVIDIA NIM / DeepSeek / ZhipuAI GLM 多提供商。
- **`code/evaluator.py`** — 评估逻辑：规则匹配 `evaluate_summary()` + DeepSeek LLM 裁判 `deepseek_evaluate_summary()` + 评分 + Agent 响应提取。
- **`code/reporter.py`** — 汇总 Markdown 生成：`write_scenario_summary_markdown()`、`write_summary_log()`。
- **`code/registry.py`** — Payload 注册表，映射场景+实验 → HTML payload 文件 + ground truth 事实。
- **`code/payloads.py`** — 工具模块：场景定义 `make_scenarios()`、投毒函数、HTML 渲染（用于构建新 payload）。
- **`code/main.py`** — CLI 入口 + 实验编排。
- **`code/payload_test/`** — 预置 HTML payload（Labyrinth、CorpNet 各 3 实验 + pure 参考页）+ `registry.json`。

**执行流程：** `main()` → `registry.get_payload_path()` 定位预置 HTML → `build_messages()` 构造对话 → agent 模型提取 → `evaluate_summary()` / `deepseek_evaluate_summary()` 评分 → `write_scenario_summary_markdown()` 生成汇总。

**自动重试：** 当 agent 响应被截断或 plain 基线得 0 分时，自动用更严格的 field-value-only prompt 重试一次。

## 场景

| Slug | 主题 | 风险类型 | 状态 |
|------|------|----------|------|
| `Labyrinth` | 翻译控制台，含 SSTI 线索 | 服务端模板注入 | **活跃** |
| `CorpNet` | 内部运维仪表盘，含命令注入入口 | 命令注入 + 特权脚本提权 | **活跃** |
| `locktalk_docs` | 内部 API 文档，含认证端点 | 认证绕过 / 权限提升 | 已定义未激活 |

## 命令

```bash
# 默认 3 项实验，单场景
python -m code.main --scenario Labyrinth

# 多场景（推荐：2 场景 × 3 实验 × 2 快模型，约 2 分钟）
python -m code.main --scenario Labyrinth CorpNet --models deepseek-chat glm-4-flash

# 全部已注册场景 + 全部实验
python -m code.main --scenario all --experiments all

# 离线验证 payload，不调 API
python -m code.main --scenario Labyrinth --generate-only

# 禁用 DeepSeek LLM 裁判（有 DEEPSEEK_API_KEY 时默认自动启用）
python -m code.main --scenario Labyrinth --no-llm-judge

# 列出已注册的场景 / 实验
python -m code.main --list-scenarios
python -m code.main --list-experiments

# 语法检查（全部模块）
python -m py_compile code/models.py code/config.py code/prompts.py code/client.py code/evaluator.py code/reporter.py code/registry.py code/payloads.py code/main.py
```

### 模型速度参考

| 模型 | 约耗时/实验 | 说明 |
|------|:--:|------|
| `deepseek-chat` | ~5s | 国内直连，推荐 |
| `glm-4-flash` | ~13s | 国内直连，免费 |
| `mistralai/mistral-large-3-675b-instruct-2512` | ~13s | NVIDIA NIM，注意 429 限流 |
| `minimaxai/minimax-m2.7` | ~40s | NVIDIA NIM，较慢 |
| `gpt-5.2` | ~50s | GPT Proxy，较慢 |
| `qwen/qwen3.5-397b-a17b` | 不稳定 | 偶发超时，不推荐 |

## 日志结构

```
log/YYYYMMDD_HHMMSS/
  └── <Scenario>/
        ├── page_pure.html                  # 干净参考页（从 payload 复制）
        ├── <Scenario>_summary.md           # 全量汇总
        ├── <Scenario>_success_summary.md   # 仅有效防御子集
        └── <experiment_name>/
              ├── <model-slug>.txt          # Agent 提取结果
              └── <model-slug>_evaluation.json
```

日志中不出现 HTML 代码——所有 payload 文件在 `code/payload_test/` 中预置。

## 环境配置

API Key 从 `.env` 文件读取。环境变量优先级：
- NVIDIA NIM: `NVIDIA_API_KEY` > `NVIDIA_NIM_API_KEY` > `NIM_API_KEY`
- DeepSeek: `DEEPSEEK_API_KEY`（用于 LLM judge）
- ZhipuAI GLM: `GLM_API_KEY`

也可通过 `--api-key` 传入。无 API Key 时自动降级为 `--generate-only` 模式。

## 新增实验

1. 使用 `code/payloads.py` 中的工具函数生成扰动 HTML
2. 将 HTML 放入 `code/payload_test/<Scenario>/`
3. 在 `code/payload_test/registry.json` 中注册实验名、HTML 文件名、ground truth 事实
4. 运行验证：`python -m code.main --scenario <Scenario> --generate-only`

## figure_comparison 目录

用于截图对比，验证扰动页面是否与干净页在浏览器中渲染一致。包含 `page_pure.html` / `page_perturbation_*.html` 和 Edge headless 截图。

## 文档文件

- `document/prompt.txt` — 完整提示词汇总（中英文）
- `document/特殊字符渲染效果.html` — 按适用/不适用分组渲染
- 旧单文件脚本 `pentest_agent_poison_sim.py` 保留作为参考（不再使用）
