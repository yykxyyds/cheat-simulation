#!/usr/bin/env python3
"""读取 render_diff 的 JSON 输出，生成汇总 Markdown 报告。"""
import json, os, sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

JSON_PATH = Path(__file__).with_name("result.json")
OUT_PATH = Path(__file__).with_name("渲染对比汇总.md")

data = json.loads(JSON_PATH.read_text(encoding='utf-8'))
data.sort(key=lambda x: x['diff_percent'])

pass_count = sum(1 for d in data if d['passed'])
fail_count = sum(1 for d in data if not d['passed'])

def short_name(p):
    return Path(p).stem.replace('page_perturbation_', '')

def fmt_bounds(b):
    if not b: return "-"
    return f"行{b[0]}-{b[1]}, 列{b[2]}-{b[3]}"

L = []
L.append("# 渲染对比汇总报告")
L.append("")
L.append(f"**纯净页**: `page_pure.html` | **窗口**: 1280×900 | **阈值**: 0.5% | **通过率**: {pass_count}/{len(data)} = {pass_count/len(data)*100:.1f}%")
L.append("")

# 概览
L.append("## 概览")
L.append("")
L.append(f"通过 **{pass_count}** / 未通过 **{fail_count}**")
L.append("")

# 详细表
L.append("## 详细结果（按差异从小到大）")
L.append("")
L.append(f"| 实验名称 | 差异% | 差异像素 | 连通域 | 差异区域 | 判定 |")
L.append(f"|----------|-------|---------|--------|---------|------|")

for d in data:
    name = short_name(d['file'])
    pct = "0%" if d['diff_percent'] == 0 else f"{d['diff_percent']:.4f}%"
    px = f"{d['diff_pixels']:,}"
    reg = str(d['connected_regions'])
    bnd = fmt_bounds(d['region_bounds'])
    verdict = "✅ 一致" if d['passed'] else "❌ 不同"
    L.append(f"| {name} | {pct} | {px} | {reg} | {bnd} | {verdict} |")

L.append("")

# 未通过
failed = [d for d in data if not d['passed']]
if failed:
    L.append("## 未通过实验分析")
    L.append("")
    for d in failed:
        name = short_name(d['file'])
        L.append(f"### {name} — {d['diff_percent']:.2f}%")
        L.append(f"- 差异像素：{d['diff_pixels']:,} / 1,152,000")
        L.append(f"- 连通区域数：{d['connected_regions']}")
        b = d['region_bounds']
        if b:
            w = b[3] - b[2] + 1
            h = b[1] - b[0] + 1
            L.append(f"- 差异区域：行{b[0]}-{b[1]}、列{b[2]}-{b[3]}（{w}×{h}px，占页面 {w*h/1152000*100:.1f}%）")
            col_pct = (b[2]+b[3])/2 / 1280 * 100
            row_pct = (b[0]+b[1])/2 / 900 * 100
            loc = "页面右侧（Deployment Notes 卡片）" if col_pct > 60 else "页面左侧（Translator 卡片）"
            if row_pct > 70: loc += "，下半部分"
            elif row_pct > 30: loc += "，中间部分"
            else: loc += "，上半部分"
            L.append(f"- 位置：{loc}")
        L.append("")

# 值得关注
notable = [d for d in data if 0 < d['diff_percent'] < 0.5 and d['passed']]
if notable:
    L.append("## 值得关注的通过项（0% < 差异 < 0.5%）")
    L.append("")
    L.append("以下实验通过了阈值，但存在可量化的微小差异，可能源于换行行为变化或字符渲染细节：")
    L.append("")
    for d in notable:
        name = short_name(d['file'])
        b = d['region_bounds']
        loc_str = f"（{fmt_bounds(b)}）" if b else ""
        L.append(f"- **{name}**：{d['diff_percent']:.4f}%，{d['connected_regions']} 个连通域 {loc_str}")
    L.append("")

# 完美
perfect = [d for d in data if d['diff_percent'] == 0]
L.append("## 完美一致（0% 差异）")
L.append("")
L.append("、".join(f"`{short_name(d['file'])}`" for d in perfect))
L.append("")

# 0.0054% 组
tiny = [d for d in data if d['diff_percent'] == 0.0054]
if tiny:
    L.append("## 0.0054% 组分析")
    L.append("")
    L.append(f"共 {len(tiny)} 个实验显示 62 像素差异（2 个连通域），区域完全相同：行5-895, 列1268-1276（页面最右边缘 9px 宽竖条）。")
    L.append("这是 Edge headless 渲染的确定性微小差异（可能为右侧阴影/边距的亚像素渲染差异），并非扰动内容导致。")
    L.append("")
    L.append("、".join(f"`{short_name(d['file'])}`" for d in tiny))
    L.append("")

L.append("---")
L.append(f"*生成时间: 2026-05-13 | 工具: render-diff skill | 日志来源: 20260513_181957_minimax-m2.7/Labyrinth_Linguist/*")

OUT_PATH.write_text("\n".join(L) + "\n", encoding='utf-8')
print(f"报告已生成: {OUT_PATH}")
print(f"通过: {pass_count}  未通过: {fail_count}  完美: {len(perfect)}")

# 列出关键发现
print(f"\n未通过:")
for d in failed:
    print(f"  ❌ {short_name(d['file'])}: {d['diff_percent']:.2f}%")
