"""
LLM API 全量速度测试 — 5 个提供商
NVIDIA NIM | v36中转站 | 讯型AI | DeepSeek直连 | GLM直连
"""
import os, sys, json, time, requests
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"

def load_env(path):
    env = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"): continue
            if "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env

ENV = load_env(ENV_FILE)

PROMPT = """Extract the single most important version number or file path from this text:
The application runs on Spring Boot 1.5.10 and uses Apache Velocity 1.7 as template engine.
Reply with just the value, nothing else."""

ROUNDS = 3
MAX_TOKENS = 800

MODELS = [
    # ═══ 讯型AI (国内直连, azpro.xunxkj.cn) ═══
    ("gpt-5.4-nano",         "http://azpro.xunxkj.cn/v1",           "gpt-5.4-nano",         ENV.get("XUNXAI_API_KEY",""), "讯型AI"),
    ("kimi-k2.6",            "http://azpro.xunxkj.cn/v1",           "kimi-k2.6",            ENV.get("XUNXAI_API_KEY",""), "讯型AI"),
    ("deepseek-chat",        "http://azpro.xunxkj.cn/v1",           "deepseek-chat",        ENV.get("XUNXAI_API_KEY",""), "讯型AI"),
    ("claude-sonnet-4-6",    "http://azpro.xunxkj.cn/v1",           "claude-sonnet-4-6",    ENV.get("XUNXAI_API_KEY",""), "讯型AI"),
    ("claude-opus-4-7",      "http://azpro.xunxkj.cn/v1",           "claude-opus-4-7",      ENV.get("XUNXAI_API_KEY",""), "讯型AI"),
    ("claude-haiku-4-5",     "http://azpro.xunxkj.cn/v1",           "claude-haiku-4-5-20251001", ENV.get("XUNXAI_API_KEY",""), "讯型AI"),
    ("gemini-3.5-flash",     "http://azpro.xunxkj.cn/v1",           "gemini-3.5-flash",     ENV.get("XUNXAI_API_KEY",""), "讯型AI"),
    ("deepseek-v4-flash",    "http://azpro.xunxkj.cn/v1",           "deepseek-v4-flash",    ENV.get("XUNXAI_API_KEY",""), "讯型AI"),
    ("gpt-5.5",              "http://azpro.xunxkj.cn/v1",           "gpt-5.5",              ENV.get("XUNXAI_API_KEY",""), "讯型AI"),
    ("MiniMax-M2.7",         "http://azpro.xunxkj.cn/v1",           "MiniMax-M2.7",         ENV.get("XUNXAI_API_KEY",""), "讯型AI"),
    ("glm-5",                "http://azpro.xunxkj.cn/v1",           "glm-5",                ENV.get("XUNXAI_API_KEY",""), "讯型AI"),

    # ═══ v36 中转站 (api.v36.cm) ═══
    ("gpt-5.2",              "https://api.v36.cm/v1",               "gpt-5.2",              ENV.get("V36_API_KEY",""), "v36"),
    ("gpt-5.4",              "https://api.v36.cm/v1",               "gpt-5.4",              ENV.get("V36_API_KEY",""), "v36"),
    ("gpt-5.1",              "https://api.v36.cm/v1",               "gpt-5.1",              ENV.get("V36_API_KEY",""), "v36"),
    ("gpt-4o-mini",          "https://api.v36.cm/v1",               "gpt-4o-mini",          ENV.get("V36_API_KEY",""), "v36"),
    ("gpt-4.1-nano",         "https://api.v36.cm/v1",               "gpt-4.1-nano",         ENV.get("V36_API_KEY",""), "v36"),
    ("gpt-5-mini",           "https://api.v36.cm/v1",               "gpt-5-mini",           ENV.get("V36_API_KEY",""), "v36"),
    ("o4-mini",              "https://api.v36.cm/v1",               "o4-mini",              ENV.get("V36_API_KEY",""), "v36"),
    ("o3-mini",              "https://api.v36.cm/v1",               "o3-mini",              ENV.get("V36_API_KEY",""), "v36"),

    # ═══ NVIDIA NIM key1 ═══
    ("Mistral Large", "https://integrate.api.nvidia.com/v1", "mistralai/mistral-large-3-675b-instruct-2512", ENV.get("NVIDIA_API_KEY",""), "NIM1"),
    ("Qwen 3.5",      "https://integrate.api.nvidia.com/v1", "qwen/qwen3.5-397b-a17b", ENV.get("NVIDIA_API_KEY",""), "NIM1"),
    ("MiniMax M2.7",  "https://integrate.api.nvidia.com/v1", "minimaxai/minimax-m2.7", ENV.get("NVIDIA_API_KEY",""), "NIM1"),

    # ═══ NVIDIA NIM key2 ═══
    ("Mistral Large", "https://integrate.api.nvidia.com/v1", "mistralai/mistral-large-3-675b-instruct-2512", ENV.get("NVIDIA_API_KEY_2",""), "NIM2"),
    ("DS V4 Pro",     "https://integrate.api.nvidia.com/v1", "deepseek-ai/deepseek-v4-pro", ENV.get("NVIDIA_API_KEY_2",""), "NIM2"),
    ("DS V4 Flash",   "https://integrate.api.nvidia.com/v1", "deepseek-ai/deepseek-v4-flash", ENV.get("NVIDIA_API_KEY_2",""), "NIM2"),

    # ═══ 直连 ═══
    ("deepseek-chat", "https://api.deepseek.com/v1",        "deepseek-chat", ENV.get("DEEPSEEK_API_KEY",""), "直连"),
    ("glm-4-flash",   "https://open.bigmodel.cn/api/paas/v4","glm-4-flash",  ENV.get("GLM_API_KEY",""), "直连"),
]

