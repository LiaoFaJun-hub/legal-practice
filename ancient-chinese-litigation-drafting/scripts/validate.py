#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
古代讼师文书 · 计算层校验器（十段式 SKILL 的"计算层"）

设计三原则（对齐 SKILL 规格）：
  1. 零依赖：只使用 Python 标准库（无 pip 包）；
  2. 单向来源：本文件内的规则数据是**唯一权威**，assets/禁用词表.md 由
     `--write-md` 自动生成，禁止手改，防止文档与代码漂移；
  3. 裸跑可用：stdin -> stdout JSON，不依赖外部文件、不依赖退出码语义。

用法：
  python validate.py < case.json            # 校验，输出 JSON 结论
  python validate.py --selftest             # 自检（含反例，必须跑出 fail）
  python validate.py --dump-rules           # 输出全部规则 JSON
  python validate.py --write-md <path>      # 由规则生成 assets/禁用词表.md

退出码：0=脚本自身正常执行完毕（结论见 JSON 的 verdict 字段）
        2=脚本自身异常（输入非 JSON 等）
不依赖退出码表达业务结论——业务结论一律读 JSON 的 verdict。
"""

import sys
import json
import os
import unicodedata

try:  # Windows 控制台默认 GBK，强制 UTF-8
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")
except Exception:
    pass


# ============================================================================
# 一、规则数据（唯一权威来源）
# ============================================================================

DYNASTIES = ["秦", "汉", "隋", "唐", "宋", "元", "明", "清"]
MODES = ["standard", "daobi"]          # 明清专用：官代书体 / 讼师刀笔体
EARLY = ["秦", "汉", "隋", "唐"]        # 明清用语不可倒推的早期朝代

# ---- 1.1 跨朝代禁用词黑名单 ------------------------------------------------
# 每条 = (词, 允许出现的朝代元组, 是否仅限刀笔模式, 说明, 法源/依据)
# 校验逻辑：dynasty ∉ allow → BLOCK（跨朝倒推）；daobi_only 且 mode != daobi → BLOCK
BLACKLIST = [
    # —— 明清讼学体系（朱语/珥语/十段锦）：秦至元一律阻断，明清仅刀笔模式 ——
    ("朱语",        ("明", "清"), True,  "明清讼学'破题'四字装头语，属讼师笔法", "总纲§四；spec_元明§五"),
    ("珥语",        ("明", "清"), True,  "明清讼学蔑称对方的第二层攻击语", "总纲§四；spec_清§四"),
    ("十段锦",      ("明", "清"), True,  "硃书—缘由—期由—计由—成败—得失—证由—截语—结尾—事释", "总纲§四；spec_元明§五"),
    ("硃书",        ("明", "清"), True,  "十段锦第一段，即朱语/主意", "spec_元明§五"),
    ("截语",        ("明", "清"), True,  "十段锦第八段，一状总断", "spec_元明§五"),
    ("事释",        ("明", "清"), True,  "十段锦第十段，二至四字收束", "spec_元明§五"),
    ("孽亲",        ("明", "清"), True,  "脸谱化亲缘贬称", "spec_元明§五；spec_清§四"),
    ("枭亲",        ("明", "清"), True,  "脸谱化亲缘贬称", "spec_元明§五"),
    ("兽亲",        ("明", "清"), True,  "脸谱化亲缘贬称", "spec_元明§五"),
    ("鳄亲",        ("明", "清"), True,  "脸谱化亲缘贬称", "spec_元明§五"),
    ("虎亲",        ("明", "清"), True,  "脸谱化亲缘贬称", "spec_元明§五"),
    ("鳄伯",        ("明", "清"), True,  "脸谱化尊长贬称", "spec_元明§五"),
    ("虎伯",        ("明", "清"), True,  "脸谱化尊长贬称", "spec_元明§五"),
    ("鳄豪",        ("明", "清"), True,  "脸谱化大户贬称", "总纲§四；spec_清§四"),
    ("虎豪",        ("明", "清"), True,  "脸谱化大户贬称", "spec_元明§五；spec_清§四"),
    ("枭豪",        ("明", "清"), True,  "脸谱化大户贬称", "spec_清§四"),
    ("焰豪",        ("明", "清"), True,  "脸谱化大户贬称", "spec_清§四"),
    ("势豪",        ("明", "清"), True,  "脸谱化大户贬称", "spec_清§四"),
    ("劣衿",        ("明", "清"), True,  "脸谱化生监贬称", "spec_清§四"),
    ("蚁民",        ("明", "清"), True,  "弱造语，讼师笔法自称", "spec_清§四"),

    # —— 清代特有制度（明代用"书状人吏"，唐宋元一律阻断）——
    ("官代书",      ("清",),      False, "清代考取受戳的代书，明代为'书状人吏'", "总纲§四；spec_清§三"),
    ("代书戳记",    ("清",),      False, "清代状尾准入门槛", "总纲§四；spec_清§三"),
    ("考取代书",    ("清",),      False, "雍正七年定例制度", "spec_清§三"),
    ("做状人",      ("清",),      False, "清代状首三栏之一", "总纲§四；spec_清§二"),
    ("戳记",        ("清",),      False, "清代'无代书戳记不准'", "总纲§四；spec_清§三"),
    ("如虚坐诬",    ("明", "清"), False, "明清告状状尾保证语", "spec_清§二"),
    ("沾恩无既",    ("明", "清"), False, "明清状尾收束语", "spec_清§二"),

    # —— 明清共有（秦至宋元阻断）——
    ("写状人",      ("明", "清"), False, "明清状式要件，无姓名者不准", "总纲§四；spec_元明§三"),
    ("状式条例",    ("明", "清"), False, "明清状纸后附准理清单", "总纲§四"),
    ("不准理",      ("明", "清"), False, "明清状式受理语", "总纲§四"),
    ("准理",        ("明", "清"), False, "明清状式受理语", "总纲§四"),
    ("抱告",        ("明", "清"), False, "清代必判、明代选填；唐宋无此制", "总纲§四；spec_清§三"),
    ("被告",        ("元", "明", "清"), False, "清代/明清口语化起诉用语，秦汉隋唐阻断", "总纲§四"),
    ("原告",        ("元", "明", "清"), False, "清代/明清口语化起诉用语，秦汉隋唐阻断", "总纲§四"),
    ("状告",        ("元", "明", "清"), False, "元明清起首语，秦汉隋唐阻断", "总纲§四；spec_元明§一"),
    ("具状人",      ("元", "明", "清"), False, "元明清状式用语", "总纲§四"),
    ("所结是实",    ("明", "清"), False, "明清验伤结状套语", "总纲§四；spec_清§一"),
    ("甘结",        ("元", "明", "清"), False, "元明清具结文书", "spec_元明§一；spec_清§一"),
    ("供状",        ("明", "清"), False, "明清堂审供词文书", "spec_清§一"),

    # —— 宋代特有（唐宋元明清之外阻断）——
    ("书铺",        ("宋", "元"), False, "宋设书铺准入，元代转为状铺", "总纲§四；spec_唐宋§三"),
    ("保识",        ("宋",),      False, "宋代'状无保识不受'", "总纲§四；spec_唐宋§三"),
    ("茶食人",      ("宋",),      False, "宋代保识人别称", "spec_唐宋§三"),
    ("印子",        ("宋",),      False, "宋代书铺印子", "spec_唐宋§三"),
    ("谨状",        ("宋",),      False, "宋代收束语；唐代用'谨辞'不可混", "总纲§四；spec_唐宋§四"),
    ("伏乞县司施行", ("宋",),      False, "宋代州县状标准收束语", "spec_唐宋§二"),

    # —— 唐代特有 ——
    ("谨辞",        ("唐",),      False, "唐代庶人收束语", "总纲§四；spec_唐宋§四"),
    ("谨牒",        ("唐",),      False, "唐代品官/杂任收束语", "spec_唐宋§四"),
    ("请裁",        ("唐",),      False, "唐代'请裁，谨辞'过渡语", "spec_唐宋§四"),

    # —— 元代特有 ——
    ("户计",        ("元",),      False, "元代民户/军户/驱口身份字段", "总纲§四；spec_元明§七"),
    ("驱口",        ("元",),      False, "元代奴婢户计名", "总纲§四"),
    ("状铺",        ("元",),      False, "元代官方代写机构", "spec_元明§一"),
    ("书状人吏",    ("元", "明"), False, "元代官选代书；明初《大明令》沿用", "总纲§四；spec_元明§六"),
    ("招伏",        ("元",),      False, "元代被告认罪文书", "spec_元明§一"),
    ("责状",        ("元",),      False, "元代具结兼含刑罚意", "spec_元明§一"),
    ("承管状",      ("元",),      False, "元代看管保证文书", "spec_元明§一"),
    ("词状",        ("宋", "元", "明"), False, "宋元明诉讼文书名", "spec_唐宋§一；spec_元明§一"),

    # —— 秦汉特有 ——
    ("爰书",        ("秦", "汉"), False, "秦汉官吏司法笔录；非当事人诉状", "spec_秦汉隋§模块2"),
    ("敢告",        ("秦",),      False, "秦代告辞套语", "spec_秦汉隋§模块4"),
    ("来告",        ("秦",),      False, "秦代告辞套语", "spec_秦汉隋§模块4"),
    ("谒杀",        ("秦",),      False, "秦代不孝案请杀语", "spec_秦汉隋§模块4"),
    ("毋它坐罪",    ("秦", "汉"), False, "秦汉口供结语", "spec_秦汉隋§模块4"),
    ("敢言之",      ("汉",),      False, "汉代劾文收束语", "spec_秦汉隋§模块4"),
    ("自告",        ("汉",),      False, "汉代自首，触发减刑", "spec_秦汉隋§模块2"),
    ("乞鞫",        ("秦", "汉"), False, "秦汉复审请求", "spec_秦汉隋§模块2"),
    ("传爰书",      ("汉",),      False, "汉代跨县移转文书", "spec_秦汉隋§模块2"),
    ("诉状",        ("宋", "元", "明", "清"), False, "答辩类文书；唐代及以前无此称谓", "spec_唐宋§一；spec_秦汉隋§模块4"),
    ("上诉",        ("明", "清"), False, "现代/明清口语，秦汉不得用", "spec_秦汉隋§模块4"),
    ("辩护",        ("明", "清"), False, "现代语，秦汉不得用", "spec_秦汉隋§模块4"),

    # —— 唐宋共同禁用（徽宗政和四年明令不受）——
    ("上命",        ("秦", "汉", "隋", "元", "明", "清"), False, "徽宗政和四年明令状内称'上命'者不受", "spec_唐宋§四"),
    ("与民作主",    ("秦", "汉", "隋", "元", "明", "清"), False, "同上，宋代明令不受", "spec_唐宋§四"),

    # —— 清代才出现的称谓（元明禁用；"奏闻"隋代制度原文即有"有司录状奏之"，故不禁隋）——
    ("敕批",        ("清",),      False, "清代称法，元明不得用", "spec_元明§五"),
    ("天语",        ("清",),      False, "清代称法，元明不得用", "spec_元明§五"),
    ("奏闻",        ("秦", "汉", "隋", "唐", "宋", "清"), False, "元明不得用清代'奏闻'称法；隋制原文'有司录状奏之'不禁", "spec_元明§五"),
]

# ---- 1.2 必含词白名单 ------------------------------------------------------
# 结构：朝代 -> [ {when_doc:[文书类], any:[必含其一], note, src} ]
# when_doc 为空表示不限文书类型
WHITELIST = {
    "秦": [{"when_doc": ["爰书", "告发类爰书"], "any": ["爰书"],
            "note": "秦代爰书起首'爰书：'二字不可省", "src": "spec_秦汉隋§6.5"}],
    "汉": [{"when_doc": [], "any": ["敢言之", "为报", "辞曰", "告曰"],
            "note": "汉代告/劾/辞各有收束语，不可写作后世状词口吻", "src": "spec_秦汉隋§模块4"}],
    "隋": [{"when_doc": [], "any": ["据隋制推定"],
            "note": "隋代律文全佚，首行强制标注史料缺口", "src": "总纲§六；spec_秦汉隋§6.5"}],
    "唐": [{"when_doc": [], "any": ["谨辞", "谨牒", "谨状"],
            "note": "唐代收束语；'谨状'为宋语，此处仅作存量兼容，优先'谨辞'/'谨牒'", "src": "spec_唐宋§四"}],
    "宋": [{"when_doc": [], "any": ["谨状"],
            "note": "宋代一律'伏乞县司施行，谨状'", "src": "spec_唐宋§二"}],
    "元": [{"when_doc": [], "any": ["书状人吏", "甘结", "状的实"],
            "note": "元代须署官选书状人吏姓名", "src": "spec_元明§七"}],
    "明": [{"when_doc": [], "any": ["写状人"],
            "note": "明代状式'无写状人姓名者不准'", "src": "spec_元明§三"}],
    "清": [{"when_doc": [], "any": ["代书", "戳记"],
            "note": "清代'无代书姓名不准收受'，须预留戳记占位", "src": "spec_清§三"}],
}

# ---- 1.3 各朝代必填字段 ----------------------------------------------------
REQUIRED_FIELDS = {
    "秦": ["dynasty", "parties.initiator.name", "parties.initiator.li",
           "facts.case_type", "facts.event_time", "facts.place",
           "facts.narrative", "request"],
    "汉": ["dynasty", "parties.initiator.name", "parties.initiator.li",
           "facts.case_type", "facts.event_time", "facts.place",
           "facts.narrative", "request", "parties.initiator.rank"],
    "隋": ["dynasty", "parties.initiator.name", "facts.case_type",
           "facts.event_time", "facts.place", "facts.narrative",
           "request", "procedure.procedure_history"],
    "唐": ["dynasty", "parties.initiator.name", "facts.case_type",
           "facts.event_time", "facts.place", "facts.narrative", "request"],
    "宋": ["dynasty", "parties.initiator.name", "parties.initiator.age",
           "parties.defendant.name", "parties.defendant.residence",
           "facts.case_type", "facts.event_time", "facts.place",
           "facts.narrative", "request", "procedure.via_shupu",
           "procedure.baoshi_name"],
    "元": ["dynasty", "parties.initiator.name", "parties.initiator.age",
           "facts.case_type", "facts.event_time", "facts.place",
           "facts.narrative", "request", "evidence"],
    "明": ["dynasty", "parties.initiator.name", "parties.initiator.age",
           "parties.defendant.name", "facts.case_type", "facts.event_time",
           "facts.place", "facts.narrative", "request",
           "procedure.writing_person_name"],
    "清": ["dynasty", "parties.initiator.name", "parties.initiator.age",
           "parties.initiator.gender", "parties.defendant.name",
           "facts.case_type", "facts.event_time", "facts.place",
           "facts.narrative", "request", "procedure.receiving_organ"],
}

# ---- 1.4 身份禁告矩阵（前置阻断，不通过不得生成）---------------------------
# 键 = 被告/被诉对象与告诉人的关系关键字；值 = 适用朝代与罚则
KINSHIP_BAN = [
    # (关键字列表, 适用朝代, 罚则, 法源)
    # 审计实测：原表仅收"父母"等书面语，"母亲/爹"等白话写法可绕过，故扩列同义。
    (["父母", "祖父母", "泰父母", "假大母", "母亲", "父亲", "双亲", "爹娘",
      "爹", "娘", "高堂", "父母亲"], ("秦", "汉", "唐", "宋", "明", "清"),
     "子告父母：秦'非公室告'勿听；汉'勿听而弃告者市'；唐'绞'；明清干名犯义",
     "spec_秦汉隋§模块3；spec_唐宋§三；spec_清§三"),
    (["威公", "公婆", "舅姑", "翁姑", "姑舅"], ("汉", "唐", "宋", "明", "清"),
     "妇告威公：汉'勿听而弃告者市'；唐'徒二年'", "spec_秦汉隋§模块3；spec_唐宋§三"),
    (["主人", "主家", "家主", "主母", "主父母", "东家", "主上", "家长"],
     ("秦", "汉", "唐", "宋", "明", "清"),
     "奴婢告主：秦'非公室告'勿听；汉'弃告者市'；唐'绞'（谋反逆叛除外）",
     "spec_秦汉隋§模块3；spec_唐宋§三"),
    (["期亲尊长", "外祖父母", "夫", "夫之祖父母", "尊长", "伯叔", "族长"],
     ("唐", "宋", "明", "清"),
     "告期亲尊长等：虽得实徒二年", "spec_唐宋§三"),
]

# ---- 1.5 程序闸门 ----------------------------------------------------------
PROCEDURE_GATES = {
    "隋": {"rule": "逐级申诉：县→郡→州→省，缺一级不得受理",
           "src": "spec_秦汉隋§模块3", "levels": ["county", "commandery", "prefecture", "secretariat"]},
    "宋": {"rule": "民户不经书铺不受、状无保识不受",
           "src": "spec_唐宋§三"},
    "明": {"rule": "户婚田土钱债斗殴须先经本里老人里甲理断，径告者不问虚实先杖六十",
           "src": "spec_元明§二"},
    "清": {"rule": "须自下而上陈告，越本管官司即实亦笞五十",
           "src": "spec_清§三"},
}

# 明代须先经里老理断的门类（《教民榜文》受理范围）
MING_ELDER_CATEGORIES = ["户婚", "田土", "钱债", "斗殴", "争占", "窃盗",
                         "骂詈", "赌博", "婚姻", "继立", "户役", "地土"]

# 清代须抱告的六类身份。判定用"包含"而非精确等于——审计实测 gender="女 "
# 或 "女性" 曾绕过精确匹配。
QING_BAOGAO_CLASSES = {
    "妇女": lambda p: any(k in str(p.get("gender", "")) + str(p.get("sex", ""))
                          for k in ["女", "妇", "妻", "妾", "孀", "妇道"]),
    "生监": lambda p: any(k in str(p.get("social_rank", "")) + str(p.get("rank", ""))
                          for k in ["生监", "监生", "生员", "贡生", "衿", "生童"]),
    "有职": lambda p: any(k in str(p.get("social_rank", "")) + str(p.get("rank", ""))
                          for k in ["有职", "职官", "品官", "官", "吏"]),
    "年七十以上": lambda p: _is_int_ge(p.get("age"), 70),
    "十五岁以下": lambda p: _is_int_le(p.get("age"), 15),
    "废疾": lambda p: any(k in str(p.get("social_rank", "")) + str(p.get("rank", ""))
                          for k in ["废疾", "笃疾", "残疾", "老幼", "病"]),
}

# ---- 1.6 字数限制 ----------------------------------------------------------
LENGTH_LIMIT = {
    "宋": {"default": 200, "choices": [200], "level": "地方官箴（黄震《词讼约束》、朱熹《约束榜》）",
           "src": "spec_唐宋§三"},
    "明": {"default": None, "choices": [150], "level": "地方官箴（佘自强、吕坤、《璞山蒋公政训》），非全国法",
           "src": "spec_元明§二", "note": "默认关闭，须显式加载 local_rule_set 方启用"},
    "清": {"default": 200, "choices": [150, 200, 300, 400], "level": "地方官示（《天台治略》），非全国律例",
           "src": "spec_清§三"},
}

# ---- 1.7 人数限制 ----------------------------------------------------------
PERSONS_LIMIT = {
    "明": {"defendants": 3, "witnesses": 3, "level": "地方官箴", "src": "spec_元明§七"},
    "清": {"defendants": 3, "witnesses": 2, "level": "地方状式条例（各地差异大）", "src": "spec_清§三"},
}

# ---- 1.8 证据随状（民事细故受理的实质门槛）---------------------------------
EVIDENCE_REQUIRED = {
    "婚姻": [["媒妁"], ["聘书", "婚书"]],
    "婚嫁": [["媒妁"], ["聘书", "婚书"]],
    "田土": [["契券", "契", "印串", "粮号"]],
    "地土": [["契券", "契", "印串", "粮号"]],
    "钱债": [["票约", "借约", "中证"]],
    "债负": [["票约", "借约", "中证"]],
    "人命": [["伤单", "伤", "凶器", "助单"]],
    "盗贼": [["清单", "地邻", "见证"]],
    "继立": [["宗图"]],
}

# ---- 1.9 加重罪名词（增减情罪检测）-----------------------------------------
AGGRAVATION_TERMS = ["打死人命", "谋杀", "强奸", "焚劫", "弑主", "谋财害命",
                     "锁勒死命", "杀命", "劫杀", "逼命", "灭彝", "逆天大变",
                     "强奸闺女", "斩", "枭首", "凌迟"]

# ---- 1.10 "无头圆状"等受理门槛（元代特有）---------------------------------
YUAN_GATES = {"rule": "无明确被告即'无头圆状'不予受理；私约文字未经官验不受为凭",
              "src": "spec_元明§一"}

# ---- 1.11 文书类型分组（审计发现：一刀切拦截会误伤特殊文书）----------------
# 审计实测：宋·投白纸被 NO_SHUPPU/NO_BAOSHI 误拦——但 spec_唐宋 模块三规则五明文
# 允许急切案件（贫窭老病幼小寡妇劫盗人命）投白纸、不经书铺。
# 元·甘结被 HEADLESS_ZHENG 误拦——但甘结是保证书，本不以有被告为要件。
SHUPU_EXEMPT_DOCS = ["投白纸", "白纸", "投白紙"]
NO_DEFENDANT_DOCS = ["甘结", "结状", "供状", "取状", "招伏", "和息状", "和息",
                     "遵断状", "缴结状", "领结状", "保状", "领状", "承管状",
                     "责状", "甘結", "結狀", "供狀"]


def _doc_type(case):
    return str(case.get("document_type") or "").strip()


def _has_defendant_requirement(case):
    """该文书类型是否以"有明确被告"为要件。"""
    dt = _doc_type(case)
    return not any(k in dt for k in NO_DEFENDANT_DOCS)


def _is_int_ge(v, n):
    try:
        return int(v) >= n
    except (TypeError, ValueError):
        return False


def _is_int_le(v, n):
    try:
        return int(v) <= n
    except (TypeError, ValueError):
        return False


# ============================================================================
# 二、工具函数
# ============================================================================

# Schema 字段名 ↔ 校验器字段名的别名表。
# 为什么需要：SKILL.md「四、输入」把籍贯写作 li_jurisdiction、身份写作 social_rank，
# 而校验器读 li / rank。审计实测：严格按 Schema 填输入的用户在秦/汉两朝会被
# MISSING_FIELD 硬拦。此处做**双向别名兼容**，不强制用户改 Schema。
_ALIAS_KEYS = {
    "li":              ("li_jurisdiction",),
    "li_jurisdiction": ("li",),
    "rank":            ("social_rank",),
    "social_rank":     ("rank",),
    "gender":          ("sex",),
    "residence":       ("address",),
    "witnesses":       ("ganzheng",),
}


def dig(obj, path):
    """按 'a.b.c' 取值；缺失返回 None。支持字段别名与空串视为缺失。"""
    cur = obj
    for seg in path.split("."):
        if isinstance(cur, dict) and seg in cur and cur[seg] not in (None, ""):
            cur = cur[seg]
            continue
        alt_hit = None
        for a in _ALIAS_KEYS.get(seg, ()):
            if isinstance(cur, dict) and a in cur and cur[a] not in (None, ""):
                alt_hit = cur[a]
                break
        if alt_hit is None:
            return None
        cur = alt_hit
    return cur


def cjk_len(s):
    """计中文字数：去空白后按字符计（史料的'二百字'按正文字数口径）。"""
    if not s:
        return 0
    return len("".join(str(s).split()))


# ---- 归一化层：匹配前统一形态，否则"朱 语""硃書"可绕过，繁简混写会误伤 ----
# 繁→简：只覆盖本文件规则词条实际涉及的字（边界照实说明，不声称覆盖全字表）
_T2S = {
    "謹": "谨", "狀": "状", "辭": "辞", "書": "书", "訴": "诉", "詞": "词", "訟": "讼",
    "訊": "讯", "縣": "县", "鄉": "乡", "號": "号", "歲": "岁", "產": "产", "業": "业",
    "爭": "争", "墳": "坟", "姦": "奸", "竊": "窃", "盜": "盗", "賊": "贼", "債": "债",
    "錢": "钱", "鬥": "斗", "毆": "殴", "繼": "继", "戶": "户", "調": "调", "審": "审",
    "證": "证", "據": "据", "總": "总", "為": "为", "無": "无", "與": "与", "從": "从",
    "語": "语", "舊": "旧", "親": "亲", "執": "执", "筆": "笔", "硃": "朱", "錦": "锦",
    "釋": "释", "敗": "败", "結": "结", "續": "续", "驗": "验", "傷": "伤", "單": "单",
    "擲": "掷", "聽": "听", "辯": "辩", "須": "须", "責": "责", "鋪": "铺", "識": "识",
    "攝": "摄", "闕": "阙", "詣": "诣", "聞": "闻", "錄": "录", "傳": "传", "議": "议",
    "廩": "廪", "嗇": "啬", "減": "减", "誣": "诬", "請": "请", "敘": "叙", "衛": "卫",
    "禮": "礼", "儀": "仪", "劃": "划", "廳": "厅", "廟": "庙", "慶": "庆", "寧": "宁",
    "隸": "隶", "贓": "赃", "贖": "赎", "黥": "黥", "劓": "劓", "遷": "迁", "棄": "弃",
    "誅": "诛", "梟": "枭", "論": "论", "赦": "赦", "賞": "赏", "囚": "囚", "繫": "系",
    "給": "给", "鈔": "钞", "劃": "划", "廢": "废", "廩": "廪", "覆": "覆", "舉": "举",
    "擄": "掳", "斷": "断", "應": "应", "該": "该", "條": "条", "規": "规", "嚴": "严",
    "會": "会", "體": "体", "讀": "读", "錯": "错", "風": "风", "險": "险", "離": "离",
}
# 需在匹配前剔除的标点与空白
_DROP = set(" \t\r\n　，。、；：？！“”‘’（）《》〈〉【】〔〕「」『』…—·〈〉‧･,.!?;:'\"()[]{}<>/\\|-_=+*&^%$#@~`")
# 易被拆字/插入的同形异码（部分兼容）
_ALIAS = {"跡": "迹", "跡": "迹", "凴": "凭", "凭": "凭"}


def normalize(s):
    """归一化：NFKC → 繁转简 → 去标点空白。用于术语匹配，不用于字数统计。"""
    if not s:
        return ""
    t = unicodedata.normalize("NFKC", str(s))
    t = "".join(_T2S.get(ch, ch) for ch in t)
    t = "".join(ch for ch in t if ch not in _DROP)
    return t


def scan_text(blob, term):
    """术语匹配：先归一化再子串匹配。
    为什么必须归一化——否则「朱 语」（插空格）、「硃書」（异体/繁体）都能绕过黑名单，
    而合规的繁体「謹狀」又会被白名单误判为"缺收束语"。"""
    nb, nt = normalize(blob), normalize(term)
    if not nb or not nt:
        return False
    return nt in nb


def collect_output_text(case):
    """取"生成文书"全文用于禁用词/白名单/字数扫描。
    不扫用户输入的事实经过（那是输入，不是产出）。
    健壮性：document 传字符串或畸形结构时返回空串而不抛异常——审计实测
    document="字符串" 曾使整个脚本在 try 循环外崩溃。"""
    doc = case.get("document")
    if isinstance(doc, str):
        return doc
    if not isinstance(doc, dict):
        return ""
    parts = [doc.get("title"), doc.get("body"), doc.get("closing")]
    ps = doc.get("postscript")
    if isinstance(ps, list):
        parts.extend(str(x) for x in ps)
    elif ps:
        parts.append(str(ps))
    return "\n".join(str(p) for p in parts if p)


# ============================================================================
# 三、各项校验
# ============================================================================

def check_blacklist(case, blob, dynasty, mode, out):
    for term, allow, daobi_only, note, src in BLACKLIST:
        if not scan_text(blob, term):
            continue
        if dynasty not in allow:
            out["blocking"].append({
                "code": "CROSS_DYNASTY_TERM",
                "term": term,
                "detail": "「%s」属 %s 朝用语，不得出现在%s代文书中：%s" % (
                    term, "/".join(allow), dynasty, note),
                "source": src,
                "suggest": "删除该词，改用%s代对应表述（详 references/spec_%s）" % (
                    dynasty, _spec_for(dynasty)),
            })
        elif daobi_only and mode != "daobi":
            out["blocking"].append({
                "code": "MODE_TERM_LEAK",
                "term": term,
                "detail": "「%s」属讼师刀笔体用语，%s 模式下不得出现：%s" % (term, mode, note),
                "source": src,
                "suggest": "标准状模式须直书事由；若确需使用请显式切换 output_mode=daobi 并阅读伦理声明",
            })


def _spec_for(d):
    return {"秦": "秦汉隋", "汉": "秦汉隋", "隋": "秦汉隋",
            "唐": "唐宋", "宋": "唐宋", "元": "元明", "明": "元明", "清": "清"}.get(d, "")


def check_whitelist(case, blob, dynasty, doc_type, out, skipped):
    rules = WHITELIST.get(dynasty)
    if not rules:
        skipped.append({"code": "WHITELIST", "reason": "该朝未定义白名单规则"})
        return
    for r in rules:
        when = r.get("when_doc") or []
        if when and doc_type not in when:
            skipped.append({"code": "WHITELIST", "reason":
                            "文书类型'%s'不落入白名单适用条件 %s" % (doc_type, when)})
            continue
        if not any(scan_text(blob, t) for t in r["any"]):
            out["blocking"].append({
                "code": "MISSING_REQUIRED_PHRASE",
                "detail": "%s代文书缺必含套语（须含其一：%s）：%s" % (
                    dynasty, "／".join(r["any"]), r["note"]),
                "source": r["src"],
                "suggest": "补入该朝收束语；缺之即为跨朝挪用或体式不全",
            })


def check_required_fields(case, dynasty, out, skipped):
    fields = list(REQUIRED_FIELDS.get(dynasty, []))
    # 结状/保证书类（甘结、供状、和息状…）本不以有被告为要件，故不要求被告姓名
    if not _has_defendant_requirement(case):
        dropped = [f for f in fields if "defendant" in f]
        if dropped:
            fields = [f for f in fields if f not in dropped]
            skipped.append({"code": "REQUIRED_FIELDS",
                            "reason": "文书类型'%s'不以有被告为要件，略去：%s"
                                      % (_doc_type(case), "、".join(dropped))})
    # 宋代投白纸豁免保识（spec_唐宋 模块三 规则五）
    if any(k in _doc_type(case) for k in SHUPU_EXEMPT_DOCS):
        dropped = [f for f in fields if f in ("procedure.baoshi_name",)]
        if dropped:
            fields = [f for f in fields if f not in dropped]
            skipped.append({"code": "REQUIRED_FIELDS",
                            "reason": "文书类型'%s'属投白纸例外，略去：%s"
                                      % (_doc_type(case), "、".join(dropped))})
    present = 0
    for f in fields:
        if f == "dynasty":
            present += 1
            continue
        v = dig(case, f)
        if v in (None, "", [], {}):
            if f in ("procedure.via_shupu",):          # 布尔 False 是有效值
                v = dig(case, f)
                if v is False:
                    present += 1
                    continue
            out["blocking"].append({
                "code": "MISSING_FIELD",
                "field": f,
                "detail": "%s代必填字段缺失：%s" % (dynasty, f),
                "source": "总纲§二 统一输入 Schema",
                "suggest": "按该朝通例补全并在正文标注「拟补」；或向用户追问",
            })
        else:
            present += 1
    if not fields:
        skipped.append({"code": "REQUIRED_FIELDS", "reason": "该朝未定义必填字段"})
    elif present == 0:
        # 空分母保护：一条都没提供时不得判满分
        out["warnings"].append({
            "code": "EMPTY_DENOMINATOR",
            "detail": "必填字段检查的分母为 0（无任何字段可核），结论为 unknown 而非通过",
        })


def check_kinship(case, dynasty, out):
    kin = dig(case, "parties.defendant.kinship") or ""
    if not kin:
        return
    kin = str(kin)
    for keys, dyns, penalty, src in KINSHIP_BAN:
        if dynasty not in dyns:
            continue
        if any(k in kin for k in keys):
            out["blocking"].append({
                "code": "KINSHIP_BAN",
                "detail": "身份禁告命中：被告与告诉人关系为「%s」，%s代不予受理——%s" % (
                    kin, dynasty, penalty),
                "source": src,
                "suggest": "此案在%s制下告诉人无诉权，不得生成告状；建议改由有诉权之人具名，或改为刑事公室告路径" % dynasty,
            })
            return


def check_procedure(case, dynasty, out, skipped):
    if dynasty == "隋":
        hist = dig(case, "procedure.procedure_history") or {}
        levels = PROCEDURE_GATES["隋"]["levels"]
        missing = [lv for lv in levels if not hist.get(lv)]
        if missing:
            out["blocking"].append({
                "code": "PROCEDURE_CHAIN_BROKEN",
                "detail": "隋代逐级申诉链断裂，缺层级：%s（县→郡→州→省，缺一级不得受理）" % "、".join(missing),
                "source": PROCEDURE_GATES["隋"]["src"],
                "suggest": "补齐前审层级与批语；越级输入在隋制中不成立",
            })
    if dynasty == "宋":
        status = str(dig(case, "parties.initiator.social_rank") or "")
        is_commoner = not any(k in status for k in ["官人", "进士", "僧", "道", "公人", "品官"])
        via = dig(case, "procedure.via_shupu")
        dt = _doc_type(case)
        # 投白纸是宋代明文允许的免书铺例外（spec_唐宋 模块三 规则五）：
        # 贫窭、老病、幼小、寡妇，或被劫盗、斗殴杀伤事干人命者，初词许于放词状日投白纸。
        exempt = any(k in dt for k in SHUPU_EXEMPT_DOCS)
        if is_commoner and via is False and not exempt:
            out["blocking"].append({
                "code": "NO_SHUPPU",
                "detail": "民户不经书铺不受（仅官人/进士/僧道/公人可自书；贫窭老病幼小寡妇劫盗人命可投白纸）",
                "source": PROCEDURE_GATES["宋"]["src"],
                "suggest": "置 via_shupu=true，或改用投白纸并标注'事后须补正'",
            })
        if not dig(case, "procedure.baoshi_name") and not exempt:
            out["blocking"].append({
                "code": "NO_BAOSHI",
                "detail": "状无保识不受——须经茶食人保识并加盖印子",
                "source": PROCEDURE_GATES["宋"]["src"],
                "suggest": "补 procedure.baoshi_name（茶食人姓名）；若为投白纸则此项暂不适用",
            })
        elif exempt:
            skipped.append({"code": "SHUPU_EXEMPT",
                            "reason": "文书类型'%s'属宋代投白纸例外，不适用书铺/保识前置" % dt})
    if dynasty == "明":
        cat = str(dig(case, "facts.case_type") or "")
        if any(k in cat for k in MING_ELDER_CATEGORIES) and case.get("first_instance") is not False:
            out["warnings"].append({
                "code": "MING_ELDER_FIRST",
                "detail": "「%s」属《教民榜文》受理范围，须先经本里老人、里甲理断；径告者不问虚实先杖六十" % cat,
                "source": PROCEDURE_GATES["明"]["src"],
                "suggest": "正文外附提示；仍可生成告状供备用，但须告知杖六十风险",
            })
    if dynasty == "清":
        organ = str(dig(case, "procedure.receiving_organ") or "")
        prev = dig(case, "procedure.procedure_history")
        # 上级机关标记；不得用"州"作本管判据（州县地名常同字，如"台州府"）
        superior = ["府", "司", "道", "宪台", "按察", "巡抚", "总督", "藩", "大人", "太老爷"]
        is_superior = any(k in organ for k in superior)
        if organ and is_superior and not prev:
            out["warnings"].append({
                "code": "YUE_SU",
                "detail": "越诉：收受机关为「%s」而未见本管州县前审记录。越本管官司即实亦笞五十" % organ,
                "source": PROCEDURE_GATES["清"]["src"],
                "suggest": "追问'是否已向本管州县呈控、是否被受理或受理而亏枉'；未满足者加注越诉风险",
            })


def check_baogao(case, dynasty, out):
    if dynasty != "清":
        return
    initiator = dig(case, "parties.initiator") or {}
    hits = [name for name, fn in QING_BAOGAO_CLASSES.items() if fn(initiator)]
    if hits and not (dig(case, "parties.baogao_person") or case.get("baogao_person")):
        out["blocking"].append({
            "code": "NO_BAOGAO",
            "detail": "抱告缺失：告诉人属须抱告六类（命中：%s），无抱告不准收理" % "、".join(hits),
            "source": "spec_清§六 规则三",
            "suggest": "补抱告人（须为同居亲属、深知所告事理；诬告则罪坐代告之人）",
        })


def check_length(case, dynasty, out, skipped):
    cfg = LENGTH_LIMIT.get(dynasty)
    if not cfg:
        skipped.append({"code": "LENGTH", "reason": "%s代无字数规定" % dynasty})
        return
    if dynasty == "明" and not case.get("local_rule_set"):
        skipped.append({"code": "LENGTH", "reason":
                        "明代字数约束属地方官箴，未加载 local_rule_set，默认关闭"})
        return
    body = dig(case, "document.body")
    full = collect_output_text(case)
    if not body:
        skipped.append({"code": "LENGTH", "reason": "document.body 未提供，无法计数（unknown）"})
        out["warnings"].append({"code": "LENGTH_UNKNOWN",
                                "detail": "字数检查分母为 0（无正文），结论 unknown 而非通过"})
        return
    # 口径（经法源核对后确定，勿轻易改动）：
    #   《福惠全书》卷11"状刊格眼三行，以一百四十四字为率"；淡新档案"第二、三折为呈控事由
    #   （印成方格共 720 格）"——可见字数限制管的是**字格内的呈控事由（正文）**，
    #   不含版刻的状首身份栏、被证栏与官代书戳记。故阻断口径只计 document.body。
    # 上限取"用户传入值"与"制度档默认值"的较小者——否则传 length_limit=9999 即可绕过。
    raw = case.get("length_limit")
    limit = None
    for cand in (raw, cfg["default"]):
        if isinstance(cand, int) and cand > 0:
            limit = cand if limit is None else min(limit, cand)
    n = cjk_len(body)
    if limit and n > limit:
        out["blocking"].append({
            "code": "OVER_LENGTH",
            "detail": "呈控事由（正文）%d 字，超出%s代上限 %d 字（史料层级：%s）" % (
                n, dynasty, limit, cfg["level"]),
            "source": cfg["src"],
            "suggest": "压缩至格内而非溢出；可选档位 %s。注：上限取用户值与制度档的较小者" % cfg["choices"],
        })
    # 兜底软预警：若把内容塞进结尾套语或附记栏来规避正文限额，全文会明显超限。
    # 这里只预警不阻断——因为史料口径只约束"词"，套语与版刻栏不属其列。
    nt = cjk_len(full)
    if limit and nt > int(limit * 1.5):
        out["warnings"].append({
            "code": "FULL_LENGTH_ADVISORY",
            "detail": "文书全文 %d 字，为上限 %d 字的 %.1f 倍。正文合规但篇幅异常，"
                      "请确认是否把实质内容写进了结尾套语或附记栏（此两项不计入呈控事由口径）"
                      % (nt, limit, nt / float(limit)),
            "source": cfg["src"],
            "suggest": "实质事实应写入正文（字格），套语与附记栏只放固定格式内容",
        })


def check_persons(case, dynasty, out, skipped):
    cfg = PERSONS_LIMIT.get(dynasty)
    if not cfg:
        skipped.append({"code": "PERSONS", "reason": "%s代无人数限制规定" % dynasty})
        return
    ev = case.get("evidence") or {}
    ws = ev.get("witnesses") if isinstance(ev, dict) else None
    if isinstance(ws, list):
        if len(ws) > cfg["witnesses"]:
            out["blocking"].append({
                "code": "TOO_MANY_WITNESSES",
                "detail": "干证 %d 人，超出%s代常规上限 %d 人（史料层级：%s；各地差异大）" % (
                    len(ws), dynasty, cfg["witnesses"], cfg["level"]),
                "source": cfg["src"],
                "suggest": "删减至上限内；注意'并唤/主唆/词内/笔证/拖救'等规避人数的名目同属代书伎俩",
            })
    else:
        skipped.append({"code": "PERSONS", "reason": "未提供 evidence.witnesses 列表"})
    ds = case.get("defendants_count")
    if isinstance(ds, int) and ds > cfg["defendants"]:
        out["blocking"].append({
            "code": "TOO_MANY_DEFENDANTS",
            "detail": "被告 %d 人，超出%s代常规上限 %d 人（史料层级：%s）" % (
                ds, dynasty, cfg["defendants"], cfg["level"]),
            "source": cfg["src"],
            "suggest": "摘唤主要被告，余者另案",
        })


# 案由近义词归一（审计实测：case_type="土地" 因不含"田土/地土"而绕过随状证据校验）
CASE_TYPE_ALIASES = {
    "田土": ["田土", "地土", "土地", "田业", "田亩", "庄田", "坟山", "山场"],
    "钱债": ["钱债", "债负", "债", "借债", "钱", "债欠", "利息", "还债"],
    "婚姻": ["婚姻", "婚嫁", "婚", "嫁娶", "聘", "退婚", "悔婚"],
    "人命": ["人命", "命案", "斗杀", "杀伤", "殴杀", "杀死", "人命重事"],
    "盗贼": ["盗贼", "盗", "窃盗", "偷盗", "强盗"],
}


def canon_case_type(case):
    """把案由归一到受控词表，避免"土地/田业"等近义写法绕过随状证据校验。"""
    cat = normalize(dig(case, "facts.case_type") or "")
    for canon, words in CASE_TYPE_ALIASES.items():
        if any(w in cat for w in words):
            return canon
    return str(dig(case, "facts.case_type") or "")


def check_evidence(case, dynasty, out, skipped):
    if dynasty not in ("明", "清", "宋"):
        return
    cat = canon_case_type(case)
    rule = EVIDENCE_REQUIRED.get(cat)
    if not rule:
        skipped.append({"code": "EVIDENCE", "reason": "案由'%s'无对应随状证据要求" % cat})
        return
    ev = case.get("evidence") or {}
    phys = " ".join(str(x) for x in (ev.get("physical") or [])) if isinstance(ev, dict) else ""
    got = any(any(k in phys for k in group) for group in rule)
    if not got:
        out["blocking"].append({
            "code": "EVIDENCE_MISSING",
            "detail": "证据随状缺失：案由「%s」须附 %s，现存物理证据描述为'%s'" % (
                cat, "／".join("或".join(g) for g in rule), phys or "（空）"),
            "source": "spec_清§三；spec_元明§七",
            "suggest": "缺此项即属地方状式'不准'之列；补证据清单或降级为直书事由",
        })


def check_aggravation(case, dynasty, out):
    if dynasty not in ("明", "清"):
        return
    narrative = str(dig(case, "facts.narrative") or "")
    body = str(dig(case, "document.body") or "")
    if not narrative or not body:
        return
    lifted = [t for t in AGGRAVATION_TERMS if scan_text(body, t) and not scan_text(narrative, t)]
    if lifted:
        out["warnings"].append({
            "code": "AGGRAVATION_RISK",
            "detail": "增减情罪风险：正文明示'%s'，但用户陈述的事实经过中无对应——加重性表述不得超过所告" % "、".join(lifted[:6]),
            "source": "《大明律·教唆词讼》'增减情罪与犯人同罪'；《大清律例》卷30第340条",
            "suggest": "删除或降级为直书事由。免责出口仅'教令得实'与'罪无增减'两条",
        })


def check_plate_and_date(case, dynasty, out, skipped):
    """基本形式要件：署名画押、年月日、戳记占位。"""
    if dynasty == "清":
        blob = collect_output_text(case)
        if "戳" not in blob and "代书" not in blob:
            out["blocking"].append({
                "code": "NO_STAMP_PLACEHOLDER",
                "detail": "状尾未见官代书戳记占位（应输出'［此处加盖官代书戳记：代书某某］'），无戳不准",
                "source": "spec_清§三 雍正七年例",
                "suggest": "补戳记占位符 + 做状人/写状人字段；不得伪造实物官印",
            })
    if dynasty == "明":
        blob = collect_output_text(case)
        if "写状人" not in blob:
            skipped.append({"code": "SIGNATURE", "reason": "写状人字段已由白名单规则覆盖，此处不重复断言"})


def check_yuan_gate(case, dynasty, out, skipped):
    if dynasty != "元":
        return
    if not _has_defendant_requirement(case):
        skipped.append({"code": "YUAN_GATE",
                        "reason": "文书类型'%s'为结状/保证书类，本不以有被告为要件" % _doc_type(case)})
        return
    if not dig(case, "parties.defendant.name"):
        out["blocking"].append({
            "code": "HEADLESS_ZHENG",
            "detail": "无被告姓名——元代判为'无头圆状'，不予受理",
            "source": YUAN_GATES["src"],
            "suggest": "补被告姓名与住址；不得含糊'某刁民'",
        })


# ============================================================================
# 四、主流程
# ============================================================================

def validate(case):
    out = {"verdict": "PASS", "dynasty": None, "document_type": None,
           "output_mode": None, "blocking": [], "warnings": [],
           "checks_run": [], "assertions_skipped": [], "level_tags": []}
    skipped = out["assertions_skipped"]

    dynasty = case.get("dynasty")
    out["dynasty"] = dynasty
    out["document_type"] = case.get("document_type")
    mode = case.get("output_mode") or "standard"
    out["output_mode"] = mode

    if dynasty not in DYNASTIES:
        out["blocking"].append({
            "code": "BAD_DYNASTY",
            "detail": "dynasty 必须是 %s 之一，实际为 %r" % ("/".join(DYNASTIES), dynasty),
            "source": "总纲§二 路由参数",
            "suggest": "先确认朝代，路由的第一道分叉是'谁执笔'而非案情",
        })
        out["verdict"] = "BLOCK"
        return out
    if mode not in MODES:
        out["blocking"].append({
            "code": "BAD_MODE",
            "detail": "output_mode 须为 standard 或 daobi，实际为 %r" % mode,
            "source": "总纲§二",
            "suggest": "默认 standard（官代书据实体）",
        })

    blob = collect_output_text(case)
    doc_type = str(case.get("document_type") or "")

    checks = [
        ("blacklist",  lambda: check_blacklist(case, blob, dynasty, mode, out)),
        ("whitelist",  lambda: check_whitelist(case, blob, dynasty, doc_type, out, skipped)),
        ("required",   lambda: check_required_fields(case, dynasty, out, skipped)),
        ("kinship",    lambda: check_kinship(case, dynasty, out)),
        ("procedure",  lambda: check_procedure(case, dynasty, out, skipped)),
        ("baogao",     lambda: check_baogao(case, dynasty, out)),
        ("length",     lambda: check_length(case, dynasty, out, skipped)),
        ("persons",    lambda: check_persons(case, dynasty, out, skipped)),
        ("evidence",   lambda: check_evidence(case, dynasty, out, skipped)),
        ("aggravation", lambda: check_aggravation(case, dynasty, out)),
        ("stamp",      lambda: check_plate_and_date(case, dynasty, out, skipped)),
        ("yuan_gate",  lambda: check_yuan_gate(case, dynasty, out, skipped)),
    ]
    for name, fn in checks:
        try:
            fn()
            out["checks_run"].append(name)
        except Exception as e:                       # 审计器本身出错也要显式暴露
            out["warnings"].append({
                "code": "CHECKER_ERROR",
                "detail": "检查项 %s 自身抛错：%s: %s" % (name, type(e).__name__, e),
            })

    out["level_tags"] = _level_tags(dynasty, case)
    if out["blocking"]:
        out["verdict"] = "BLOCK"
    elif out["warnings"]:
        out["verdict"] = "WARN"
    else:
        out["verdict"] = "PASS"
    return out


def _level_tags(dynasty, case):
    tags = []
    if dynasty == "隋":
        tags.append("【据隋制推定 · 暂无确证】《开皇律》已佚，仅《隋书》卷25《刑法志》可据")
    if dynasty == "元":
        tags.append("【政书条格 · 非律文】《元典章》为官修政书，非律典")
    if dynasty == "清":
        tags.append("【律例】《大清律例》卷30第340条；附例须标年份（雍正七年／乾隆七年／嘉庆二十二年）")
        if case.get("local_rule_set"):
            tags.append("【地方条例】%s 状式条例，仅对对应府县与年份生效，不可外推" % case.get("local_rule_set"))
        else:
            tags.append("【缺省】未指定府县年份，仅启用全国律例档＋《福惠全书》档")
    if dynasty == "明":
        tags.append("【律】《大明律·刑律·诉讼》教唆词讼条；【地方条例】地方状式；【秘本成例】《萧曹遗笔》等（不得与律典等量呈现）")
    return tags


# ============================================================================
# 五、自检（含反例——一条从不失败的检查等于没有检查）
# ============================================================================

BASE_QING = {
    "dynasty": "清", "document_type": "告状", "output_mode": "standard",
    "parties": {"initiator": {"name": "张阿三", "age": 40, "gender": "男",
                              "li_jurisdiction": "浙江台州府黄岩县三都二图"},
                "defendant": {"name": "李阿四", "residence": "三都三图"}},
    "facts": {"case_type": "田土", "event_time": "光绪十年三月初五",
              "place": "三都二图土名杨树湾",
              "narrative": "李阿四私移田界，占去张阿三祖田三段"},
    "procedure": {"receiving_organ": "黄岩县正堂"},
    "request": "追还田土",
    "evidence": {"witnesses": ["王五", "赵六"],
                 "physical": ["契券一纸", "粮号印串"]},
    "document": {"title": "为占业事", "body": "为占业事。民间祖遗田土坐落三都二图。",
                 "closing": "伏乞大老爷台前恩准提究断结施行。上告。如虚坐诬。",
                 "postscript": ["［此处加盖官代书戳记：代书陈大］"]},
}


def _mk(base, **over):
    """document 整体替换（它是最终产出，不该被 fixture 残留污染）；
    parties/facts/procedure/evidence 做浅层合并便于构造反例。"""
    import copy
    c = copy.deepcopy(base)
    for k, v in over.items():
        if k in ("parties", "facts", "procedure", "evidence") and isinstance(v, dict):
            c[k] = {**c.get(k, {}), **v}
        else:
            c[k] = v
    return c


SELFTEST_CASES = [
    # (名称, case, 期望 verdict)
    ("正常清代标准状（正例）",
     _mk(BASE_QING), "PASS"),
    ("秦代爰书混入现代词'原告'（反例·黑名单）",
     _mk(BASE_QING, dynasty="秦", document_type="爰书",
         document={"title": "爰书", "body": "爰书：某里士伍甲告曰。原告乙侵其田。",
                   "closing": "敢告主。"}), "BLOCK"),
    ("唐代文书误用宋语'谨状'（反例·朝代倒推）",
     _mk(BASE_QING, dynasty="唐", document_type="辞",
         document={"title": "辞", "body": "某年某月，某甲辞：乙夺其田。",
                   "closing": "谨状。"}), "BLOCK"),
    ("宋代正文超二百字（反例·字数）",
     _mk(BASE_QING, dynasty="宋", document_type="状",
         parties={"initiator": {"name": "某甲", "age": 40, "social_rank": "民户"}},
         procedure={"via_shupu": True, "baoshi_name": "茶食人陈某"},
         evidence={"witnesses": ["甲", "乙"], "physical": ["契券"]},
         document={"title": "状", "body": "为田土事。" + "争" * 250, "closing": "伏乞县司施行，谨状。"}),
     "BLOCK"),
    ("宋代民户不经书铺（反例·程序闸门）",
     _mk(BASE_QING, dynasty="宋", document_type="状",
         parties={"initiator": {"name": "某甲", "age": 40, "social_rank": "民户"}},
         procedure={"via_shupu": False, "baoshi_name": "茶食人陈某"},
         evidence={"witnesses": ["甲"], "physical": ["契券"]},
         document={"title": "状", "body": "为田土事，乙夺甲田。", "closing": "伏乞县司施行，谨状。"}),
     "BLOCK"),
    ("清代妇女无抱告（反例·抱告闸门）",
     _mk(BASE_QING, parties={"initiator": {"name": "张氏", "age": 40, "gender": "女",
                                           "li_jurisdiction": "三都二图"}}),
     "BLOCK"),
    ("隋代前审链缺失（反例·逐级闸门）",
     _mk(BASE_QING, dynasty="隋", document_type="录状",
         procedure={"procedure_history": {"county": {"result": "不理"}}},
         document={"title": "录状", "body": "【据隋制推定 · 暂无确证】录状：某甲以枉屈陈诉。",
                   "closing": "有司录状奏之。"}), "BLOCK"),
    ("明代干证五人（反例·人数）",
     _mk(BASE_QING, dynasty="明", document_type="告状",
         parties={"initiator": {"name": "张三", "age": 40, "li_jurisdiction": "某都某里"}},
         procedure={"writing_person_name": "书状人吏王某"},
         evidence={"witnesses": ["甲", "乙", "丙", "丁", "戊"], "physical": ["契券"]},
         document={"title": "为占业事", "body": "状告为占业事。", "closing": "伏乞老爷台下，俯赐准理，上告。",
                   "postscript": ["写状人王某"]}), "BLOCK"),
    ("明代标准模式混入朱语（反例·模式泄漏）",
     _mk(BASE_QING, dynasty="明", document_type="告状", output_mode="standard",
         parties={"initiator": {"name": "张三", "age": 40, "li_jurisdiction": "某都某里"}},
         procedure={"writing_person_name": "书状人吏王某"},
         evidence={"witnesses": ["甲"], "physical": ["契券"]},
         document={"title": "为虎豪吞业事", "body": "状告为虎豪吞业事，依十段锦为文。",
                   "closing": "伏乞老爷台下，俯赐准理，上告。", "postscript": ["写状人王某"]}),
     "BLOCK"),
    ("明代刀笔模式使用朱语（正例·模式放行）",
     _mk(BASE_QING, dynasty="明", document_type="告状", output_mode="daobi",
         first_instance=False,
         parties={"initiator": {"name": "张三", "age": 40, "li_jurisdiction": "某都某里"}},
         procedure={"writing_person_name": "书状人吏王某"},
         evidence={"witnesses": ["甲"], "physical": ["契券"]},
         document={"title": "为虎豪吞业事", "body": "状告为虎豪吞业事，依十段锦为文，虎豪李某势占产业。",
                   "closing": "伏乞老爷台下，俯赐准理，上告。", "postscript": ["写状人王某"]}),
     "PASS"),
    ("明代首审田土未经理老（反例·前置程序预警）",
     _mk(BASE_QING, dynasty="明", document_type="告状",
         parties={"initiator": {"name": "张三", "age": 40, "li_jurisdiction": "某都某里"}},
         procedure={"writing_person_name": "书状人吏王某"},
         evidence={"witnesses": ["甲"], "physical": ["契券"]},
         document={"title": "为占业事", "body": "状告为占业事，李某占去祖田。",
                   "closing": "伏乞老爷台下，俯赐准理，上告。", "postscript": ["写状人王某"]}),
     "WARN"),
    ("汉代子告父母（反例·身份禁告）",
     _mk(BASE_QING, dynasty="汉", document_type="告",
         parties={"initiator": {"name": "甲", "li": "某里", "rank": "士伍"},
                  "defendant": {"name": "乙", "kinship": "父母"}},
         procedure={}, evidence={},
         document={"title": "告", "body": "某里士伍甲告曰：乞治，为报。", "closing": "敢言之。"}),
     "BLOCK"),
    ("元代词状带户计（正例·朝代特有字段放行）",
     _mk(BASE_QING, dynasty="元", document_type="词状",
         parties={"initiator": {"name": "熊瑞", "age": 40, "social_rank": "民户",
                                "li_jurisdiction": "某路某州某县"},
                  "defendant": {"name": "诚德库"}},
         procedure={}, request="追给",
         evidence={"witnesses": ["某甲"], "physical": ["契一纸"]},
         document={"title": "词状", "body": "告状人熊瑞，年四十岁，系某路某县人为民户，状告为钱债事。",
                   "closing": "所供前词是的实并无虚诳。", "postscript": ["书状人吏李四（籍记吏员）"]}),
     "PASS"),
    ("明代误用元代'户计'（反例·跨朝倒推）",
     _mk(BASE_QING, dynasty="明", document_type="告状",
         parties={"initiator": {"name": "张三", "age": 40, "li_jurisdiction": "某都某里"}},
         procedure={"writing_person_name": "书状人吏王某"},
         evidence={"witnesses": ["甲"], "physical": ["契券"]},
         document={"title": "为占业事", "body": "告状人张三，系民户户计，状告为占业事。",
                   "closing": "伏乞老爷台下，俯赐准理，上告。", "postscript": ["写状人王某"]}),
     "BLOCK"),
    ("宋代民户有书铺无保识（反例·保识闸门）",
     _mk(BASE_QING, dynasty="宋", document_type="状",
         parties={"initiator": {"name": "某甲", "age": 40, "social_rank": "民户"}},
         procedure={"via_shupu": True, "baoshi_name": ""},
         evidence={"witnesses": ["甲"], "physical": ["契券"]},
         document={"title": "状", "body": "为田土事，乙夺甲田。", "closing": "伏乞县司施行，谨状。"}),
     "BLOCK"),
    ("宋代缺收束语'谨状'（反例·白名单）",
     _mk(BASE_QING, dynasty="宋", document_type="状",
         parties={"initiator": {"name": "某甲", "age": 40, "social_rank": "民户"}},
         procedure={"via_shupu": True, "baoshi_name": "茶食人陈某"},
         evidence={"witnesses": ["甲"], "physical": ["契券"]},
         document={"title": "状", "body": "为田土事，乙夺甲田。", "closing": "上告。"}),
     "BLOCK"),
    ("清代正文加重罪名而无事实对应（反例·增减情罪）",
     _mk(BASE_QING,
         document={"title": "为占业事",
                   "body": "为占业事。李阿四私移田界，实系打死人命，谋财害命。",
                   "closing": "伏乞大老爷台前恩准提究断施。上告。如虚坐诬。",
                   "postscript": ["［此处加盖官代书戳记：代书陈大］"]}),
     "WARN"),
    ("清代越诉（告府而无前审）（反例·预警型）",
     _mk(BASE_QING, procedure={"receiving_organ": "台州府太老爷"}),
     "WARN"),
    ("清代田土无契券（反例·证据随状）",
     _mk(BASE_QING, evidence={"witnesses": ["王五"], "physical": ["口头相传"]}),
     "BLOCK"),
    ("缺正文导致字数检查空分母（反例·unknown保护）",
     _mk(BASE_QING, document={"title": "为占业事", "body": "", "closing": "上告。",
                              "postscript": ["［此处加盖官代书戳记：代书陈大］"]}),
     "WARN"),

    # ===== 以下 10 例来自 2026-10-04 三路独立审计的证伪尝试，固化防回归 =====
    ("反例·拆字绕过黑名单：'朱 语'（插空格）",
     _mk(BASE_QING, dynasty="明", document_type="告状", output_mode="standard",
         first_instance=False,
         parties={"initiator": {"name": "张三", "age": 40, "li_jurisdiction": "某都某里"}},
         procedure={"writing_person_name": "某己"},
         evidence={"witnesses": ["甲"], "physical": ["契券"]},
         document={"title": "为占业事", "body": "状告为占业事。依朱 语之法办。",
                   "closing": "伏乞老爷台下准理，上告。", "postscript": ["写状人某己"]}),
     "BLOCK"),
    ("正例·繁体'謹狀'不得误判为缺收束语（归一化防误伤）",
     _mk(BASE_QING, dynasty="宋", document_type="状",
         parties={"initiator": {"name": "某甲", "age": 40, "social_rank": "民户"}},
         procedure={"via_shupu": True, "baoshi_name": "茶食人陈某"},
         evidence={"witnesses": ["甲"], "physical": ["契券"]},
         document={"title": "狀", "body": "為田土事，乙奪甲田。", "closing": "伏乞縣司施行，謹狀。"}),
     "PASS"),
    ("正例·按 SKILL.md Schema 的 li_jurisdiction 填写亦应放行（字段别名）",
     _mk(BASE_QING, dynasty="秦", document_type="爰书",
         parties={"initiator": {"name": "某甲", "li_jurisdiction": "某里", "social_rank": "士伍"},
                  "defendant": {"name": "某乙"}},
         procedure={}, evidence={},
         document={"title": "爰书",
                   "body": "爰书：某里士伍甲告曰：「同里士伍乙盗徙封，侵甲田廿步。谒执乙。」"
                           "即令令史某往诊。丞某讯乙，辞曰：「乙诚徙封，毋它坐罪。」",
                   "closing": "当腾，腾皆为报，敢告主。"}),
     "PASS"),
    ("正例·宋代投白纸豁免书铺与保识（spec_唐宋 模块三规则五）",
     _mk(BASE_QING, dynasty="宋", document_type="投白纸",
         parties={"initiator": {"name": "某寡", "age": 68, "gender": "女", "social_rank": "民户"},
                  "defendant": {"name": "某乙", "residence": "本村"}},
         procedure={"via_shupu": False, "baoshi_name": ""},
         facts={"case_type": "人命", "event_time": "元祐五年二月初三日", "place": "某乡",
                "narrative": "某乙殴伤某寡致死，事干人命"},
         evidence={"witnesses": ["某丙"], "physical": ["伤单"]},
         document={"title": "投白纸", "body": "为殴伤致死事，某乙殴伤致死，情切。",
                   "closing": "伏乞县司施行，谨状。"}),
     "PASS"),
    ("正例·元代甘结无须被告（保证书非告诉文书）",
     _mk(BASE_QING, dynasty="元", document_type="甘结",
         parties={"initiator": {"name": "某甲", "age": 40, "social_rank": "民户"},
                  "defendant": {}},
         procedure={}, evidence={"witnesses": ["某丙"], "physical": ["前契一纸"]},
         document={"title": "甘结",
                   "body": "具甘结人某甲，今与某乙和息其事，所供前词是的实并无虚诳。",
                   "closing": "对问不实甘当诳官重罪不词。", "postscript": ["书状人吏某丁（籍记吏员）"]}),
     "PASS"),
    ("反例·抱告绕过：gender 写'女性'而非'女'",
     _mk(BASE_QING, parties={"initiator": {"name": "张氏", "age": 40, "gender": "女性",
                                           "li_jurisdiction": "三都二图"}}),
     "BLOCK"),
    ("反例·禁告绕过：kinship 写'母亲'而非'父母'",
     _mk(BASE_QING, dynasty="汉", document_type="告",
         parties={"initiator": {"name": "甲", "li": "某里", "rank": "士伍"},
                  "defendant": {"name": "乙", "kinship": "母亲"}},
         procedure={}, evidence={},
         document={"title": "告", "body": "某里士伍甲告曰：「乞治，为报。」", "closing": "敢言之。"}),
     "BLOCK"),
    ("反例·案由近义绕过：case_type 写'土地'而非'田土'",
     _mk(BASE_QING, facts={"case_type": "土地", "event_time": "光绪十年",
                           "place": "三都二图", "narrative": "李某占田"},
         evidence={"witnesses": ["王五"], "physical": ["口头相传"]}),
     "BLOCK"),
    ("反例·用户传 length_limit=9999 试图放宽字数上限",
     _mk(BASE_QING, length_limit=9999,
         document={"title": "为占业事", "body": "为田土事。" + "争" * 260,
                   "closing": "伏乞大老爷台前恩准施行。上告。如虚坐诬。",
                   "postscript": ["［此处加盖官代书戳记：代书陈大］"]}),
     "BLOCK"),
    ("反例·document 传字符串时校验器不得崩溃（应正常给出阻断结论）",
     _mk(BASE_QING, document="为占业事。某乙盗移田封。"),
     "BLOCK"),
    ("反例·朝代不在八朝之内（路由参数非法）",
     _mk(BASE_QING, dynasty="南北朝"), "BLOCK"),
    ("反例·元代词状无被告姓名（无头圆状）",
     _mk(BASE_QING, dynasty="元", document_type="词状",
         parties={"initiator": {"name": "熊瑞", "age": 40, "social_rank": "户计民户"},
                  "defendant": {}},
         procedure={}, evidence={"witnesses": ["某丙"], "physical": ["契一纸"]},
         document={"title": "词状", "body": "告状人熊瑞，年四十岁，状告为钱债事。",
                   "closing": "所供前词是的实并无虚诳。", "postscript": ["书状人吏某丁"]}),
     "BLOCK"),
]


def selftest():
    print("[SELFTEST-BEGIN] 古代讼师文书校验器自检 · 共 %d 例" % len(SELFTEST_CASES))
    fails = []
    for i, (name, case, expect) in enumerate(SELFTEST_CASES, 1):
        try:
            r = validate(case)
            got = r["verdict"]
        except Exception as e:
            got = "ERROR:%s" % e
        ok = (got == expect)
        flag = "[OK]" if ok else "[FAIL]"
        print("%s #%02d 期望=%-5s 实得=%-5s  %s" % (flag, i, expect, got, name))
        if not ok:
            fails.append((i, name, expect, got))
        if got == "BLOCK" and r["blocking"]:
            for b in r["blocking"]:
                print("        └─ %s：%s" % (b.get("code"), b.get("detail")))
    print("[SELFTEST-SUMMARY] 通过 %d / %d" % (len(SELFTEST_CASES) - len(fails), len(SELFTEST_CASES)))
    # 覆盖性断言：每条检查项都必须至少出现过一次 fail，否则视为"从不失败的检查"
    must_fail_codes = {"CROSS_DYNASTY_TERM", "MODE_TERM_LEAK", "MISSING_REQUIRED_PHRASE",
                       "MISSING_FIELD", "KINSHIP_BAN", "PROCEDURE_CHAIN_BROKEN",
                       "NO_SHUPPU", "NO_BAOSHI", "NO_BAOGAO", "OVER_LENGTH",
                       "TOO_MANY_WITNESSES", "EVIDENCE_MISSING", "AGGRAVATION_RISK",
                       "YUE_SU", "LENGTH_UNKNOWN", "MING_ELDER_FIRST",
                       "NO_STAMP_PLACEHOLDER", "HEADLESS_ZHENG", "BAD_DYNASTY"}
    # 加固一：覆盖集下限。审计实测"从 must_fail_codes 删掉若干项后自检仍报 OK"——
    # 说明这道断言可被静默削弱。故设下限，删到下限以下即失败。
    MIN_MUST_FAIL = 18
    if len(must_fail_codes) < MIN_MUST_FAIL:
        print("[SELFTEST-FAIL] 覆盖集被削弱：must_fail_codes 仅 %d 项，低于下限 %d 项"
              % (len(must_fail_codes), MIN_MUST_FAIL))
        fails.append(("coverage-size", "must_fail_codes", ">=%d" % MIN_MUST_FAIL,
                      str(len(must_fail_codes))))
    # 加固二：每条检查函数都必须至少在一个用例中真正执行过（防"检查被摘掉"）。
    MUST_RUN_CHECKS = {"blacklist", "whitelist", "required", "kinship", "procedure",
                       "baogao", "length", "persons", "evidence", "aggravation",
                       "stamp", "yuan_gate"}
    seen = set()
    ran = set()
    for name, case, expect in SELFTEST_CASES:
        r = validate(case)
        ran |= set(r["checks_run"])
        for b in r["blocking"] + r["warnings"]:
            seen.add(b.get("code"))
    dead = sorted(must_fail_codes - seen)
    if dead:
        print("[SELFTEST-FAIL] 以下检查项在自检中从未触发失败，构成'从不失败的检查'：%s" % "、".join(dead))
        fails.append(("coverage", " ".join(dead), "触发过", "未触发"))
    notrun = sorted(MUST_RUN_CHECKS - ran)
    if notrun:
        print("[SELFTEST-FAIL] 以下检查函数在全部用例中从未被执行：%s" % "、".join(notrun))
        fails.append(("execution", " ".join(notrun), "执行过", "未执行"))
    if fails:
        print("[SELFTEST-FAIL] 共 %d 项不合格" % len(fails))
        return 1
    print("[SELFTEST-OK] 全部通过，且每条检查均已被反例激活")
    return 0


# ============================================================================
# 六、规则导出
# ============================================================================

def dump_rules():
    return {
        "dynasties": DYNASTIES,
        "modes": MODES,
        "blacklist": [{"term": t, "allow": list(a), "daobi_only": d,
                       "note": n, "source": s} for t, a, d, n, s in BLACKLIST],
        "whitelist": WHITELIST,
        "required_fields": REQUIRED_FIELDS,
        "kinship_ban": [{"keys": k, "dynasties": list(d), "penalty": p, "source": s}
                        for k, d, p, s in KINSHIP_BAN],
        "procedure_gates": PROCEDURE_GATES,
        "length_limit": LENGTH_LIMIT,
        "persons_limit": PERSONS_LIMIT,
        "evidence_required": EVIDENCE_REQUIRED,
        "aggravation_terms": AGGRAVATION_TERMS,
        "qing_baogao_classes": list(QING_BAOGAO_CLASSES.keys()),
    }


def write_md(path):
    L = []
    L.append("# 跨朝代禁用词表 / 必含词白名单（机器可读规则的镜像）\n")
    L.append("> **本文件由 `scripts/validate.py --write-md` 自动生成，请勿手改。**")
    L.append("> 唯一权威来源是 `scripts/validate.py` 顶部的规则数据块；改规则请改代码后重新生成本文件。\n")
    L.append("---\n")
    L.append("## 一、为什么需要这张表\n")
    L.append("八朝最容易被误用的不是格式繁简，而是**明清讼学体系（朱语、珥语、十段锦、官代书戳记、抱告、状式条例）史料最丰富，因而最容易被倒推到唐以前**。")
    L.append("本表把「某个词只允许出现在哪些朝代」做成机器可判定规则，命中即阻断。\n")
    L.append("---\n")
    L.append("## 二、禁用词黑名单（%d 条）\n" % len(BLACKLIST))
    L.append("| 词 | 允许朝代 | 限刀笔模式 | 说明 | 依据 |")
    L.append("|---|---|---|---|---|")
    for t, a, d, n, s in BLACKLIST:
        L.append("| %s | %s | %s | %s | %s |" % (
            t, "／".join(a) if a else "（无）", "是" if d else "—", n, s))
    L.append("")
    L.append("---\n")
    L.append("## 三、必含词白名单\n")
    L.append("命中该朝文书类型时，正文**必须**含所列词语之一，否则判为跨朝挪用或体式不全。\n")
    L.append("| 朝代 | 适用文书 | 必含其一 | 说明 |")
    L.append("|---|---|---|---|")
    for dyn, rules in WHITELIST.items():
        for r in rules:
            L.append("| %s | %s | %s | %s |" % (
                dyn, "／".join(r["when_doc"]) or "（不限）",
                "／".join(r["any"]), r["note"]))
    L.append("")
    L.append("---\n")
    L.append("## 四、身份禁告矩阵（前置阻断）\n")
    L.append("| 关系关键字 | 适用朝代 | 罚则 | 依据 |")
    L.append("|---|---|---|---|")
    for keys, dyns, pen, src in KINSHIP_BAN:
        L.append("| %s | %s | %s | %s |" % ("、".join(keys), "／".join(dyns), pen, src))
    L.append("")
    L.append("---\n")
    L.append("## 五、程序闸门与人数／字数／证据\n")
    L.append("### 5.1 程序闸门\n")
    L.append("| 朝代 | 规则 |")
    L.append("|---|---|")
    for d, g in PROCEDURE_GATES.items():
        L.append("| %s | %s |" % (d, g["rule"]))
    L.append("")
    L.append("### 5.2 字数上限（均为地方层级，非全国律）\n")
    L.append("| 朝代 | 默认上限 | 可选档位 | 史料层级 |")
    L.append("|---|---|---|---|")
    for d, c in LENGTH_LIMIT.items():
        L.append("| %s | %s | %s | %s |" % (
            d, c["default"] if c["default"] else "默认关闭", c["choices"], c["level"]))
    L.append("")
    L.append("### 5.3 人数上限（地方状式，各地差异显著）\n")
    L.append("| 朝代 | 被告 | 干证 |")
    L.append("|---|---|---|")
    for d, c in PERSONS_LIMIT.items():
        L.append("| %s | ≤%s | ≤%s |" % (d, c["defendants"], c["witnesses"]))
    L.append("")
    L.append("### 5.4 证据随状\n")
    L.append("| 案由 | 须附（每组取其一） |")
    L.append("|---|---|")
    for k, groups in EVIDENCE_REQUIRED.items():
        L.append("| %s | %s |" % (k, "；".join("或".join(g) for g in groups)))
    L.append("")
    L.append("---\n")
    L.append("## 六、增减情罪检测词\n")
    L.append("以下词出现在正文而用户陈述的事实经过中无对应时，触发「增减情罪」预警：\n")
    L.append("> " + "、".join(AGGRAVATION_TERMS) + "\n")
    L.append("法源：《大明律·刑律·诉讼》教唆词讼条「增减情罪诬告人者与犯人同罪」；")
    L.append("《大清律例》卷30第340条同。免责出口仅两条：**教令得实** 与 **罪无增减**。\n")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    return path


# ============================================================================
# 七、入口
# ============================================================================

def main(argv):
    if "--selftest" in argv:
        return selftest()
    if "--dump-rules" in argv:
        print(json.dumps(dump_rules(), ensure_ascii=False, indent=2))
        return 0
    if "--write-md" in argv:
        i = argv.index("--write-md")
        target = argv[i + 1] if i + 1 < len(argv) else "禁用词表.md"
        print("[WROTE] %s" % write_md(target))
        return 0
    raw = sys.stdin.read()
    if not raw.strip():
        print(json.dumps({"verdict": "ERROR",
                          "detail": "stdin 为空。用法：python validate.py < case.json"},
                         ensure_ascii=False, indent=2))
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
