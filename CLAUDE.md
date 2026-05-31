# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 目标

研究特殊字符扰动能否在不影响人类用户浏览器渲染的前提下，干扰 LLM 渗透测试 agent 的事实提取准确性。约束：agent 只读预置的扰动 HTML；`page_pure.html` 仅作人类参考；扰动不得暴露给 agent；日志简洁。

## 目录结构

```
cheat_simulation/
├── code/                          # 全部源码
│   ├── main.py                    # CLI 入口 + 实验编排 + DeepSeek 汇总生成
│   ├── merge_log_summaries.py     # 合并各场景 summary.md → 带编号+目录 → PDF
│   ├── models.py                  # Fact / Scenario / ExperimentSpec / EvaluationRow
│   ├── config.py                  # 常量、字符映射表、MODEL_PROVIDER_CONFIG、DEFAULT_MODELS
│   ├── prompts.py                 # Agent 解析 + LLM 裁判 + 汇总生成 提示词
│   ├── client.py                  # NimChatClient，OpenAI 兼容 /chat/completions
│   ├── evaluator.py               # 规则匹配 + DeepSeek 裁判 + 字段提取 + 评分
│   ├── payloads.py                # 场景定义 + 投毒函数（30+ 方法）+ HTML 渲染
│   ├── registry.py                # 读 registry.json → 场景+实验→HTML+事实
│   ├── payload_test/              # 预置 HTML payload + registry.json + 同形字对照表
│   └── api_test/                  # API Key 可用性测试 + 模型速度基准
├── log/                           # 实验输出（gitignore，每次运行新建时间戳子目录）
├── document/                      # 文档（渲染效果、实验结果、prompt 汇总等）
├── .env                           # API Key（gitignore）
└── .vscode/                       # Markdown 表格换行 CSS
```

## 架构

**执行流程：** `main()` → `registry.get_payload_path()` 读预置 HTML → `build_messages()` 包装对话 → agent 模型提取 → `evaluate_summary()` 规则评分 → `deepseek_evaluate_summary()` LLM 裁判（有 `DEEPSEEK_API_KEY` 时自动启用）→ `generate_summary_with_deepseek()` 调 DeepSeek 生成 `_summary.md`

**自动重试：** agent 响应截断或 plain 基线得 0 分时，用更严格的 field-value-only prompt 重试一次。

## 场景（7 个，全部可用）

| Slug | 主题 | 风险类型 |
|------|------|----------|
| `Labyrinth` | 翻译控制台，含 SSTI 线索 | 服务端模板注入 |
| `CorpNet` | 内部运维仪表盘 | 命令注入 + 特权脚本提权 |
| `CornHub` | — | — |
| `Shocker` | — | — |
| `DC-2` / `DC-4` / `DC-6` | — | — |

每场景含 3 个预置实验：`right_to_left_override`、`mixed_homoglyph`、`mixed_homoglyph_rlo`。

## 命令

```bash
# 推荐快跑（2 场景 × 2 快模型，约 2 分钟）
python -m code.main --scenario Labyrinth CorpNet --models deepseek-chat gpt-5.4-nano

# 全 7 场景 + 全部实验（建议仅用快模型）
python -m code.main --scenario all --experiments all --models deepseek-chat gpt-5.4-nano gpt-4o-mini

# 离线验证 payload，不调 API
python -m code.main --scenario Labyrinth --generate-only

# 禁用 LLM 裁判
python -m code.main --scenario Labyrinth --no-llm-judge

# 列出场景 / 实验
python -m code.main --list-scenarios
python -m code.main --list-experiments

# API 速度测试
python code/api_test/speed_test.py

# 合并日志生成汇总 PDF
python code/merge_log_summaries.py log/20260531_100611
```

## 模型

`DEFAULT_MODELS`（10 个，按速度排序）：

| 模型 | 耗时 | 提供商 | 环境变量 |
|------|:--:|------|------|
| `deepseek-chat` | ~1.3s | 直连 | `DEEPSEEK_API_KEY` |
| `gpt-5.4-nano` | ~1.7s | 讯型AI | `XUNXAI_API_KEY` |
| `gpt-4o-mini` | ~2.2s | v36 | `V36_API_KEY` |
| `claude-sonnet-4-6` | ~2.3s | 讯型AI | `XUNXAI_API_KEY` |
| `claude-haiku-4-5-20251001` | ~2.5s | 讯型AI | `XUNXAI_API_KEY` |
| `gpt-4.1-nano` | ~2.5s | v36 | `V36_API_KEY` |
| `gpt-5.4` | ~2.8s | v36 | `V36_API_KEY` |
| `claude-opus-4-7` | ~2.9s | 讯型AI | `XUNXAI_API_KEY` |
| `gpt-5.2` | ~3.0s | GPT Proxy | `GPT_API_KEY` |
| `kimi-k2.6` | ~3.3s | 讯型AI | `XUNXAI_API_KEY` |

完整 15+ 模型见 `code/config.py` `MODEL_PROVIDER_CONFIG`。

## 环境配置

API Key 从 `.env` 读取（gitignore）。提供商 → 环境变量：

| 提供商 | 环境变量 |
|--------|----------|
| NVIDIA NIM | `NVIDIA_API_KEY` / `NVIDIA_API_KEY_2` |
| DeepSeek | `DEEPSEEK_API_KEY` |
| ZhipuAI | `GLM_API_KEY` |
| GPT Proxy | `GPT_API_KEY` |
| v36 中转 | `V36_API_KEY` |
| 讯型AI | `XUNXAI_API_KEY` |

无任何 Key 时自动降级为 `--generate-only`。

## 日志结构

```
log/YYYYMMDD_HHMMSS/<Scenario>/
├── <Scenario>_summary.md           # DeepSeek 生成
└── <experiment>/
    ├── <model-slug>.txt            # Agent 原始输出
    └── <model-slug>_evaluation.json
```

## 新增场景/实验

1. 生成扰动 HTML 放入 `code/payload_test/<Scenario>/`
2. 在 `code/payload_test/registry.json` 注册：实验名、HTML 路径、ground truth 事实列表
3. `python -m code.main --scenario <Scenario> --generate-only` 验证

Payload 构造约定见 `code/payload_test/同形字对照表.html` 顶部（5 条规则）。