def test_one(cfg):
    name, base, model, key, tag = cfg
    if not key:
        return {"name": f"{name} ({tag})", "tag": tag, "model": model, "skipped": True, "avg_ms": 0, "success_rate": 0, "rounds": []}

    disp = f"{name} ({tag})"
    print(f"\n{'─'*45}\n🔍 {disp} — {model}")
    rounds = []
    for i in range(ROUNDS):
        t0 = time.time()
        try:
            r = requests.post(f'{base.rstrip("/")}/chat/completions', json={
                "model": model, "max_tokens": MAX_TOKENS, "temperature": 0.0,
                "messages": [{"role": "user", "content": PROMPT}],
            }, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            timeout=(15, 120), proxies={"http": None, "https": None})

            ms = round((time.time() - t0) * 1000)
            data = r.json()
            msg = data.get("choices", [{}])[0].get("message", {})
            content = msg.get("content") or msg.get("reasoning_content") or ""
            rd = {"round": i+1, "status": r.status_code, "ms": ms, "content_len": len(content),
                  "preview": content[:60].replace("\n", "\\n").replace("<think>", "[think]")}
            rounds.append(rd)
            ok = "✅" if content.strip() else "⚠️空"
            print(f"  R{i+1} {ok} {ms/1000:.1f}s | {rd['preview'][:55]}")
        except Exception as e:
            ms = round((time.time() - t0) * 1000)
            rounds.append({"round": i+1, "status": 0, "ms": ms, "content_len": 0, "preview": "", "error": str(e)[:120]})
            print(f"  R{i+1} ❌ {ms/1000:.1f}s | {str(e)[:80]}")
        if i < ROUNDS-1: time.sleep(0.15)

    ok_rds = [r for r in rounds if r["status"] == 200 and r["content_len"] > 0]
    avg = sum(r["ms"] for r in ok_rds) / len(ok_rds) if ok_rds else 999999
    sr = len(ok_rds) / len(rounds) if rounds else 0
    print(f"  📊 成功率={sr:.0%} 平均={avg/1000:.1f}s")
    return {"name": disp, "tag": tag, "model": model, "skipped": False, "avg_ms": round(avg), "success_rate": round(sr,3), "rounds": rounds}


