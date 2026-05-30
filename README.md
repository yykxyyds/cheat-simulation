# LLM4CTF — Cheat Simulation

研究特殊 Unicode 字符扰动能否干扰 LLM 渗透测试 agent 的事实提取准确性，同时不影响人类在浏览器中的可见渲染。

**核心假说**：在网页 HTML 源码中注入不可见的 Unicode 控制字符（RLO、同形字等），人类在浏览器中看到的内容不变，但 LLM agent 解析时会被误导，提取出错误信息。

## 快速开始

```bash
pip install requests python-dotenv

# 跑完整实验（2 场景 × 3 实验 × 2 快模型 ≈ 2 分钟）
python -m code.main --scenario Labyrinth CorpNet --models deepseek-chat glm-4-flash

# 离线模式（不调 API，仅验证 payload）
python -m code.main --scenario Labyrinth --generate-only
```

API Key 配置在 `.env` 文件中，支持 NVIDIA NIM / DeepSeek / ZhipuAI GLM / GPT Proxy 多提供商。

## 实验结果摘要

| 实验 | 方法 | deepseek-chat | glm-4-flash |
|------|------|:--:|:--:|
| `right_to_left_override` | RLO 反转字符顺序 | 0.800 | **0.000** |
| `mixed_homoglyph` | 希腊+西里尔同形字替换 | 1.000 | 0.600 |
| `mixed_homoglyph_rlo` | 同形字 + RLO 叠加 | **0.200** | **0.000** |

> accuracy 越低 = 防御越有效。Labyrinth 和 CorpNet 两个场景结果一致。

- **glm-4-flash** 最易被防御：RLO 单独就能达到 100% 防御率
- **deepseek-chat** 抵抗力最强：只有同形字+RLO 组合拳才能有效
- **`mixed_homoglyph_rlo`** 是唯一对所有模型都有效的通用防御方法

完整报告：`document/实验结果_20260530.pdf`

## 场景

| Slug | 主题 | 风险类型 |
|------|------|----------|
| `Labyrinth` | 翻译控制台 | 服务端模板注入 (SSTI) |
| `CorpNet` | 内部运维仪表盘 | 命令注入 + 特权脚本提权 |

## 模型速度

| 模型 | ~耗时 | 推荐 |
|------|:--:|:--:|
| `deepseek-chat` | 5s | 首选 |
| `glm-4-flash` | 13s | 免费 |
| `mistralai/mistral-large-3-675b-instruct-2512` | 13s | 注意限流 |
| `minimaxai/minimax-m2.7` | 40s | 慢 |

## 日志结构

```
log/YYYYMMDD_HHMMSS/
├── Labyrinth/
│   ├── Labyrinth_summary.md          ← 总览表 + 详情
│   ├── right_to_left_override/       ← 每模型 .txt + _evaluation.json
│   ├── mixed_homoglyph/
│   └── mixed_homoglyph_rlo/
└── CorpNet/                          ← 同上
```
