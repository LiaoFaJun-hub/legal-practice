# -*- coding: utf-8 -*-
"""check_redlines.py · 跑在【推理轨】

校验四条红线 R1-R4，以及绝对化表述、S→F 混淆、结论条件化、禁确定数值。
用法：python check_redlines.py <推理轨文件>   （或 stdin）
退出码：0 = 无 P0；1 = 存在 P0。
"""
import re

import common as C


def main():
    text = C.load_text(C.read_arg())
    sec = C.split_sections(text)
    rep = C.Report("check_redlines")

    # ---------- R1 法条来源红线 ----------
    cites = C.find_citations(text)
    if not cites:
        rep.add("R1", "P1", False, "未发现任何法条引用（法律分析通常至少一处，请确认）")
    else:
        bad = []
        pending = 0
        for c in cites:
            if c["form"] == "bracket":
                f = [x.strip() for x in c["fields"]]
                if len(f) != 4 or any(x in C.PLACEHOLDERS for x in f):
                    bad.append("四元组元素缺失: " + c["raw"])
                    continue
                src = f[2]
                if ("记忆" in src) or ("模型" in src) or src in C.PLACEHOLDERS:
                    bad.append("来源非法（疑似模型记忆）: " + c["raw"])
                if f[3] in C.PENDING:
                    pending += 1
        if bad:
            rep.add("R1", "P0", False, "；".join(bad[:10]))
        else:
            rep.add("R1", "P0", True, f"引用四元组完整，共 {len(cites)} 处")
        if pending:
            rep.add("R1-占位", "P1", False,
                    f"{pending} 处引用的核验时间待补（合法占位，去重汇总为 1 条）")

    # ---------- R2 要件覆盖红线 ----------
    a4 = C.a_ids(C.section(sec, 4))
    a5 = C.a_state_ids(C.section(sec, 5))
    if not a4:
        rep.add("R2", "P1", False, "第四段未识别到要件清单编号 A1..An")
    elif a4 == a5:
        rep.add("R2", "P0", True, f"要件覆盖一致，共 {len(a4)} 项")
    else:
        missing = sorted(a4 - a5)
        extra = sorted(a5 - a4)
        rep.add("R2", "P0", False,
                f"要件集合不一致：第四段={sorted(a4)}，第五段判定={sorted(a5)}；"
                f"漏判={missing}，多判={extra}")

    # ---------- R3 对抗隔离红线（弱校验） ----------
    s5 = C.section(sec, 5)
    s6 = C.section(sec, 6)
    if s5 and s6:
        leaked = [ln.strip() for ln in s5.splitlines()
                  if len(ln.strip()) >= 12 and ln.strip() in s6]
        if leaked:
            rep.add("R3", "P1", False,
                    f"第六段疑似复用了第五段原文（{len(leaked)} 行），"
                    f"请确认已子 Agent 隔离：{leaked[0][:40]}…")
        else:
            rep.add("R3", "P1", True, "未发现第六段逐行复用第五段（弱校验通过）")

    # ---------- R4 留痕同屏红线 ----------
    keys = {"存疑清单": "存疑清单", "适用边界": "适用边界", "排除项": "排除项"}
    missing = []
    for k, label in keys.items():
        hit = (k in text) or (("排除清单" in text) and k == "排除项")
        if not hit:
            missing.append(label)
    if missing:
        rep.add("R4", "P0", False, "缺少清单：" + "、".join(missing))
    else:
        rep.add("R4", "P0", True, "存疑/边界/排除三清单齐全")

    # ---------- 绝对化表述 ----------
    for label, rx, lvl in (("硬性绝对化", C.ABSOLUTE_HARD, "P0"),
                           ("软性绝对化", C.ABSOLUTE_SOFT, "P1")):
        hits = rx.findall(text)
        if hits:
            rep.add(label, lvl, False, f"命中 {len(hits)} 处：" + "、".join(hits[:8]))
        else:
            rep.add(label, lvl, True, "无")

    # ---------- S→F 混淆 ----------
    conflicts = []
    blocks = re.split(r"(?=A\d+)", s5)
    for b in blocks:
        if ("✓" in b) and re.search(r"S\d+", b) and not re.search(r"F\d+", b):
            m = re.search(r"A\d+", b)
            conflicts.append(m.group(0) if m else "?")
    if conflicts:
        rep.add("S→F", "P0", False,
                "以下要件以单方陈述(S)支撑“成立(✓)”判定，属事实层级误用：" + "、".join(conflicts))
    else:
        rep.add("S→F", "P0", True, "无")

    # ---------- 结论条件化 ----------
    s8 = C.section(sec, 8)
    has_tend = "倾向于" in s8
    has_cond = ("若" in s8) and ("则" in s8)
    if s8 and has_tend and has_cond:
        rep.add("结论条件化", "P0", True, "含“倾向于”与“若…则”")
    else:
        detail = []
        if not has_tend:
            detail.append("缺“倾向于”限定")
        if not has_cond:
            detail.append("缺“若…则”反转条件")
        rep.add("结论条件化", "P0", False, "；".join(detail))

    # ---------- 禁确定数值 ----------
    num_rx = re.compile(r"胜诉率\s*[:：]?\s*\d|胜诉概率|赔偿(?:金|额)?\s*[:：]?\s*\d+\s*元|百分之\d+\s*[^，。]{0,6}(胜诉|败诉)")
    nums = num_rx.findall(text)
    if nums:
        rep.add("禁确定数值", "P1", False, "出现疑似确定数值断言：" + "、".join(nums[:8]))
    else:
        rep.add("禁确定数值", "P1", True, "无")

    raise SystemExit(rep.emit())


if __name__ == "__main__":
    main()
