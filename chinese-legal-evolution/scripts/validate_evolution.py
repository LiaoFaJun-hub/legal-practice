#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
中国法律沿革比较 · 报告校验器（计算层）

设计三原则（与 validator-harness 技能一致）：
  1. 零依赖：只用 Python 标准库；
  2. 校验对象是**报告**，不是法条——法条真伪需原书核验，超出计算层能力；
  3. 裸跑可用：stdin -> stdout JSON，不依赖退出码表达业务结论。

用法：
  python validate_evolution.py < case.json        # 校验
  python validate_evolution.py --selftest         # 自检（含反例与覆盖断言）
  python validate_evolution.py --dump-rules        # 导出规则 JSON

2026-10-04 编写时已吸收上一轮三路独立审计的全部教训：
  · 匹配层归一化（繁简·异体·插空格·标点）——否则「干 名 犯 義」可绕过
  · 覆盖断言带下限 + 每条检查函数须被执行过——否则删掉断言仍能静默通过
  · 用户传入参数不得放宽制度上限
  · 畸形输入不得崩溃
"""

import sys
import json
import os
import re
import unicodedata

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")
except Exception:
    pass


# ============================================================================
# 一、规则数据（唯一权威来源）
# ============================================================================

# 十个朝代节点——报告必须逐一交代，无材料者标"无法判断"，不得跳过
DYNASTY_NODES = ["秦", "汉", "隋", "唐", "宋", "元", "明", "清", "民国", "现行"]

# 可判断度四档（见 references/02_存佚与可判断度.md）
COMPARABILITY_LEVELS = ["甲", "乙", "丙", "丁"]

# 差异五态 + 两态例外
DIFF_STATES = ["首次", "沿用", "修改", "增补", "废止", "并存", "无法判断", "不适用"]

# 跨断点后的合法差异态（1949 年后法统断裂，"废止"等五态不适用）
POST_BREAK_DYNASTIES = ["民国", "现行"]

# ---- 归一化层：匹配前统一形态，否则拆字/异体/繁简可绕过 -------------------
_T2S = {
    "謹": "谨", "狀": "状", "辭": "辞", "書": "书", "訴": "诉", "詞": "词", "訟": "讼",
    "訊": "讯", "縣": "县", "鄉": "乡", "號": "号", "歲": "岁", "產": "产", "業": "业",
    "鬥": "斗", "毆": "殴", "繼": "继", "戶": "户", "調": "调", "審": "审", "證": "证",
    "據": "据", "總": "总", "為": "为", "無": "无", "與": "与", "從": "从", "語": "语",
    "舊": "旧", "親": "亲", "執": "执", "筆": "笔", "釋": "释", "敗": "败", "結": "结",
    "續": "续", "驗": "验", "傷": "伤", "單": "单", "辯": "辩", "須": "须", "責": "责",
    "鋪": "铺", "識": "识", "攝": "摄", "闕": "阙", "詣": "诣", "聞": "闻", "錄": "录",
    "傳": "传", "議": "议", "減": "减", "誣": "诬", "請": "请", "衛": "卫", "禮": "礼",
    "劃": "划", "廳": "厅", "慶": "庆", "廢": "废", "斷": "断", "應": "应", "該": "该",
    "條": "条", "規": "规", "嚴": "严", "體": "体", "錯": "错", "險": "险", "離": "离",
    "義": "义", "會": "会", "經": "经", "歷": "历", "斷": "断", "隸": "隶", "贓": "赃",
    "贖": "赎", "黥": "黥", "梟": "枭", "論": "论", "賞": "赏", "囚": "囚", "繫": "系",
    "舉": "举", "權": "权", "禮": "礼", "殺": "杀", "傷": "伤", "盜": "盗", "贖": "赎",
    "簡": "简", "憲": "宪", "規": "规", "制": "制", "設": "设", "廳": "厅", "長": "长",
    # 常见异体/OCR 混淆字：乾、幹 在旧刻与 OCR 文本中常代「干」出现
    "乾": "干", "幹": "干", "幹": "干",
}
_DROP = set(" \t\r\n　，。、；：？！“”‘’（）《》〈〉【】〔〕「」『』…—·‧,.;:!?\"'()[]{}<>/\\|-_=+*&^%$#@~`")

# 繁简映射只覆盖规则词条涉及的字——**不声称覆盖全字表**（边界照实说明）


def normalize(s):
    """归一化：NFKC → 繁转简 → 去标点空白。用于术语与句式匹配，不用于字数统计。"""
    if not s:
        return ""
    t = unicodedata.normalize("NFKC", str(s))
    t = "".join(_T2S.get(ch, ch) for ch in t)
    t = "".join(ch for ch in t if ch not in _DROP)
    return t


def scan(blob, term):
    """术语匹配：先归一化再子串匹配。"""
    nb, nt = normalize(blob), normalize(term)
    if not nb or not nt:
        return False
    return nt in nb


# ---- 跨代术语黑名单（另建，不照搬文书体式黑名单）-------------------------
TERM_BLACKLIST = [
    ("干名犯义",   ("明", "清"),              "明代律条名，唐宋及以前无此名"),
    ("律例",       ("清",),                  "律与例并称系清代制度"),
    ("六法体系",   ("民国",),                "民国法制结构"),
    ("亲亲相隐",   ("唐", "宋", "元", "明", "清"), "唐律疏议确立的律名，秦汉无"),
    ("诬告陷害",   ("现行",),                "现行刑法罪名体系"),
    ("民法典",     ("现行",),                "现行法典名"),
    ("刑法",       ("民国", "现行"),          "现行法典名"),
    ("秋审",       ("清",),                  "清代制度"),
    ("朝审",       ("清",),                  "清代制度"),
    ("折杖法",     ("清",),                  "清代制度"),
    ("服制",       ("明", "清"),             "明清有服制图"),
]

# ---- 「无材料」≠「无规定」的三种表述禁令 -----------------------------------
# 出现"某朝无此规定"时，必须同时出现以下降级标记之一
NO_RULE_PATTERNS = ["无此规定", "没有此规定", "未有此规定", "并无此规定", "不规定此", "无此条"]
DOWNGRADE_MARKERS = ["无法判断", "未能核验", "未见依据", "未见废止依据", "未能核验",
                     "该批材料未见", "不可外推", "未见相应记载", "材料不存", "存佚"]

# 丙档（仅史志转述）朝代：不得下"有/无此规定"的强断言
PROHIBITED_DYNASTY = ["隋"]

# ---- 判「废止」的四类正面依据（穷举，用尽即止）----------------------------
CESSATION_BASIS = ["修律诏", "修律敕", "废改诏", "纂修", "凡例", "沿革说明", "沿革",
                   "判例", "官修目录", "法律目录", "目录著录", "毋庸再用", "停止适用"]

# 「废止」的否定式——**审计首轮发现**：「不作废止论」「未见废止依据」这类正确表述
# 若被当作废止断言，会使本检查在每一份诚实报告上误报。故须先排除否定式。
CESSATION_NEGATIONS = ["不作废止论", "不作废止", "不认定废止", "不称废止", "不得判为废止",
                       "不能判为废止", "非废止", "未废止", "未见废止", "无法判断废止",
                       "不宜判为废止", "慎称废止"]
# 否定式分两级窗口——自检发现「而非废止」「不写废止」因否定词不紧邻而漏判，
# 若一味放宽窗口又会让「已废止，未见其他规定」这类真断言漏网。故分两级。
CESSATION_PREFIX_NEG = CESSATION_NEGATIONS + [
    "而非废止", "并非废止", "不写废止", "不判为废止", "不废止", "不会废止", "难以废止",
    "不是废止", "非为废止", "未出现废止", "没有出现废止", "未写入废止", "未判定废止",
]
CESSATION_WIDE_HEDGE = [
    "无法判断", "未能判断", "未及核验", "未及判断", "待核", "存疑",
    "是否", "有无", "能否", "未见依据", "无依据", "没有依据",
    "被正面依据证明", "未见废止依据", "不作为废止论", "不得作废止论",
]

# ---- 不确定性标记（出现即须有清单）----------------------------------------
UNCERTAINTY_MARKERS = ["无法判断", "待核", "未见依据", "未能核验", "存疑", "拟补", "待补"]


def _is_int_like(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _positive_cessation(blob):
    """统计**正面**的「废止」断言数；否定式与对冲式不计入。
    两级窗口：紧邻前缀查否定词（8字），较宽窗口查对冲词（±24字）。
    Why 不用单一窗口：自检发现「而非废止」「不写废止」因否定词不紧邻而漏判；
    而一味放宽窗口又会让「已废止，未见其他规定」这类真断言漏网。"""
    nb = normalize(blob)
    cnt, idx = 0, 0
    term = "废止"
    while True:
        j = nb.find(term, idx)
        if j < 0:
            break
        prefix = nb[max(0, j - 8): j]
        wide = nb[max(0, j - 24): j + 24]
        # 注意：前缀窗口要**连同"废止"二字一起**扫描——否则「而非废止」这类
        # 本身含"废止"的否定式永远匹配不上（自检实测漏判）。
        if not (any(scan(prefix + term, n) for n in CESSATION_PREFIX_NEG)
                or any(scan(wide, h) for h in CESSATION_WIDE_HEDGE)):
            cnt += 1
        idx = j + len(term)
    return cnt


def _iter_lines(md):
    return [ln.strip() for ln in str(md or "").splitlines() if ln.strip()]


# ---- 显示宽度：画框线必须用它，不能用 len() -------------------------------
# 依据 11_线框图规范.md：中文在等宽字体下占 2 个显示宽度。
# `len("秦·丁")` = 4，但实际占 5~6 格——按字符数画框线必然错位。
# 这条是通用陷阱，已同步沉淀进 ~/.workbuddy/skills/validator-harness/
def disp_width(s):
    """显示宽度：East Asian Width 为 W/F（全角）的字符计 2，其余计 1。"""
    w = 0
    for ch in str(s or ""):
        w += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return w


# ---- 图解析：抽取节点/关系/不确定标记/图说 --------------------------------
NODE_RE = re.compile(r"\[([^\[\]]{1,80}?)\]")
REL_RE = re.compile(r"[─-╿]{2,}\s*[（(]([^（）()]{1,40})[)）]\s*[─-╿]{2,}\s*[▶>→]")
MARK_RE = re.compile(r"\[\?\]")
GLOSS_RE = re.compile(r"图说\s*[：:](.*)", re.S)

# T2 Mermaid：ID["标签"] 与 A -->|"关系词"| B
# 依据 11_线框图规范.md 第三节。标签必须带双引号，否则 [?] 会破坏 Mermaid 语法——
# 故本正则只认带引号形式，无引号标签属不合规，由 Mermaid 渲染失败自然暴露。
MM_NODE_RE = re.compile(r'\w+\s*\[\s*"([^"]{1,80}?)"\s*\]')
MM_REL_RE = re.compile(r'(\w+)\s*-->\s*\|"([^"]{1,40})"\|\s*(\w+)')
MM_REL_RE2 = re.compile(r'(\w+)\s*--\s*"([^"]{1,40})"\s*-->\s*(\w+)')
MM_UNLINKED_RE = re.compile(r'^\s*(\w+)\s*\[\s*"([^"]{1,80}?)"\s*\]', re.M)

# 并列连接词：出现 **两个以上** 才判为多概念（单个可能是"趋势与清单"这类正常表述）
CONJ = ["且", "以及", "并且", "、", "；", "和", "同时"]

NODE_WIDTH_LIMIT = 16       # 显示宽度上限（见 11_线框图规范.md 第四节，三档通用）

# 载体档位上限（见 11_线框图规范.md 第二节）
CARRIER_LIMITS = {"ascii": 12, "mermaid": 24, "svg": 10 ** 6}
CARRIER_ALIASES = {"ascii": "ascii", "text": "ascii", "plain": "ascii", "box": "ascii",
                   "mermaid": "mermaid", "mmd": "mermaid",
                   "svg": "svg", "inline_svg": "svg"}

# 断点标记：不是概念节点，是分隔标记，故豁免宽度上限；但**必须孤立**。
# Why 单列豁免：断点标签天然要写"1949 制度更替·法统断裂"才说得清，
# 按 16 显示宽度一刀切拦下它，等于逼作者把断点缩成"1949"而丢掉语义。
BREAK_LABELS = ["1949", "断点", "法统断裂", "制度更替"]

# 输入/输出边界标记：图例要求的"标出输入输出边界"，它们是**边界标记**而非概念节点。
# 与断点同理豁免概念宽度，但**另设更宽的独立上限**（24）——
# Why 不能顺手放进 BREAK_LABELS 那样无条件豁免：那会变成万能后门，
# 任何超长文本只要改个前缀就能绕过「节点单概念」这条纪律。
IO_PREFIX = ("输入", "输出")
IO_WIDTH_LIMIT = 24


def _is_break_label(s):
    t = str(s or "")
    return any(k in t for k in BREAK_LABELS)


def _is_io_label(s):
    return str(s or "").startswith(IO_PREFIX)


def _parse_mermaid(src):
    """解析 Mermaid 图。返回与 T1 同构的抽取结果，字段口径完全一致——
    **换载体不换判据**：四项图示校验对三档一视同仁。"""
    nodes = [m.group(1) for m in MM_NODE_RE.finditer(src)]
    rels = [m.group(2) for m in MM_REL_RE.finditer(src)]
    rels += [m.group(2) for m in MM_REL_RE2.finditer(src)]
    marks = len(MARK_RE.findall(src))
    return nodes, rels, marks


def parse_diagram(case):
    d = case.get("diagram")
    carrier = "ascii"
    src = ""
    gloss = ""
    baseline = ""
    note = ""
    if isinstance(d, str):
        src = d
    elif isinstance(d, dict):
        c = str(d.get("carrier") or "").strip().lower()
        carrier = CARRIER_ALIASES.get(c, c or "ascii")
        src = str(d.get("source") or d.get("code") or "")
        gloss = str(d.get("gloss") or "")
        baseline = str(d.get("baseline") or "")
        note = str(d.get("note") or "")
        # SVG 本体无法机检节点/关系，故以 baseline（Mermaid）为校验对象
        if carrier == "svg" and baseline:
            src = baseline
        if gloss and not GLOSS_RE.search(src or ""):
            src = (src or "") + "\n图说：" + gloss
    if not src:
        # 回退：从报告全文里抓 fenced code block
        for m in re.finditer(r"```[a-zA-Z]*\n(.*?)```", str(case.get("report_markdown") or ""), re.S):
            src += m.group(1) + "\n"
    if carrier == "mermaid" or re.search(r"^\s*(graph|flowchart)\s+\w", src or "", re.M):
        nodes, rels, marks = _parse_mermaid(src)
    else:
        nodes = [m.group(1) for m in NODE_RE.finditer(src)]
        rels = [m.group(1) for m in REL_RE.finditer(src)]
        marks = len(MARK_RE.findall(src))
    g = GLOSS_RE.search(src)
    gloss = g.group(1).strip() if g else ""
    return {"raw": src, "nodes": nodes, "rels": rels, "marks": marks, "gloss": gloss,
            "carrier": carrier, "baseline": baseline, "note": note}


# ============================================================================
# 四、七至十项校验（图示合规）
# ============================================================================

def check_node_single_concept(case, out, skipped):
    """7. 节点单概念——每节点只保留一个核心概念，且装得下。"""
    dg = parse_diagram(case)
    if not dg["raw"].strip():
        skipped.append({"code": "NODE_SINGLE_CONCEPT", "reason": "未提供 diagram，结论 unknown"})
        return
    if not dg["nodes"]:
        out["blocking"].append({"code": "NODE_SINGLE_CONCEPT",
                                "detail": "图里没有解析到任何 [节点]",
                                "source": "11_线框图规范.md 第三节"})
        return
    for n in dg["nodes"]:
        if _is_break_label(n):
            continue          # 断点是分隔标记，不是概念节点，豁免宽度（见规范第五节）
        w = disp_width(n)
        limit = IO_WIDTH_LIMIT if _is_io_label(n) else NODE_WIDTH_LIMIT
        if w > limit:
            out["blocking"].append({
                "code": "NODE_TOO_WIDE",
                "detail": "节点「%s」显示宽度 %d，超出上限 %d（中文占 2 格，按字符数算必错位）"
                          % (n[:16], w, limit),
                "source": "11_线框图规范.md 第四节；disp_width()",
                "suggest": "拆成两个节点；节点是概念不是容器，不要塞条文原文",
            })
        hits = [c for c in CONJ if c in n]
        if len(hits) >= 2:
            out["blocking"].append({
                "code": "NODE_MULTI_CONCEPT",
                "detail": "节点「%s」含多个并列成分（%s），违反「每节点只保留一个核心概念」"
                          % (n[:16], "、".join(hits)),
                "source": "SKILL.md Gotchas 15；11_线框图规范.md 第六节",
                "suggest": "拆节点，或删掉次要概念",
            })


def check_relation_not_invented(case, out, skipped):
    """8. 关系不得自补——箭头上的每个关系词都须在报告中有出处。"""
    dg = parse_diagram(case)
    if not dg["raw"].strip():
        skipped.append({"code": "RELATION_NOT_INVENTED", "reason": "未提供 diagram，结论 unknown"})
        return
    if not dg["rels"]:
        out["blocking"].append({"code": "RELATION_UNLABELED",
                                "detail": "图中有箭头但没有关系词注记（无法核验）",
                                "source": "11_线框图规范.md 第五节"})
        return
    body = normalize(case.get("report_markdown") or "")
    for n in (case.get("nodes") or []):
        if isinstance(n, dict):
            body += normalize(str(n.get("diff_basis") or ""))
            body += normalize(str(n.get("diff_state") or ""))
    for r in dg["rels"]:
        if not scan(body, r):
            out["blocking"].append({
                "code": "RELATION_NOT_INVENTED",
                "detail": "箭头关系词「%s」在报告正文与差异依据中均无出处——属自行补关系" % r,
                "source": "工作区红线：视觉类头号红线＝为美观补内容、补关系",
                "suggest": "改为报告中确有依据的关系，或删除该箭头",
            })


def check_uncertainty_marked(case, out, skipped):
    """9. 不确定处必须单独标注——图中的 [?] 须与报告的不确定性对应。"""
    dg = parse_diagram(case)
    if not dg["raw"].strip():
        skipped.append({"code": "UNCERTAINTY_MARKED", "reason": "未提供 diagram，结论 unknown"})
        return
    md = normalize(case.get("report_markdown") or "")
    has_unc = any(scan(md, m) for m in UNCERTAINTY_MARKERS)
    if has_unc and dg["marks"] == 0:
        out["blocking"].append({
            "code": "UNCERTAINTY_UNMARKED",
            "detail": "报告存在不确定项，但图中未标任何 [?]",
            "source": "SKILL.md 铁律 13；11_线框图规范.md 第五节",
            "suggest": "材料不足的节点一律加 [?]（如丙档朝代、材料未见、未核验节点）",
        })
    elif dg["marks"] > 0 and not any(scan(dg["gloss"], w) for w in ["不确定", "存疑", "待核", "无法判断", "未核验"]):
        out["warnings"].append({
            "code": "UNCERTAINTY_GLOSS_SILENT",
            "detail": "图中标了 [?] 但图说未提及不确定在哪——读者会忽略标记",
            "source": "11_线框图规范.md 第六节",
        })


def check_diagram_gloss(case, out, skipped):
    """10. 图说必须恰好三句。"""
    dg = parse_diagram(case)
    if not dg["raw"].strip():
        skipped.append({"code": "DIAGRAM_GLOSS", "reason": "未提供 diagram，结论 unknown"})
        return
    if not dg["gloss"]:
        out["blocking"].append({"code": "GLOSS_MISSING",
                                "detail": "图说缺失（须以「图说：」开头）",
                                "source": "11_线框图规范.md 第三节"})
        return
    n = sum(dg["gloss"].count(c) for c in "。！？")
    if n != 3:
        out["blocking"].append({
            "code": "GLOSS_NOT_THREE",
            "detail": "图说为 %d 句，须恰好三句（画什么关系／主流程与断点／哪里不确定）" % n,
            "source": "11_线框图规范.md 第七节；SKILL.md Gotchas 16",
            "suggest": "三句各有一职，不是把一句话拆成三句",
        })
    check_carrier(case, out, skipped, dg)
    check_break_isolated(case, out, skipped, dg)


def check_break_isolated(case, out, skipped, dg=None):
    """12. 断点必须孤立——1949 前后不得连成一条线。

    Why 这条以前只写在规范里、没有机检：自检用例的框线图把断点画成
    `└──── 1949 ────┘` 这种**汇合线**，看上去是"断链"，实则把清与民国
    连在了一起——正是「跨断点连线＝宣称法统承继」这条历史伪造。
    **一条从不失败的检查等于没有检查**——本条由自检首次实跑抓出。"""
    dg = dg or parse_diagram(case)
    if not dg["raw"].strip():
        skipped.append({"code": "BREAK_ISOLATED", "reason": "未提供 diagram，结论 unknown"})
        return
    raw = dg["raw"]
    carrier = dg["carrier"]

    # 断点节点是否出现在任何一条边上
    brk_nodes = set()
    if carrier == "mermaid":
        for m in MM_NODE_RE.finditer(raw):
            if _is_break_label(m.group(1)):
                brk_nodes.add(m.group(0).split("[")[0].strip())
        linked = set()
        for rx in (MM_REL_RE, MM_REL_RE2):
            for m in rx.finditer(raw):
                linked.add(m.group(1))
                linked.add(m.group(3))
        hit = brk_nodes & linked
        if hit:
            out["blocking"].append({
                "code": "BREAK_NOT_ISOLATED",
                "detail": "Mermaid 断点节点 %s 被连进了关系边——跨 1949 连线等于宣称法统承继，"
                          "是历史伪造" % "、".join(sorted(hit)),
                "source": "11_线框图规范.md 第五节；SKILL.md 铁律 8",
                "suggest": "断点须为孤立节点（只声明不连线）；前后两段各自成图或用 subgraph 视觉分隔",
            })
        return

    # 框线图：断点若与框线网格（─│└┘├┤┬┴┼）或箭头同处一行，即为连线。
    # 正确画法是**独立成行的 ════ 断链标记**，上下不接任何竖线。
    CONNECT_CHARS = "─│└┘├┤┬┴┼→▶"
    for ln in raw.splitlines():
        if not _is_break_label(ln):
            continue
        if any(ch in ln for ch in CONNECT_CHARS):
            out["blocking"].append({
                "code": "BREAK_NOT_ISOLATED",
                "detail": "断点行含连接线字符：%s——1949 前后不得连成一条线"
                          % ln.strip()[:40],
                "source": "11_线框图规范.md 第五节；SKILL.md 铁律 8",
                "suggest": "断点单独成行且只含 ════ 标记，上下不接竖线；清与民国分作两段",
            })


def check_carrier(case, out, skipped, dg=None):
    """11. 载体申报一致性——密度决定载体；SVG 必须附机检基准；降级须注明。

    Why 单列一项而不并入密度检查：前四项图示校验都锚定在 diagram 源码上，
    若 SVG 不附基准，四项校验会在 SVG 上**静默全部失效**（解析不到节点→各项 skipped→不报）。
    「扫描面之外＝没检查」——所以缺基准必须阻断，不能只预警。"""
    dg = dg or parse_diagram(case)
    if not dg["raw"].strip():
        skipped.append({"code": "CARRIER", "reason": "未提供 diagram，结论 unknown"})
        return
    carrier = dg["carrier"]
    if carrier not in CARRIER_LIMITS:
        out["warnings"].append({
            "code": "CARRIER_UNKNOWN",
            "detail": "载体「%s」不在受支持档位（ascii / mermaid / svg），已按 ascii 判据校验" % carrier,
            "source": "11_线框图规范.md 第二节",
        })
        carrier = "ascii"
    n = len(dg["nodes"])
    limit = CARRIER_LIMITS[carrier]

    if carrier == "svg" and not dg["baseline"].strip():
        out["blocking"].append({
            "code": "SVG_NO_BASELINE",
            "detail": "SVG 图未附等价 Mermaid 基准（diagram.baseline）——节点/关系/不确定标注"
                      "三项校验在 SVG 上将全部失效且无告警",
            "source": "11_线框图规范.md 第二节纪律1；validator-harness 技法九（扫描面之外＝没检查）",
            "suggest": "补 diagram.baseline（Mermaid 源码，标签与关系词须与 SVG 逐字一致）",
        })

    if n > limit:
        out["blocking"].append({
            "code": "CARRIER_TOO_DENSE",
            "detail": "载体 %s 下有 %d 个节点，超出该档上限 %d——密度超限必然错乱，"
                      "降级是义务不是选项" % (carrier, n, limit),
            "source": "11_线框图规范.md 第二节降级阶梯",
            "suggest": "降到 Mermaid（≤24），或拆成两张图后分 carrier 声明",
        })
    elif carrier != "ascii" and not dg["note"].strip():
        out["warnings"].append({
            "code": "CARRIER_NOTE_MISSING",
            "detail": "已降级为 %s 载体但未注明——读者会误以为这是本技能的原生画法，"
                      "误判密度上限不存在" % carrier,
            "source": "11_线框图规范.md 第二节纪律3",
            "suggest": '补 diagram.note，如「载体：Mermaid（节点 16，超框线图上限 12）」',
        })


# ============================================================================

# 注：CHECKS 汇总表在各校验函数定义之后（见"六、主流程"节）。此处不重复定义，
# 避免出现"函数未定义即被引用"的初始化顺序错误。
# ============================================================================
# 二、工具
# ============================================================================

def dig(obj, path):
    """按 'a.b.c' 取值；缺失返回 None。支持字段别名与空串视为缺失。"""
    aliases = {"source": ("law_source",), "text": ("article_text",),
               "evidence_level": ("level",), "diff_state": ("difference",),
               "markdown_row": ("row",), "comparability": ("level_cmp",)}
    cur = obj
    for seg in path.split("."):
        if isinstance(cur, dict) and seg in cur and cur[seg] not in (None, ""):
            cur = cur[seg]
            continue
        hit = None
        for a in aliases.get(seg, ()):
            if isinstance(cur, dict) and a in cur and cur[a] not in (None, ""):
                hit = cur[a]
                break
        if hit is None:
            return None
        cur = hit
    return cur


# ============================================================================
# 三、六项校验
# ============================================================================

def check_node_coverage(case, out, skipped):
    """1. 朝代覆盖连续性——十个节点逐一交代，不得跳过。"""
    nodes = case.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        skipped.append({"code": "NODE_COVERAGE", "reason": "未提供 nodes 列表（分母为 0），结论 unknown"})
        out["warnings"].append({
            "code": "EMPTY_DENOMINATOR",
            "detail": "未提供任何朝代节点，覆盖检查分母为 0，结论 unknown 而非通过",
        })
        return
    got = set()
    for n in nodes:
        d = (n or {}).get("dynasty")
        if d:
            got.add(str(d).strip())
    missing = [d for d in DYNASTY_NODES if d not in got]
    extra = [d for d in got if d not in DYNASTY_NODES]
    if missing:
        out["blocking"].append({
            "code": "NODE_MISSING",
            "detail": "以下朝代节点未在报告中交代（缺一即不可接受）：%s"
                      % "、".join(missing),
            "source": "SKILL.md S2 存佚判档；02_存佚与可判断度.md 第五节",
            "suggest": "对每个缺失节点：给出法源与可判断度；无材料者须标丙档并写「无法判断」",
        })
    if extra:
        out["warnings"].append({
            "code": "NODE_UNKNOWN",
            "detail": "出现十节点之外的朝代：%s（若为确需增补，须在【一】声明并说明理由）"
                      % "、".join(sorted(extra)),
        })
    if not missing and not extra:
        out["level_tags"] = ["十节点覆盖完整"]


def check_evidence_level(case, out, skipped):
    """2. 引注证据层级完整性 + 用户参数不得放宽制度门槛。"""
    nodes = [n for n in (case.get("nodes") or []) if isinstance(n, dict)]
    if not nodes:
        skipped.append({"code": "EVIDENCE_LEVEL", "reason": "未提供 nodes，结论 unknown"})
        return
    opts = case.get("options") or {}
    # 制度门槛固定为 B；用户传入的门槛不得低于 C 之外——即 C/D 不得作阻断性结论
    user_min = str(opts.get("evidence_min_level", "B") or "B").strip().upper()
    if user_min in ("D", "C"):
        out["warnings"].append({
            "code": "GATE_RELAXED",
            "detail": "传入的证据门槛为 %s，但制度红线规定：C 级（辑佚）仅可支撑制度叙述，"
                      "D 级（技艺文本）不可作法源。已按制度门槛执行。" % user_min,
            "source": "00_法源底座索引.md 第四节",
        })
        user_min = "B"
    no_level = [i for i, n in enumerate(nodes) if not str(n.get("evidence_level", "")).strip()]
    if no_level:
        out["blocking"].append({
            "code": "EVIDENCE_LEVEL_MISSING",
            "detail": "第 %s 条节点缺证据层级标注（A/B/C/D）"
                      % "、".join(str(i + 1) for i in no_level),
            "source": "SKILL.md 铁律 7；01_归一schema.md 第一节",
            "suggest": "每条引注必须带 A/B/C/D；缺级即不得进入比较表",
        })
    for n in nodes:
        lv = str(n.get("evidence_level", "")).strip().upper()
        if lv and lv in ("C", "D") and user_min == "B":
            out["warnings"].append({
                "code": "WEAK_EVIDENCE",
                "detail": "《%s》%s（%s）证据层级为 %s，不得作阻断性结论，仅可作制度叙述"
                          % (str(n.get("source", ""))[:16], str(n.get("locator", ""))[:14],
                             str(n.get("dynasty", "")), lv),
                "source": "00_法源底座索引.md 第四节",
            })
        if lv and lv not in ("A", "B", "C", "D"):
            out["blocking"].append({
                "code": "EVIDENCE_LEVEL_INVALID",
                "detail": "证据层级取值非法：%r（须为 A/B/C/D）" % lv,
                "source": "01_归一schema.md 第一节",
            })
        if not str(n.get("diff_state", "")).strip():
            out["blocking"].append({
                "code": "DIFF_STATE_MISSING",
                "detail": "《%s》缺差异态标注（%s之一）"
                          % (str(n.get("source", ""))[:16], "/".join(DIFF_STATES)),
                "source": "SKILL.md S4；03_差异判定规则.md 第一节",
            })
        elif str(n["diff_state"]).strip() not in DIFF_STATES:
            out["blocking"].append({
                "code": "DIFF_STATE_INVALID",
                "detail": "差异态取值非法：%r（须为 %s之一）" % (n["diff_state"], "/".join(DIFF_STATES)),
                "source": "03_差异判定规则.md 第一节",
            })


def check_uncertainty(case, out, skipped):
    """3. 不确定性标注存在性——出现不确定标记时须有清单，且清单不得为空占位。"""
    md = case.get("report_markdown") or ""
    if not md:
        skipped.append({"code": "UNCERTAINTY", "reason": "未提供 report_markdown，结论 unknown"})
        return
    hits = [m for m in UNCERTAINTY_MARKERS if scan(md, m)]
    unc = case.get("uncertainties")
    unc_list = unc if isinstance(unc, list) else []
    if not unc_list:
        if hits:
            out["blocking"].append({
                "code": "UNCERTAINTY_MISSING",
                "detail": "报告正文出现不确定标记（%s），但未提供不确定性清单"
                          % "、".join(hits[:4]),
                "source": "SKILL.md 五、输出【五】；05_转折点与社会动因.md 第三节",
                "suggest": "每一处不确定（无法判断/待核/未见依据）都须进清单",
            })
        elif not scan(md, "本次未发现不确定项"):
            out["blocking"].append({
                "code": "UNCERTAINTY_EMPTY_PLACEHOLDER",
                "detail": "既无不确定标记，也未声明「本次未发现不确定项」及其核验范围",
                "source": "SKILL.md S6；Gotchas 12",
                "suggest": "若确实无不确定项，须写明核验范围——不是「没有不确定性」，"
                            "而是「核验范围仅 X，Y 未及核验」",
            })
        else:
            out["warnings"].append({
                "code": "UNCERTAINTY_SELF_DECLARED",
                "detail": "报告声明「本次未发现不确定项」——须确认该声明附带核验范围",
            })
        return
    for i, u in enumerate(unc_list, 1):
        if isinstance(u, str):
            continue
        if not str((u or {}).get("item", "")).strip():
            out["blocking"].append({
                "code": "UNCERTAINTY_ITEM_EMPTY",
                "detail": "第 %d 条不确定项为空" % i,
                "source": "SKILL.md 五、输出【五】",
            })


def check_term_anachronism(case, out, skipped):
    """4. 跨代术语倒推——后世规范用语不得出现在早期朝代节点。"""
    nodes = [n for n in (case.get("nodes") or []) if isinstance(n, dict)]
    if not nodes:
        skipped.append({"code": "TERM_ANACHRONISM", "reason": "未提供 nodes，结论 unknown"})
        return
    for n in nodes:
        dyn = str(n.get("dynasty", "")).strip()
        if dyn in POST_BREAK_DYNASTIES:
            continue
        row = str(n.get("markdown_row") or n.get("text") or "")
        for term, allow, note in TERM_BLACKLIST:
            if scan(row, term) and dyn not in allow:
                out["blocking"].append({
                    "code": "TERM_ANACHRONISM",
                    "detail": "「%s」属 %s 朝用语，不得出现在%s代条目：%s"
                              % (term, "／".join(allow), dyn or "（未标朝代）", note),
                    "source": "01_归一schema.md 第五节",
                    "suggest": "删除该词，或改用该朝实际用语；若该朝确有同义规定，另行引注",
                })


def check_survival_cap(case, out, skipped):
    """5. 存佚封顶——「无材料」≠「无规定」；丙档不得下强断言。"""
    md = case.get("report_markdown") or ""
    nodes = [n for n in (case.get("nodes") or []) if isinstance(n, dict)]
    if not md and not nodes:
        skipped.append({"code": "SURVIVAL_CAP", "reason": "无 report_markdown 与 nodes，结论 unknown"})
        out["warnings"].append({"code": "EMPTY_DENOMINATOR",
                                "detail": "存佚封顶检查分母为 0，结论 unknown 而非通过"})
        return
    # 5a 句式禁令：逐行判定「无此规定」是否同句带降级标记
    # 窗口取**本行 + 下一行**（而非全篇 ±120 字）——窗口过宽会让别处的降级标记
    # 为此处的裸断言背书，检查就咬不住了。
    lines = _iter_lines(md)
    for i, line in enumerate(lines):
        if not any(scan(line, pat) for pat in NO_RULE_PATTERNS):
            continue
        window = line + (" " + lines[i + 1] if i + 1 < len(lines) else "")
        if not any(scan(window, mk) for mk in DOWNGRADE_MARKERS):
            out["blocking"].append({
                "code": "NO_MATERIAL_NOT_NO_RULE",
                "detail": "报告出现「%s」但同句无任何降级标记（无法判断/存佚/不可外推等）：%s"
                          % (next(p for p in NO_RULE_PATTERNS if scan(line, p)), line[:60]),
                "source": "SKILL.md Gotchas 1；02_存佚与可判断度.md 第三节",
                "suggest": "材料不存时唯一正确表述是「无法判断」；判「无此规定」须有正面依据",
            })
    # 5b 丙档封顶：仅史志转述的朝代不得下「有／无此规定」强断言
    for n in nodes:
        cmp_level = str(n.get("comparability", "")).strip()
        dyn = str(n.get("dynasty", "")).strip()
        row = normalize(n.get("markdown_row") or n.get("text") or "")
        if cmp_level not in ("丙",) and dyn not in PROHIBITED_DYNASTY:
            continue
        has_downgrade = any(scan(row, mk) for mk in DOWNGRADE_MARKERS)
        if not has_downgrade:
            out["blocking"].append({
                "code": "SURVIVAL_CAP_EXCEEDED",
                "detail": "%s朝（判档%s·仅程序级）条目未出现任何降级标记——律文残缺不存时，"
                          "结论只能是「无法判断」" % (dyn or "（未标朝代）", cmp_level or "丙"),
                "source": "SKILL.md S2；02_存佚与可判断度.md 第二、三节",
                "suggest": "改写为「××朝律文已佚，无法判断」；禁止写「××朝无此规定」",
            })


def check_cessation_basis(case, out, skipped):
    """6. 判「废止」须有正面依据；史料沉默不等于已废止。"""
    md = case.get("report_markdown") or ""
    nodes = [n for n in (case.get("nodes") or []) if isinstance(n, dict)]
    blob = md + "\n" + "\n".join(
        "%s %s %s %s" % (n.get("dynasty", ""), n.get("diff_state", ""),
                         n.get("diff_basis", ""), n.get("markdown_row", ""))
        for n in nodes)
    if not blob.strip():
        skipped.append({"code": "CESSATION", "reason": "无内容可比对，结论 unknown"})
        return
    if _positive_cessation(blob) <= 0:
        return
    # 出现正面「废止」断言时，全文须有四类正面依据之一
    if not any(scan(blob, b) for b in CESSATION_BASIS):
        out["blocking"].append({
            "code": "CESSATION_NO_BASIS",
            "detail": "报告出现「废止」判断，但全文未见任何正面依据"
                      "（修律诏令／律例沿革说明／判例 cessation／官修目录著录）",
            "source": "SKILL.md 铁律 4；03_差异判定规则.md 第二节",
            "suggest": "史料沉默不等于已废止。无法定依据者一律改写为「未见废止依据」",
        })
    # 逐节点：凡差异态为"废止"者，该节点自身须有依据
    for n in nodes:
        if str(n.get("diff_state", "")).strip() != "废止":
            continue
        basis = str(n.get("diff_basis", ""))
        if not any(scan(basis, b) for b in CESSATION_BASIS):
            out["blocking"].append({
                "code": "CESSATION_NODE_NO_BASIS",
                "detail": "%s朝节点判为「废止」但 diff_basis 未给出正面依据：%r"
                          % (str(n.get("dynasty", "（未标）")), basis[:40]),
                "source": "03_差异判定规则.md 第二节",
                "suggest": "补正面依据；无则改为「无法判断」或「未见废止依据」",
            })


# ============================================================================
# 六、主流程
# ============================================================================

CHECKS = [
    ("node_coverage",   check_node_coverage),
    ("evidence_level",  check_evidence_level),
    ("uncertainty",     check_uncertainty),
    ("term_anachronism", check_term_anachronism),
    ("survival_cap",    check_survival_cap),
    ("cessation",       check_cessation_basis),
    ("node_concept",    check_node_single_concept),
    ("relation_origin", check_relation_not_invented),
    ("diagram_uncert",  check_uncertainty_marked),
    ("diagram_gloss",   check_diagram_gloss),
    ("carrier",         check_carrier),
    ("break_isolated",  check_break_isolated),
]


def validate(case):
    out = {"verdict": "PASS", "checks_run": [],
           "blocking": [], "warnings": [], "assertions_skipped": [], "level_tags": []}
    if not isinstance(case, dict):
        out["verdict"] = "ERROR"
        out["blocking"].append({"code": "BAD_INPUT",
                                "detail": "输入不是 JSON 对象：%s" % type(case).__name__})
        return out
    skipped = out["assertions_skipped"]
    for name, fn in CHECKS:
        try:
            fn(case, out, skipped)
            out["checks_run"].append(name)
        except Exception as e:                      # 审计器自身出错必须显式暴露
            out["warnings"].append({"code": "CHECKER_ERROR",
                                    "detail": "检查项 %s 自身抛错：%s: %s" % (name, type(e).__name__, e)})
    out["verdict"] = "BLOCK" if out["blocking"] else ("WARN" if out["warnings"] else "PASS")
    return out


# ============================================================================
# 五、自检（反例 + 覆盖断言 + 下限）
# ============================================================================

# 一份完整合规的报告（正例底本）
GOOD_NODES = [
    {"dynasty": "秦", "comparability": "丁", "source": "睡虎地秦简·法律答问", "locator": "简号",
     "text": "子告父母，臣妾告主，非公室告，勿听。", "norm_target": "身份禁告", "penalty": "勿听",
     "evidence_level": "A", "diff_state": "首次", "diff_basis": "该批简牍未见此前规定",
     "markdown_row": "秦｜出土简牍｜《法律答问》｜非公室告勿听｜A｜首次"},
    {"dynasty": "汉", "comparability": "丁", "source": "张家山汉简·二年律令", "locator": "告律简126",
     "text": "子告父母，妇告威公，奴婢告主、主父母妻子，勿听而弃告者市。", "norm_target": "身份禁告",
     "penalty": "弃告者市", "evidence_level": "A", "diff_state": "修改",
     "diff_basis": "汉简增列妇告威公、奴婢告主，且罚则改为弃告者市", "markdown_row": "汉｜告律简126｜弃告者市｜A｜修改"},
    {"dynasty": "隋", "comparability": "丙", "source": "《隋书》卷25·刑法志", "locator": "篇目",
     "text": "有枉屈县不理者，令以次经郡及州。", "norm_target": "程序", "penalty": "",
     "evidence_level": "B", "diff_state": "无法判断",
     "diff_basis": "《开皇律》全佚，无法判断隋代身份禁告的规定", "markdown_row": "隋｜律文已佚，无法判断｜B"},
    {"dynasty": "唐", "comparability": "甲", "source": "《唐律疏议》", "locator": "卷24·斗讼·第345条",
     "text": "诸告祖父母、父母者，绞。", "norm_target": "身份禁告", "penalty": "绞",
     "evidence_level": "A", "diff_state": "修改",
     "diff_basis": "由程序性不受转为实体性绞刑", "markdown_row": "唐｜卷24斗讼345条｜告祖父母父母者绞｜A｜修改"},
    {"dynasty": "宋", "comparability": "甲", "source": "《宋刑统》", "locator": "卷24·斗讼",
     "text": "诸告祖父母、父母者，绞。", "norm_target": "身份禁告", "penalty": "绞",
     "evidence_level": "A", "diff_state": "沿用",
     "diff_basis": "宋刑统承唐律原文，文字全同（全沿）", "markdown_row": "宋｜卷24斗讼｜绞｜A｜沿用"},
    {"dynasty": "元", "comparability": "乙", "source": "《元典章》", "locator": "卷53·刑部",
     "text": "〔该门未见身份禁告相应规定〕", "norm_target": "身份禁告", "penalty": "",
     "evidence_level": "B", "diff_state": "无法判断",
     "diff_basis": "元代无统一律典，《元典章》该门未见相应规定，不作废止论", "markdown_row": "元｜元典章卷53｜该门未见相应记载，不可外推｜B"},
    {"dynasty": "明", "comparability": "甲", "source": "《大明律》", "locator": "刑律·人命·干名犯义",
     "text": "凡告祖父母父母及夫若谒而告者，绞。", "norm_target": "身份禁告", "penalty": "绞",
     "evidence_level": "A", "diff_state": "沿用",
     "diff_basis": "明律承唐制并立干名犯义条，文字全同（全沿）", "markdown_row": "明｜干名犯义｜绞｜A｜沿用"},
    {"dynasty": "清", "comparability": "甲", "source": "《大清律例》", "locator": "卷30·刑律·诉讼·第337条",
     "text": "凡告祖父母父母及夫若谒而告者，绞。", "norm_target": "身份禁告", "penalty": "绞",
     "evidence_level": "A", "diff_state": "沿用",
     "diff_basis": "清律承明律，文字全同（全沿）", "markdown_row": "清｜卷30第337条｜绞｜A｜沿用"},
    {"dynasty": "民国", "comparability": "待核", "source": "民国《民法·亲属编》", "locator": "条文",
     "text": "〔本次未能核验原文〕", "norm_target": "亲属关系", "penalty": "",
     "evidence_level": "B", "diff_state": "不适用",
     "diff_basis": "属1949年后法统，无承继关系", "markdown_row": "民国｜不适用差异五态｜未能核验原文｜B"},
    {"dynasty": "现行", "comparability": "待核", "source": "《中华人民共和国民法典》", "locator": "第×条",
     "text": "〔本次未能核验时效性〕", "norm_target": "亲属关系", "penalty": "",
     "evidence_level": "A", "diff_state": "不适用",
     "diff_basis": "属1949年后法统，无承继关系", "markdown_row": "现行｜不适用差异五态｜未能核验时效性｜A"},
]

GOOD_MD = (
    "【一】比较范围与判断标准\n"
    "【二】时间轴比较表\n"
    "秦｜《法律答问》｜非公室告勿听｜A｜首次\n"
    "汉｜告律简126｜弃告者市｜A｜修改\n"
    "隋｜律文已佚，无法判断｜B｜无法判断\n"
    "唐｜卷24斗讼345条｜告祖父母父母者绞｜A｜修改\n"
    "宋｜卷24斗讼｜绞｜A｜沿用\n"
    "元｜元典章卷53｜该门未见相应记载，不可外推｜B｜无法判断\n"
    "明｜干名犯义｜绞｜A｜沿用\n"
    "清｜卷30第337条｜绞｜A｜沿用\n"
    "民国｜不适用差异五态｜未能核验原文｜B\n"
    "现行｜不适用差异五态｜未能核验时效性｜A\n"
    "【三】趋势与转折点\n"
    "【四】明文规定 vs 实际执行 vs 学理解释\n"
    "【五】不确定性清单\n"
    "【六】总结\n"
)

# 一份合规的图：节点单概念、宽度达标、关系词在报告中有出处、不确定处带 [?]、图说恰好三句
GOOD_DIAGRAM = """[输入：案情]
        │
   [判档]  │  [判差异]
        │
 秦·丁 ──(首次)──→ 汉·丁 ──(修改)──→ 隋·丙 [?]
        │                   │
   [证据层级]          [无法判断]
        │                   │
 唐·甲 ──(沿用)──→ 宋·甲   明·甲 ──(修改)──→ 清·甲

                        ════ 1949 制度更替·法统断裂 ════

                       民国·待核 [?] ──(不适用)──→ 现行·待核
                                 │
                            [输出：趋势]"""

GOOD_GLOSS = ("这张图画的是同一个法律问题在十个朝代之间的规范关系。"
              "主线是秦汉排除、唐宋入罪、明清缓和三条段，1949 年断开为两段。"
              "标问号的三处是不确定处：材料不足，不是制度空白。")

# T2 Mermaid 等价图：14 个节点（超框线图上限 12），用于验证载体降级。
# 关系词全部取自 GOOD_MD 与 GOOD_NODES，故 RELATION_NOT_INVENTED 不应触发。
GOOD_MERMAID = """graph TD
  Q["输入：案情＋比较范围"] --> J1["存佚判档"]
  Q --> J2["差异态判定"]
  J1 --> A1["秦·丁"]
  A1 -->|"修改"| A2["汉·丁"]
  A2 --> A3["隋·丙 [?]"]
  J1 --> A4["证据层级"]
  J2 --> B1["唐·甲"]
  B1 -->|"沿用"| B2["宋·甲"]
  J2 --> B3["元·乙 [?]"]
  B3 -->|"无法判断"| B2
  J2 --> C1["明·甲"]
  C1 -->|"修改"| C2["清·甲"]
  BRK["════ 1949 制度更替·法统断裂 ════"]
  J2 --> D1["民国·待核 [?]"]
  D1 -->|"不适用"| D2["现行·待核"]
  J1 --> OUT["输出：趋势＋清单"]
  J2 --> OUT
  BRK