def gen_report(results, out_dir):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    valid = sorted([r for r in results if not r.get("skipped") and r["success_rate"]>0], key=lambda x: x["avg_ms"])
    failed = [r for r in results if not r.get("skipped") and r["success_rate"]==0]
    skipped = [r for r in results if r.get("skipped")]

    md = [
        f"# LLM API 全量速度测试报告",
        "",
        f"**测试时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | **轮次**: {ROUNDS}轮/模型 | **max_tokens**: {MAX_TOKENS} | **temperature**: 0.0",
        "",
        f"**提供商**: NVIDIA NIM (key1+key2) | v36 中转站 | 讯型AI 中转站 | DeepSeek 直连 | GLM 直连",
        "",
        "---",
        "",
        "## 🏆 速度排名 (共 {} 个模型)".format(len(valid)),
        "",
        "| 排名 | 模型 | 提供商 | 平均耗时 | R1 | R2 | R3 | 波动 |",
        "|------|------|--------|----------|----|----|----|------|",
    ]
    for i, r in enumerate(valid, 1):
        tms = [f"{rd['ms']/1000:.1f}s" for rd in r["rounds"] if rd["status"]==200 and rd["content_len"]>0]
        tvals = [rd["ms"]/1000 for rd in r["rounds"] if rd["status"]==200 and rd["content_len"]>0]
        if tvals:
            dev = max(tvals) - min(tvals)
            if dev < 0.5: stab = "🟢"
            elif dev < 2: stab = "🟡"
            elif dev < 5: stab = "🟠"
            else: stab = "🔴"
        else:
            stab = "—"
        avg_s = r["avg_ms"]/1000
        if avg_s < 2:
            speed_icon = "⚡⚡"
        elif avg_s < 3:
            speed_icon = "⚡"
        elif avg_s < 8:
            speed_icon = "✅"
        elif avg_s < 20:
            speed_icon = "🟡"
        else:
            speed_icon = "🐢"
        md.append(f"| {i} | {speed_icon} **{r['name']}** | {r['tag']} | **{avg_s:.1f}s** | {tms[0]} | {tms[1] if len(tms)>1 else '-'} | {tms[2] if len(tms)>2 else '-'} | {stab} |")

    if failed:
        md.extend(["", "---", "", "## ❌ 全部失败", "", "| 模型 | 错误 |", "|------|------|"])
        for r in failed:
            err = r["rounds"][0].get("error","?")[:100] if r.get("rounds") else "无数据"
            md.append(f"| {r['name']} | {err} |")

    # 分提供商总结
    md.extend(["", "---", "", "## 📊 分提供商对比", ""])
    for tag in ["讯型AI", "v36", "NIM1", "NIM2", "直连"]:
        group = [r for r in valid if r["tag"] == tag]
        if not group: continue
        avg_all = sum(r["avg_ms"] for r in group) / len(group)
        md.append(f"### {tag} ({len(group)} 个模型, 平均 {avg_all/1000:.1f}s)")
        md.append("")
        for r in group:
            md.append(f"- **{r['name']}**: {r['avg_ms']/1000:.1f}s (成功率 {r['success_rate']:.0%})")
        md.append("")

    # 推荐
    md.extend([
        "---", "", "## 💡 实验推荐", "",
        "### 🥇 第一梯队 — 极快稳定 (<2s)",
    ])
    for r in valid:
        if r["avg_ms"] < 2000:
            tvals = [rd["ms"]/1000 for rd in r["rounds"] if rd["status"]==200 and rd["content_len"]>0]
            dev = f"波动{max(tvals)-min(tvals):.1f}s" if tvals else "?"
            md.append(f"- **{r['name']}** ({r['tag']}) — {r['avg_ms']/1000:.1f}s, {dev}")
    md.extend(["", "### 🥈 第二梯队 — 快速稳定 (2-3s)", ""])
    for r in valid:
        if 2000 <= r["avg_ms"] < 3000:
            md.append(f"- **{r['name']}** ({r['tag']}) — {r['avg_ms']/1000:.1f}s")
    md.extend(["", "### 🥉 第三梯队 — 可用 (3-8s)", ""])
    for r in valid:
        if 3000 <= r["avg_ms"] < 8000:
            md.append(f"- **{r['name']}** ({r['tag']}) — {r['avg_ms']/1000:.1f}s")
    md.extend(["", "### ⚠️ 不推荐 (>8s 或 不稳定)", ""])
    for r in valid:
        if r["avg_ms"] >= 8000:
            md.append(f"- **{r['name']}** ({r['tag']}) — {r['avg_ms']/1000:.1f}s")
    for r in failed:
        md.append(f"- ~~{r['name']}~~ — 全部失败")

    md_text = "\n".join(md)
    md_path = out_dir / f"speed_report_{ts}.md"
    md_path.write_text(md_text, encoding="utf-8")

    pdf_path = out_dir / f"speed_report_{ts}.pdf"
    try:
        from markdown import markdown as md2html
        html_body = md2html(md_text, extensions=["tables", "fenced_code"])
        html = f"""<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8">
<style>
body{{font-family:'Segoe UI','Microsoft YaHei',sans-serif;max-width:1000px;margin:0 auto;padding:35px;color:#1a1a2e;}}
h1{{border-bottom:3px solid #2563eb;padding-bottom:8px;font-size:1.6em;}}
h2{{border-bottom:2px solid #e2e8f0;padding-bottom:6px;margin-top:26px;font-size:1.2em;}}
h3{{font-size:1.05em;margin-top:20px;}}
table{{border-collapse:collapse;width:100%;margin:8px 0;font-size:12px;}}
th,td{{border:1px solid #e2e8f0;padding:5px 8px;text-align:left;}}
th{{background:#f1f5f9;font-weight:600;}}
tr:nth-child(even){{background:#f8fafc;}}
code{{background:#f1f5f9;padding:1px 4px;border-radius:3px;font-size:11px;}}
</style></head><body>{html_body}</body></html>"""
        html_path = out_dir / f"speed_report_{ts}.html"
        html_path.write_text(html, encoding="utf-8")

        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(html_path.as_uri(), wait_until="networkidle")
                page.pdf(path=str(pdf_path), format="A4", margin={"top":"20px","bottom":"20px","left":"20px","right":"20px"})
                browser.close()
            print(f"\n📄 PDF: {pdf_path}")
        except Exception as e:
            print(f"\n⚠️ PDF失败: {e}\n📄 HTML: {html_path}")
    except ImportError:
        print(f"\n⚠️ markdown未安装\n📄 MD: {md_path}")

    return md_path


