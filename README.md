# LLM4CTF — Cheat Simulation

研究特殊 Unicode 字符扰动能否干扰 LLM 渗透测试 agent 的事实提取准确性，同时不影响人类在浏览器中的可见渲染。

**核心假说**：在网页 HTML 源码中注入不可见的 Unicode 控制字符（RLO、同形字等），人类看到的内容不变，但 LLM agent 解析时被误导，提取出错误信息。

## 快速开始

```bash
# 跑实验（2 场景 × 3 实验 × 2 快模型 ≈ 2 分钟）
python -m code.main --scenario Labyrinth CorpNet --models deepseek-chat gpt-5.4-nano

# 全 7 场景 + 全部实验
python -m code.main --scenario all --experiments all --models deepseek-chat gpt-5.4-nano gpt-4o-mini

# 合并日志生成带编号目录的汇总 PDF
python code/merge_log_summaries.py log/20260531_100611
```

API Key 配置在 `.env`，支持 DeepSeek / NVIDIA NIM / ZhipuAI / v36 / 讯型AI 六家提供商。

## 场景（7 个）

| Slug | 主题 | 风险类型 |
|------|------|----------|
| `Labyrinth` | 翻译控制台 | SSTI |
| `CorpNet` | 内部运维仪表盘 | 命令注入 + 提权 |
| `CornHub` | — | — |
| `Shocker` | — | — |
| `DC-2` / `DC-4` / `DC-6` | — | — |

每场景含 3 个预置实验：`right_to_left_override`（RLO 反转）、`mixed_homoglyph`（同形字替换）、`mixed_homoglyph_rlo`（叠加）。

## 模型（10 个快模型，按速度排）

| 模型 | 耗时 | 提供商 |
|------|:--:|------|
| `deepseek-chat` | ~1.3s | DeepSeek 直连 |
| `gpt-5.4-nano` | ~1.7s | 讯型AI |
| `gpt-4o-mini` | ~2.2s | v36 |
| `claude-sonnet-4-6` | ~2.3s | 讯型AI |
| `claude-haiku-4-5-20251001` | ~2.5s | 讯型AI |
| `gpt-4.1-nano` | ~2.5s | v36 |
| `gpt-5.4` | ~2.8s | v36 |
| `claude-opus-4-7` | ~2.9s | 讯型AI |
| `gpt-5.2` | ~3.0s | GPT Proxy |
| `kimi-k2.6` | ~3.3s | 讯型AI |

完整 15+ 模型见 `code/config.py`，速度测试见 `code/api_test/speed_report_*.pdf`。

## 项目结构

```
cheat_simulation/
├── code/                     # 源码（main/config/client/evaluator/payloads/registry/prompts/models）
│   ├── payload_test/         # 预置 HTML payload + registry.json
│   └── api_test/             # API Key 测试 + 速度基准
├── log/                      # 实验输出（gitignore）
│   └── YYYYMMDD_HHMMSS/
│       ├── summary.md        # 合并汇总（带编号+目录）
│       ├── summary.pdf
│       └── <Scenario>/       # 场景级汇总 + 各实验子目录
├── document/                 # 文档
└── .env                      # API Key（gitignore）
```

## 日志合并

```bash
python code/merge_log_summaries.py log/<时间戳>
```

自动扫描所有场景的 `_summary.md`，生成带层级编号（1 / 1.1 / 1.2.1）和目录的 `summary.md`，并转 PDF。不指定目录时默认取最新的 `log/` 子目录。