图说：""" + GOOD_GLOSS

# 16 节点的框线图——超 ascii 档上限 12，须降级
DENSE_ASCII = "".join("[朝代节点%02d] ──(修改)──→ " % i for i in range(1, 16)) + "[末节点]\n图说：" + GOOD_GLOSS


def _case(nodes=None, md=None, unc=None, opts=None, diagram=None):
    import copy
    dg = {"source": GOOD_DIAGRAM, "gloss": GOOD_GLOSS} if diagram is None else diagram
    return {
        "problem": "亲属相告（告尊长）的法律地位",
        "nodes": copy.deepcopy(nodes if nodes is not None else GOOD_NODES),
        "report_markdown": md if md is not None else GOOD_MD,
        "uncertainties": unc if unc is not None else [{"item": "隋代身份禁告规定无法判断"},
                                                      {"item": "元代该门未见相应规定"}],
        "diagram": dg,
        "options": opts or {},
    }


def _drop_node(nodes, dyn):
    return [n for n in nodes if n["dynasty"] != dyn]



SELFTEST_CASES = [
    ("正例·完整合规报告", _case(), "PASS"),
    ("反例·漏掉隋代节点（覆盖连续性）",
     _case(nodes=_drop_node(GOOD_NODES, "隋"), md=GOOD_MD.replace("隋｜律文已佚，无法判断｜B｜无法判断\n", "")),
     "BLOCK"),
    ("反例·缺证据层级标注",
     _case(nodes=[dict(n, evidence_level="") if n["dynasty"] == "唐" else n for n in GOOD_NODES]),
     "BLOCK"),
    ("反例·差异态取值非法",
     _case(nodes=[dict(n, diff_state="大概沿用") if n["dynasty"] == "宋" else n for n in GOOD_NODES]),
     "BLOCK"),
    ("反例·差异态完全缺失",
     _case(nodes=[dict(n, diff_state="") if n["dynasty"] == "唐" else n for n in GOOD_NODES]),
     "BLOCK"),
    ("反例·有不确定标记但无清单",
     _case(unc=[]), "BLOCK"),
    ("反例·清单为空占位（既无标记也无声明）",
     _case(nodes=_drop_node(GOOD_NODES, "隋"), md="【一】范围\n【二】比较表\n", unc=[]), "BLOCK"),
    ("反例·「无此规定」无降级标记（静默材料沉默当制度空白）",
     _case(md=GOOD_MD + "综上，唐代以前无此规定。"), "BLOCK"),
    ("反例·拆字绕过：'干 名 犯 义' 出现在唐节点",
     _case(nodes=[dict(n, markdown_row="唐｜干 名 犯 义｜绞｜A｜修改")
                  if n["dynasty"] == "唐" else n for n in GOOD_NODES]), "BLOCK"),
    ("反例·繁体'乾名犯義'出现在唐节点（异体绕过）",
     _case(nodes=[dict(n, markdown_row="唐｜乾名犯義｜绞｜A｜修改")
                  if n["dynasty"] == "唐" else n for n in GOOD_NODES]), "BLOCK"),
    ("反例·丙档隋代下强断言（存佚封顶被突破）",
     _case(nodes=[dict(n, markdown_row="隋｜不设身份禁告｜B｜首次",
                      diff_basis="未见", text="不设")
                  if n["dynasty"] == "隋" else n for n in GOOD_NODES],
           md=GOOD_MD.replace("隋｜律文已佚，无法判断｜B｜无法判断", "隋｜不设身份禁告｜B｜首次")),
     "BLOCK"),
    ("反例·判废止但无正面依据",
     _case(nodes=[dict(n, diff_state="废止", diff_basis="后世律中查不到",
                      markdown_row="清｜绞｜A｜废止")
                  if n["dynasty"] == "清" else n for n in GOOD_NODES],
           md=GOOD_MD + "该条至清代已废止。"), "BLOCK"),
    ("反例·判废止但依据只在正文（节点自身无依据）",
     _case(nodes=[dict(n, diff_state="废止", diff_basis="查不到")
                  if n["dynasty"] == "清" else n for n in GOOD_NODES],
           md=GOOD_MD + "据修律诏，该条已废止。"), "BLOCK"),
    ("正例·判废止且有正面依据（修律诏）",
     _case(nodes=[dict(n, diff_state="废止",
                      diff_basis="据某年修律诏，该条废止",
                      markdown_row="清｜绞｜A｜废止")
                  if n["dynasty"] == "清" else n for n in GOOD_NODES],
           md=GOOD_MD + "据某年修律诏，该条已废止。"), "PASS"),
    ("反例·用户传证据门槛 D（试图放宽制度红线）",
     _case(opts={"evidence_min_level": "D"}), "WARN"),
    ("反例·畸形输入：nodes 传字符串（不得崩溃）",
     _case(nodes="不是列表"), "WARN"),
    ("反例·空输入（分母为 0 须记 unknown 而非通过）",
     {"problem": "x"}, "WARN"),

    # ===== 以下 10 例针对 2026-10-04 新增的四项图示校验 =====
    ("反例·节点超宽（按显示宽度不按字符数）",
     _case(diagram={"source": "[输入：案情＋比较范围＋十朝代节点]\n[秦·丁] ──(首次)──→ [汉·丁]\n图说：" + GOOD_GLOSS,
                    "gloss": ""}), "BLOCK"),
    ("反例·节点塞多个概念（含两个不同并列连接词）",
     _case(diagram={"source": "[唐宋明清 判档且存疑 并且缺证]\n[甲] ──(首次)──→ [乙]\n图说：" + GOOD_GLOSS,
                    "gloss": ""}), "BLOCK"),
    ("反例·箭头无关系词注记（无法核验）",
     _case(diagram={"source": "[秦·丁] ──→ [汉·丁]\n图说：" + GOOD_GLOSS, "gloss": ""}), "BLOCK"),
    ("反例·自行补关系（关系词在报告中无出处）",
     _case(diagram={"source": "[秦·丁] ──(判例互相印证)──→ [汉·丁]\n图说：" + GOOD_GLOSS,
                    "gloss": ""}), "BLOCK"),
    ("反例·有不确定项但图中未标 [?]",
     _case(diagram={"source": "[秦·丁] ──(首次)──→ [汉·丁]\n[唐·甲] ──(沿用)──→ [宋·甲]\n图说：" + GOOD_GLOSS,
                    "gloss": ""}), "BLOCK"),
    ("反例·图说只有两句",
     _case(diagram={"source": GOOD_DIAGRAM,
                    "gloss": "这张图画的是同一法律问题在十朝之间的规范关系。1949 年断开为两段。"}), "BLOCK"),
    ("反例·图说四句（凑数）",
     _case(diagram={"source": GOOD_DIAGRAM,
                    "gloss": GOOD_GLOSS + "另外元代材料不足。"}), "BLOCK"),
    ("反例·图说缺失",
     _case(diagram={"source": GOOD_DIAGRAM, "gloss": ""}), "BLOCK"),
    ("反例·拆字绕过宽度上限（节点超宽但字符数不超）",
     _case(diagram={"source": "[秦 汉 隋 唐 宋 元 明 清 民 国 现 行 全部十一个节点塞进一个框]\n"
                               "[甲] ──(首次)──→ [乙]\n图说：" + GOOD_GLOSS, "gloss": ""}), "BLOCK"),
    ("正例·图说提到不确定且节点标注齐全",
     _case(), "PASS"),

    # ===== 以下 6 例针对载体分档（2026-10-04 v1.2.0）=====
    ("正例·Mermaid 载体（14 节点超框线上限，须带 note）",
     _case(diagram={"carrier": "mermaid", "source": GOOD_MERMAID,
                    "gloss": "", "note": "载体：Mermaid（节点 14，超框线图上限 12）"}), "PASS"),
    ("反例·Mermaid 降级但未注明（读者会误判密度上限不存在）",
     _case(diagram={"carrier": "mermaid", "source": GOOD_MERMAID, "gloss": ""}), "WARN"),
    ("反例·SVG 未附 Mermaid 基准（三项校验会静默失效）",
     _case(diagram={"carrier": "svg", "source": "<svg><text>秦·丁</text></svg>",
                    "baseline": "", "gloss": "", "note": "载体：SVG"}), "BLOCK"),
    ("正例·SVG 附等价 Mermaid 基准",
     _case(diagram={"carrier": "svg", "source": "<svg><text>秦·丁</text></svg>",
                    "baseline": GOOD_MERMAID, "gloss": "",
                    "note": "载体：SVG（节点 14，另附 Mermaid 基准）"}), "PASS"),
    ("反例·框线图 16 节点超上限（降级是义务不是选项）",
     _case(diagram={"source": DENSE_ASCII, "gloss": ""}), "BLOCK"),
    ("反例·Mermaid 关系词在报告无出处（换载体不换判据）",
     _case(diagram={"carrier": "mermaid",
                    "source": GOOD_MERMAID.replace('|"沿用"|', '|"判例互相印证"|'),
                    "gloss": "", "note": "载体：Mermaid（节点 14）"}), "BLOCK"),
    ("反例·框线图断点被连成一条线（法统承继的历史伪造）",
     _case(diagram={"source": GOOD_DIAGRAM.replace(
         "                        ════ 1949 制度更替·法统断裂 ════",
         "        └──── 1949 制度更替·法统断裂 ────┘"),
         "gloss": ""}), "BLOCK"),
    ("反例·Mermaid 断点被连进关系边",
     _case(diagram={"carrier": "mermaid",
                    "source": GOOD_MERMAID.replace(
                        'BRK["════ 1949 制度更替·法统断裂 ════"]',
                        'BRK["════ 1949 制度更替 ════"]\n  BRK -->|"沿用"| C2'),
                    "gloss": "", "note": "载体：Mermaid（节点 14）"}), "BLOCK"),
    ("反例·借「输入」前缀绕过节点宽度（豁免不得成为后门）",
     _case(diagram={"source": "[输入：秦汉隋唐宋元明清民国现行全部十一个朝代的规范状态逐一铺开]"
                               "\n[甲] ──(首次)──→ [乙]\n图说：" + GOOD_GLOSS,
                    "gloss": ""}), "BLOCK"),
]


def selftest():
    print("[SELFTEST-BEGIN] 中国法律沿革比较 · 校验器自检 · 共 %d 例" % len(SELFTEST_CASES))
    fails = []
    for i, (name, case, expect) in enumerate(SELFTEST_CASES, 1):
        try:
            r = validate(case)
            got = r["verdict"]
        except Exception as e:
            got, r = "ERROR:%s" % e, {"blocking": [], "warnings": []}
        ok = (got == expect)
        print("%s #%02d 期望=%-5s 实得=%-5s  %s" % ("[OK]" if ok else "[FAIL]", i, expect, got, name))
        if not ok:
            fails.append((i, name, expect, got))
        for b in r["blocking"]:
            print("        └─ BLOCK %s：%s" % (b.get("code"), b.get("detail")))
        for w in r["warnings"]:
            print("        └─ WARN  %s：%s" % (w.get("code"), w.get("detail")))

    # 覆盖断言 1：每个检查码至少被反例激活过一次
    MUST_FAIL = {"NODE_MISSING", "EVIDENCE_LEVEL_MISSING", "DIFF_STATE_MISSING",
                 "DIFF_STATE_INVALID", "UNCERTAINTY_MISSING", "UNCERTAINTY_EMPTY_PLACEHOLDER",
                 "TERM_ANACHRONISM", "NO_MATERIAL_NOT_NO_RULE", "SURVIVAL_CAP_EXCEEDED",
                 "CESSATION_NO_BASIS", "CESSATION_NODE_NO_BASIS",
                 "NODE_TOO_WIDE", "NODE_MULTI_CONCEPT", "RELATION_UNLABELED",
                 "RELATION_NOT_INVENTED", "UNCERTAINTY_UNMARKED",
                 "GLOSS_MISSING", "GLOSS_NOT_THREE",
                 "CARRIER_TOO_DENSE", "SVG_NO_BASELINE", "BREAK_NOT_ISOLATED"}
    MIN_MUST_FAIL = 20
    if len(MUST_FAIL) < MIN_MUST_FAIL:
        print("[SELFTEST-FAIL] 覆盖集被削弱：仅 %d 项，低于下限 %d 项" % (len(MUST_FAIL), MIN_MUST_FAIL))
        fails.append(("coverage-size", "MUST_FAIL", ">=%d" % MIN_MUST_FAIL, str(len(MUST_FAIL))))

    seen, ran = set(), set()
    for name, case, expect in SELFTEST_CASES:
        r = validate(case)
        ran |= set(r["checks_run"])
        for b in r["blocking"] + r["warnings"]:
            seen.add(b.get("code"))
    dead = sorted(MUST_FAIL - seen)
    if dead:
        print("[SELFTEST-FAIL] 以下检查码从未被反例激活，构成'从不失败的检查'：%s" % "、".join(dead))
        fails.append(("coverage", " ".join(dead), "激活过", "未激活"))

    # 覆盖断言 2：每条检查函数都必须至少执行过一次（防"检查被摘掉"）
    MUST_RUN = {n for n, _ in CHECKS}
    notrun = sorted(MUST_RUN - ran)
    if notrun:
        print("[SELFTEST-FAIL] 以下检查函数在全部用例中从未被执行：%s" % "、".join(notrun))
        fails.append(("execution", " ".join(notrun), "执行过", "未执行"))

    print("[SELFTEST-SUMMARY] 通过 %d / %d" % (len(SELFTEST_CASES) - len(fails), len(SELFTEST_CASES)))
    if fails:
        print("[SELFTEST-FAIL] 共 %d 项不合格" % len(fails))
        return 1
    print("[SELFTEST-OK] 全部通过，且每条检查均已被反例激活")
    return 0


def dump_rules():
    return {
        "dynasty_nodes": DYNASTY_NODES,
        "comparability_levels": COMPARABILITY_LEVELS,
        "diff_states": DIFF_STATES,
        "post_break_dynasties": POST_BREAK_DYNASTIES,
        "term_blacklist": [{"term": t, "allow": list(a), "note": n} for t, a, n in TERM_BLACKLIST],
        "no_rule_patterns": NO_RULE_PATTERNS,
        "downgrade_markers": DOWNGRADE_MARKERS,
        "prohibited_dynasty": PROHIBITED_DYNASTY,
        "cessation_basis": CESSATION_BASIS,
        "uncertainty_markers": UNCERTAINTY_MARKERS,
        "checks": [n for n, _ in CHECKS],
    }


def main(argv):
    if "--selftest" in argv:
        return selftest()
    if "--dump-rules" in argv:
        print(json.dumps(dump_rules(), ensure_ascii=False, indent=2))
        return 0
    raw = sys.stdin.read()
    if not raw.strip():
        print(json.dumps({"verdict": "ERROR", "detail": "stdin 为空"}, ensure_ascii=False, indent=2))
        return 2
    try:
        case = json.loads(raw)
    except json.JSONDecodeError as e:
        print(json.dumps({"verdict": "ERROR", "detail": "输入非合法 JSON：%s" % e},
                         ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(validate(case), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
