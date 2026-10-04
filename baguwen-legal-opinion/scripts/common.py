# -*- coding: utf-8 -*-
"""八股体法律意见书 · 校验脚本共用工具。

解析约定见 references/redlines.md 第七节「推理轨的机器可读约定」。
所有脚本为启发式校验：用于拦截结构性问题，不替代人工判断。
"""
import json
import re
import sys


if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


STATE_SYMBOLS = "✓◐✗?"
BAGU_NAMES = ["破题", "承题", "起讲", "入手", "起股", "中股", "后股", "束股"]

# 硬性绝对化表述（命中计 P0）
ABSOLUTE_HARD = re.compile(r"显然|毫无疑问|毋庸置疑|必然|必定")
# 软性绝对化表述（命中计 P1）
ABSOLUTE_SOFT = re.compile(r"肯定|绝对肯定|百分之百|盖章定论")

PLACEHOLDERS = {"", "____", "待填", "...", "…", "xxx", "XXX", "XX"}
PENDING = {"待核验", "未核验", "未检索到", "需人工核实", "待核实", "未核实"}

# 引用四元组：[条文号][原文片段][来源标识][效力核验时间]
BRACKET_RE = re.compile(r"\[([^\[\]\n]*)\]\[([^\[\]\n]*)\]\[([^\[\]\n]*)\]\[([^\[\]\n]*)\]")


def load_text(path=None):
    """从文件或标准输入读取文本（UTF-8）。"""
    if path and path != "-":
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    data = sys.stdin.buffer.read()
    return data.decode("utf-8", errors="replace")


_CN2D = {"一": "1", "二": "2", "三": "3", "四": "4", "五": "5",
         "六": "6", "七": "7", "八": "8", "1": "1", "2": "2", "3": "3",
         "4": "4", "5": "5", "6": "6", "7": "7", "8": "8"}
_SEG_HEADER = re.compile(r"(?m)^[#\s>、]*(第\s*[一二三四五六七八1-8]\s*[段股])")


def split_sections(text):
    """按段切分推理轨文本，返回 {段号: 文本}。
    优先用「行首 第N段/股」显式段头（避免第零段或正文误含八股名导致错切）；
    命中不足 2 个时回退为按八股名首次出现切分。"""
    headers = {}
    for m in _SEG_HEADER.finditer(text):
        num = _CN2D.get(re.search(r"[一二三四五六七八1-8]", m.group(1)).group(0))
        if num and num not in headers:
            headers[num] = m.start()
    if len(headers) >= 2:
        order = sorted(headers.items(), key=lambda kv: kv[1])
        sections = {}
        for j, (num, pos) in enumerate(order):
            end = order[j + 1][1] if j + 1 < len(order) else len(text)
            sections[num] = text[pos:end]
        return sections
    # 回退：按八股名首次出现
    positions = []
    for i, name in enumerate(BAGU_NAMES):
        idx = text.find(name)
        if idx != -1:
            positions.append((idx, str(i + 1)))
    positions.sort()
    sections = {}
    for j, (idx, num) in enumerate(positions):
        end = positions[j + 1][0] if j + 1 < len(positions) else len(text)
        sections[num] = text[idx:end]
    return sections


def section(sections, num):
    return sections.get(str(num), "")


def find_citations(text):
    """返回引用列表 [{form, fields, raw}]。"""
    cites = []
    for m in BRACKET_RE.finditer(text):
        cites.append({"form": "bracket", "fields": list(m.groups()), "raw": m.group(0)})
    for raw in text.splitlines():
        if ("条文号" in raw) and ("来源" in raw) and ("核验时间" in raw):
            cites.append({"form": "labeled", "fields": [], "raw": raw.strip()})
    return cites


def a_ids(text):
    """提取要件编号集合 { '1','2',... }。"""
    return set(re.findall(r"A(\d+)", text))


def state_lines(text):
    """返回含要件编号且含四态符号的行（保留兼容）。"""
    out = []
    for line in text.splitlines():
        if re.search(r"A\d+", line) and any(sym in line for sym in STATE_SYMBOLS):
            out.append(line)
    return out


def a_state_ids(text):
    """返回带四态判定的要件编号集合 { '1','2',... }。
    以"A<编号>"切块，只要该块内出现四态符号即计入——
    兼容"编号与判定分行"与"编号与判定同行"两种写法。"""
    ids = set()
    for block in re.split(r"(?=A\d+)", text):
        m = re.match(r"A(\d+)", block)
        if not m:
            continue
        if any(sym in block for sym in STATE_SYMBOLS):
            ids.add(m.group(1))
    return ids


def count_pattern(text, pattern):
    return len(re.findall(pattern, text))


class Report:
    def __init__(self, name):
        self.name = name
        self.items = []

    def add(self, check_id, level, ok, detail=""):
        self.items.append({
            "id": check_id,
            "level": level,          # P0 / P1 / P2
            "ok": bool(ok),
            "detail": detail,
        })

    def p0(self):
        return [i for i in self.items if i["level"] == "P0" and not i["ok"]]

    def p1(self):
        return [i for i in self.items if i["level"] == "P1" and not i["ok"]]

    def p2(self):
        return [i for i in self.items if i["level"] == "P2" and not i["ok"]]

    def emit(self):
        summary = {
            "report": self.name,
            "pass": len(self.p0()) == 0,
            "P0_failed": len(self.p0()),
            "P1_failed": len(self.p1()),
            "P2_failed": len(self.p2()),
            "results": self.items,
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if len(self.p0()) == 0 else 1


def read_arg():
    """第一个命令行参数作为输入文件；无则读 stdin。"""
    return sys.argv[1] if len(sys.argv) > 1 else None
