# -*- coding: utf-8 -*-
"""check_dod.py · 跑在【推理轨】

逐段 DoD 门禁校验（启发式）。缺整段计 P0，其余结构缺失计 P1。
用法：python check_dod.py <推理轨文件>   （或 stdin）
退出码：0 = 无 P0；1 = 存在 P0。
"""
import re

import common as C


def has_any(text, words):
    return any(w in text for w in words)


def s(rep, cid, level, ok, detail=""):
    rep.add(cid, level, ok, detail)


def main():
    text = C.load_text(C.read_arg())
    sec = C.split_sections(text)
    rep = C.Report("check_dod")

    # 整段缺失（P0）
    for num, name in enumerate(C.BAGU_NAMES, start=1):
        present = name in text
        s(rep, f"存在性-{num}{name}", "P0", present,
          "" if present else f"缺少第{num}段（{name}）")

    # 第一段 破题
    t = C.section(sec, 1)
    if t:
        shell = [w for w in ("违约责任认定", "性质认定", "效力问题", "责任认定") if w in t]
        s(rep, "破题-无空壳术语", "P1", not shell, f"疑似空壳术语：{shell}" if shell else "无空壳术语")
        s(rep, "破题-L/F分离", "P1", ("法律命题" in t) and ("事实命题" in t),
          "须含“法律命题”与“事实命题”并列")
        excl = len(re.findall(r"排除", t))
        s(rep, "破题-排除项≥2", "P1", excl >= 2, f"检测到“排除”出现 {excl} 次")

    # 第二段 承题
    t = C.section(sec, 2)
    if t:
        s(rep, "承题-引用四元组", "P1", bool(C.find_citations(t)), "须含四元组引用")
        s(rep, "承题-歧义≥2", "P1", t.count("歧义") >= 2, f"“歧义”出现 {t.count('歧义')} 次")
        s(rep, "承题-例外≥2", "P1", t.count("例外") >= 2, f"“例外”出现 {t.count('例外')} 次")
        boundary = [k for k in ("法域", "层级", "不含") if k in t]
        s(rep, "承题-边界四要素", "P1",
          has_any(t, ["法域"]) and has_any(t, ["时点", "效力", "生效"]) and ("层级" in t) and ("不含" in t),
          f"检测到：{boundary}")

    # 第三段 起讲
    t = C.section(sec, 3)
    if t:
        has_s = bool(re.search(r"S\d+", t))
        s(rep, "起讲-S标陈述方", "P1", (not has_s) or ("陈述方" in t) or ("方" in t),
          "含 S 类须标注陈述方")
        has_u = bool(re.search(r"U\d+", t))
        s(rep, "起讲-U写所需证据", "P1", (not has_u) or ("证据" in t),
          "含 U 类须写明转为已证所需证据")
        s(rep, "起讲-无评价", "P1",
          not has_any(t, ["应当承担", "构成违约", "据此认定"]),
          "本段只分层，不应出现法律评价性表述")

    # 第四段 入手
    t = C.section(sec, 4)
    if t:
        a = C.a_ids(t)
        s(rep, "入手-要件编号", "P1", bool(a), f"识别到要件 {len(a)} 项")
        s(rep, "入手-举证方", "P1", "举证" in t, "须为要件标注举证方")
        s(rep, "入手-缺失后果", "P1", has_any(t, ["后果", "不成立"]), "须写明缺失后果")

    # 第五段 起股
    t = C.section(sec, 5)
    if t:
        a4 = C.a_ids(C.section(sec, 4))
        a5 = C.a_state_ids(t)
        s(rep, "起股-判定数=要件数", "P0", (bool(a4) and a4 == a5),
          f"第四段={sorted(a4)} 第五段判定={sorted(a5)}")
        s(rep, "起股-三要素", "P1", has_any(t, ["事实依据"]) and has_any(t, ["规范依据", "依据"]),
          "每判定宜含事实依据+规范依据+推理说明")

    # 第六段 中股
    t = C.section(sec, 6)
    if t:
        five = ["权利障碍", "权利消灭", "权利阻止", "证据抗辩", "程序抗辩"]
        miss = [x for x in five if x not in t]
        s(rep, "中股-五类齐", "P1", not miss, ("缺：" + "、".join(miss)) if miss else "五类齐")
        s(rep, "中股-漏洞≥2", "P1", len(re.findall(r"V\d+", t)) >= 2 or t.count("漏洞") >= 2,
          "须列正向论证漏洞清单 ≥2 条")

    # 第七段 后股
    t = C.section(sec, 7)
    if t:
        rules = ("①" in t) or ("命中" in t)
        s(rep, "后股-写明命中规则", "P1", rules, "须写明命中的优先级规则编号")
        s(rep, "后股-举证责任", "P1", has_any(t, ["举证完成", "完成举证", "举证方"]),
          "每个冲突点须回答“谁举证、是否完成”")

    # 第八段 束股
    t = C.section(sec, 8)
    if t:
        s(rep, "束股-三清单", "P0",
          ("存疑" in text) and ("适用边界" in text) and ("排除" in text),
          "存疑/边界/排除三清单须齐")
        s(rep, "束股-边界≥4", "P1",
          sum(k in t for k in ("法域", "时点", "不适用", "裁量")) >= 3,
          "适用边界宜含 法域/时点/不适用/裁量空间")
        s(rep, "束股-补强≥2", "P1",
          len(re.findall(r"S\d+", t)) >= 2 or t.count("建议") >= 2,
          "补强建议须 ≥2 条")
        s(rep, "束股-尾部三提示", "P1",
          ("不构成法律意见" in t) and ("核验" in t) and ("复核" in t),
          "固定尾部三提示须齐")

    # 门0 弱校验：有大量待查明/存疑，却无澄清记录或假设声明 → 提示可能跳过了门0
    doubt = len(re.findall(r"待查明|待证|存疑|尚待|未查明|待核实", text))
    has_intake = any(k in text for k in ("澄清", "假设声明", "门0", "用户回答", "门1", "门2"))
    if doubt >= 3 and not has_intake:
        s(rep, "澄清已登记", "P1", False,
          f"检测到 {doubt} 处待查明/存疑，但未见澄清记录或假设声明（门0 可能被跳过）")
    else:
        s(rep, "澄清已登记", "P1", True,
          "已登记澄清/假设声明" if has_intake else "待查明项较少，可免")

    raise SystemExit(rep.emit())


if __name__ == "__main__":
    main()
