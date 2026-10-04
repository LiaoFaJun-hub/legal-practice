# -*- coding: utf-8 -*-
"""validate_delivery.py · 跑在【行文轨】（交付物）

校验交付物（律师文体意见书）：
  1) 内容完整性：三清单齐、条件式结论、引用可溯源
  2) 文体合规：机械符号不外泄正文、无绝对化表述
  3) 附录齐全：引用索引 / 人审复核清单 / 推理链路自检表
用法：python validate_delivery.py <交付物文件>   （或 stdin）
退出码：0 = 无 P0；1 = 存在 P0。
"""
import re

import common as C


def has_any(text, words):
    return any(w in text for w in words)


def main():
    text = C.load_text(C.read_arg())
    rep = C.Report("validate_delivery")

    # 正文 = 附录标题行之前（行首的"附录一/附录A"，避免误切正文内联引用）
    m = re.search(r"(?m)^[#\s>]*附录\s*[一1A]", text)
    body = text[:m.start()] if m else text

    # ---------- 三清单（律师化呈现，仍须齐）----------
    has_doubt = has_any(body, ["尚待查明", "尚待核实", "存疑", "待证", "待核实", "尚待证明"])
    has_bound = has_any(body, ["适用范围", "适用边界", "本意见的适用范围"])
    has_excl = has_any(body, ["未予涉及", "未处理", "排除", "未涉及"])
    s = []
    if not has_doubt:
        s.append("存疑类")
    if not has_bound:
        s.append("边界类")
    if not has_excl:
        s.append("排除类")
    rep.add("三清单齐", "P0", not s, ("缺：" + "、".join(s)) if s else "存疑/边界/排除齐备")

    # ---------- 条件式结论 ----------
    cond = ("倾向于" in body) and ("若" in body) and ("则" in body)
    rep.add("结论条件化", "P0", cond,
            "结论须含“倾向于”与“若…则”反转条件" if not cond else "含条件式结论")

    # ---------- 机械符号外泄（正文不得出现）----------
    leak = []
    for rx, label in ((r"A\d+", "要件编号A?"),
                      (r"D\d+", "抗辩编号D?"),
                      (r"V\d+", "漏洞编号V?"),
                      (r"(?<![A-Za-z])C\d+", "冲突编号C?"),
                      (r"F\d+", "事实编号F?"),
                      (r"S\d+", "陈述编号S?"),
                      (r"U\d+", "存疑编号U?")):
        hits = re.findall(rx, body)
        if hits:
            leak.append(f"{label}({len(hits)})")
    sym = [x for x in C.STATE_SYMBOLS if x in body]
    if sym:
        leak.append("判定符号" + "".join(sym))
    rep.add("符号不外泄", "P0", not leak,
            ("正文含机械符号：" + "、".join(leak)) if leak else "正文无机械符号外泄")

    # ---------- 绝对化表述 ----------
    hard = C.ABSOLUTE_HARD.findall(body)
    soft = C.ABSOLUTE_SOFT.findall(body)
    rep.add("绝对化(硬)", "P0", not hard, "命中：" + "、".join(hard[:8]) if hard else "无")
    rep.add("绝对化(软)", "P1", not soft, "命中：" + "、".join(soft[:8]) if soft else "无")

    # ---------- 引用可溯源（行文轨正文可引附录 Ref，附录须有四元组或待核验）----------
    cites = C.find_citations(text)
    ref_body = "Ref" in body or "附录一" in text
    if not cites and not ref_body:
        rep.add("引用可溯源", "P1", False, "未发现引用或指向附录的交叉引用")
    else:
        rep.add("引用可溯源", "P1", True, f"引用/交叉引用 {len(cites)} 处")

    # ---------- 附录齐全 ----------
    has_app1 = ("引用索引" in text) or ("附录一" in text)
    has_app2 = ("复核清单" in text) or ("人审" in text)
    has_app3 = "自检" in text
    miss = []
    if not has_app1:
        miss.append("附录一引用索引")
    if not has_app2:
        miss.append("附录二人审复核清单")
    if not has_app3:
        miss.append("附录三推理链路自检表")
    rep.add("附录齐全", "P1", not miss, ("缺：" + "、".join(miss)) if miss else "三附录齐全")

    raise SystemExit(rep.emit())


if __name__ == "__main__":
    main()
