"""
合并日志目录下各场景的 _summary.md → 带目录和编号的单文件 → 转 PDF。
用法: python code/merge_log_summaries.py log/20260531_102658
"""
import re
import sys
from pathlib import Path


def _scenario_label(path: Path) -> str:
    return path.name.replace("_summary.md", "")


def _number_headings(text: str, scenario_num: int) -> tuple:
    """给场景正文的标题加编号，返回 (numbered_text, toc_entries)。
    toc_entries: [(缩进级别, 编号, 标题文字)] 用于生成目录。
    """
    lines = text.splitlines()
    out: list[str] = []
    toc: list[tuple[int, str, str]] = []
    counters = [0, 0]  # counters[0]=h3计数, counters[1]=h4计数

    for line in lines:
        if line.startswith("#### "):
            counters[1] += 1
            label = line[5:]
            num = f"{scenario_num}.{counters[0]}.{counters[1]}"
            line = f"#### {num} {label}"
            toc.append((2, num, label))
        elif line.startswith("### "):
            counters[0] += 1
            counters[1] = 0
            label = line[4:]
            num = f"{scenario_num}.{counters[0]}"
            line = f"### {num} {label}"
            toc.append((1, num, label))
        elif line.startswith("## "):
            label = line[3:]
            num = str(scenario_num)
            line = f"## {num} {label}"
            toc.append((0, num, label))
        out.append(line)

    return "\n".join(out), toc


def merge_summaries(log_dir: Path) -> Path:
    summary_files = sorted(
        p for p in log_dir.rglob("*_summary.md")
        if p.parent.parent == log_dir
        and "_success_summary" not in p.name
    )
    if not summary_files:
        raise SystemExit(f"未找到 _summary.md 文件于 {log_dir}")

    timestamp = log_dir.name.replace("_", "-")
    model_names = []
    first_content = summary_files[0].read_text(encoding="utf-8")
    m = re.search(r"\| 特殊字符实验 \|(.+)\|", first_content)
    if m:
        model_names = [n.strip() for n in m.group(1).split("|") if n.strip()]

    merged = log_dir / "summary.md"
    all_toc: list[tuple[int, str, str]] = []  # (indent, num, label)

    with open(merged, "w", encoding="utf-8") as out:
        out.write("# 实验汇总报告\n\n")
        out.write(f"**时间戳**：{timestamp}　|　**场景数**：{len(summary_files)}　|　**模型**：{' · '.join(model_names) if model_names else '—'}\n\n")

        # ── 目录（先占位，等处理完所有场景再回填）──
        out.write("## 目录\n\n")
        toc_marker = "<!-- TOC_PLACEHOLDER -->\n"
        out.write(toc_marker)
        out.write("---\n\n")

        # ── 各场景正文 ──
        for i, sf in enumerate(summary_files):
            content = sf.read_text(encoding="utf-8")
            # 标题降级：# → ##, ## → ###, ### → ####
            content = re.sub(r"^### ", "#### ", content, flags=re.MULTILINE)
            content = re.sub(r"^## ", "### ", content, flags=re.MULTILINE)
            content = re.sub(r"^# ", "## ", content, flags=re.MULTILINE)

            # 加编号
            numbered, toc = _number_headings(content, i + 1)
            all_toc.extend(toc)

            if i > 0:
                out.write('<div style="page-break-before: always;"></div>\n\n')
            out.write(numbered)
            if not numbered.endswith("\n"):
                out.write("\n")
            out.write("\n")

    # ── 回填目录 ──
    toc_lines = []
    for indent, num, label in all_toc:
        prefix = "    " * indent + "-"
        toc_lines.append(f"{prefix} {num} {label}")
    toc_text = "\n".join(toc_lines) + "\n"

    full = merged.read_text(encoding="utf-8")
    full = full.replace(toc_marker, toc_text)
    merged.write_text(full, encoding="utf-8")

    print(f"[merge] {len(summary_files)} 个场景 → {merged}")
    return merged


def md_to_pdf(md_path: Path) -> Path:
    script = Path.home() / ".claude" / "scripts" / "md2pdf_preview.py"
    if not script.exists():
        raise SystemExit(
            f"md2pdf 脚本不存在: {script}\n"
            "先安装: pip install markdown pygments playwright && python -m playwright install chromium"
        )
    pdf_path = md_path.with_suffix(".pdf")
    import subprocess
    subprocess.run([sys.executable, str(script), str(md_path), str(pdf_path)], check=True)
    print(f"[pdf] {pdf_path}")
    return pdf_path


def main():
    if len(sys.argv) < 2:
        log_dir = max(
            (p for p in Path("log").iterdir() if p.is_dir()),
            key=lambda p: p.name, default=None,
        )
        if log_dir is None:
            raise SystemExit("用法: python code/merge_log_summaries.py <log_dir>")
    else:
        log_dir = Path(sys.argv[1])
    if not log_dir.is_dir():
        raise SystemExit(f"目录不存在: {log_dir}")

    merged = merge_summaries(log_dir)
    md_to_pdf(merged)
    print(f"[done] {merged} + {merged.with_suffix('.pdf')}")


if __name__ == "__main__":
    main()