def main():
    for v in ("HTTP_PROXY","HTTPS_PROXY","http_proxy","https_proxy","ALL_PROXY","all_proxy"):
        os.environ.pop(v, None)

    print(f"{'='*50}")
    print(f"🚀 全量 API 速度测试: {len(MODELS)} 模型 × {ROUNDS}轮")
    print(f"{'='*50}")

    results = []
    for cfg in MODELS:
        results.append(test_one(cfg))
        time.sleep(0.1)

    print(f"\n{'='*50}\n📊 最终排名\n{'='*50}")
    valid = sorted([r for r in results if not r.get("skipped") and r["success_rate"]>0], key=lambda x: x["avg_ms"])
    for i, r in enumerate(valid, 1):
        tms = [f"{rd['ms']/1000:.1f}s" for rd in r["rounds"] if rd["status"]==200 and rd["content_len"]>0]
        print(f"  {i:2d}. {r['name']:<32s} {r['avg_ms']/1000:>5.1f}s  [{', '.join(tms)}]")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw = out_dir / f"raw_{ts}.json"
    with open(raw, "w", encoding="utf-8") as f: json.dump(results, f, ensure_ascii=False, indent=2)

    gen_report(results, out_dir)
    print(f"\n📁 原始数据: {raw}\n✅ 完成!")

out_dir = Path(__file__).resolve().parent

if __name__ == "__main__":
    main()
