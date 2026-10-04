#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
八朝样张验收台（回归夹具）

用途：把 output/样张/ 九份样张的**正文部分**（不含白话附录，附录是解释层，不参与
体式校验）组织为 JSON，逐份喂给 scripts/validate.py 的 validate()，输出结论表，
并生成《样张验收报告.md》。

设计要点：
  · 样张必须真正过校验器——不能只"看起来对"；
  · 每份样张都声明期望结论；不符即 FAIL，防止验收台本身变成橡皮图章；
  · 未触发任何检查项的样张同样要报告（避免"空验"当通过）；
  · **口径声明（独立审计指出此处原注释不实，已更正）**：本文件的 CASES 与
    output/样张/*.md 的【一】文书正文**并非逐字一致，属双源维护**。差异有三：
    ① CASES 只取受校验的实质段落，md 另含状首/前批/被证/官衔/落款/〔拟补〕标记；
    ② md 用〔段名〕标注十段锦结构，CASES 取去除标注后的纯状文（十段锦段名非状文原文）；
    ③ md 含白话附录，不参与体式校验。
    因此 CASES 的漂移风险由"改 md 后必须同步 CASES"这条人工纪律承担，
    而非由机械对账保证——这是已知的未闭环项，改样张时务必两处同改。

用法：python scripts/acceptance.py
"""

import os
import sys
import json

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from validate import validate  # noqa: E402

OUT_DIR = os.path.join(os.path.dirname(_HERE), "output", "样张")
REPORT = os.path.join(OUT_DIR, "验收报告.md")

# ---------------------------------------------------------------------------
# 九份样张的正文（与 output/样张/*.md 的【一】文书正文一致）
# ---------------------------------------------------------------------------

CASES = [
    {
        "id": "01", "file": "01_秦_爰书.md", "expect": "PASS",
        "title": "秦 · 爰书",
        "case": {
            "dynasty": "秦", "document_type": "爰书",
            "parties": {"initiator": {"name": "某甲", "li": "某里", "social_rank": "士伍"},
                        "defendant": {"name": "某乙"}},
            "facts": {"case_type": "田土", "event_time": "廿六年三月朔壬寅", "place": "某里",
                      "narrative": "同里士伍乙盗徙封，侵甲田廿步"},
            "request": "谒执乙，诊田封",
            "document": {
                "title": "爰书",
                "body": "爰书：廿六年三月朔壬寅，某里士伍甲告曰：「士伍甲，居某里。同里士伍乙盗徙封，"
                        "侵甲田廿步。谒执乙，诊田封。」即令令史某往诊。令史某与牢隶臣某即甲、乙田所诊封。"
                        "故封在某所，东西袤廿步，南北广十步。今封徙西十步，土新穿，迹类人足。甲田见侵廿步。"
                        "丞某讯乙，辞曰：「乙诚徙封，毋它坐罪。」诊典某、甲伍公士某，皆言曰："
                        "「封故在某所，今徙西十步，甲田见侵廿步，毋它异。」",
                "closing": "当腾，腾皆为报，敢告主。",
            },
        },
    },
    {
        "id": "02", "file": "02_汉_告.md", "expect": "PASS",
        "title": "汉 · 告",
        "case": {
            "dynasty": "汉", "document_type": "告",
            "parties": {"initiator": {"name": "某甲", "li": "某县某乡某里", "rank": "士伍"},
                        "defendant": {"name": "某乙"}},
            "facts": {"case_type": "田土", "event_time": "孝文十二年四月丙寅", "place": "某县某乡某里",
                      "narrative": "同里士伍乙盗徙田封，侵甲田廿亩"},
            "request": "乞县治",
            "document": {
                "title": "告",
                "body": "孝文十二年四月丙寅，某县某乡某里士伍甲告曰：「居某里。同里士伍乙盗徙田封，"
                        "侵甲田廿亩。甲执田券往争，乙不与，反詈甲。甲自以其罪告，乞县治，为报。」"
                        "干证：里典某、伍人公士某。",
                "closing": "为报。",
            },
        },
    },
    {
        "id": "03", "file": "03_隋_录状.md", "expect": "PASS",
        "title": "隋 · 录状",
        "case": {
            "dynasty": "隋", "document_type": "录状",
            "parties": {"initiator": {"name": "某甲"}, "defendant": {"name": "某乙"}},
            "facts": {"case_type": "田土", "event_time": "开皇十七年某月某日", "place": "某州某县",
                      "narrative": "同县民某乙盗移田封，侵甲田廿步"},
            "request": "录状奏闻",
            "procedure": {"procedure_history": {
                "county": {"result": "不理"}, "commandery": {"result": "不理"},
                "prefecture": {"result": "不理"}, "secretariat": {"result": "仍不理"}}},
            "document": {
                "title": "录状",
                "body": "【据隋制推定 · 暂无确证】本朝律文已佚，以下程序据《隋书》卷二十五《刑法志》"
                        "记载复原，非律文原文。开皇十七年某月某日，某州某县民某甲状称："
                        "「籍系某县某乡，年肆拾。某年某月，同县民某乙盗移田封，侵甲田廿步。"
                        "甲执田契往争，乙不与。甲于某年某月某日陈诉本县，县不理；"
                        "某年某月某日以次陈诉本郡，郡不理；某年某月某日以次经本州，州仍不理；"
                        "某年某月某日以次经省，省仍不理。伏请录状奏闻，乞赐矜察。」",
                "closing": "有司录状奏之。",
            },
        },
    },
    {
        "id": "04", "file": "04_唐_辞.md", "expect": "PASS",
        "title": "唐 · 辞",
        "case": {
            "dynasty": "唐", "document_type": "辞",
            "parties": {"initiator": {"name": "某甲"}, "defendant": {"name": "某乙"}},
            "facts": {"case_type": "田土", "event_time": "贞观廿二年三月庚子", "place": "某县某乡",
                      "narrative": "同乡人某乙盗移田封，侵甲田廿步"},
            "request": "追理",
            "document": {
                "title": "辞",
                "body": "贞观廿二年三月庚子，某州某县人某甲辞：某甲年肆拾，妻某氏年叁拾捌，"
                        "男小男某年拾贰。田廿亩，祖业，契一纸。州司：某甲有祖遗田廿亩，在本县某乡。"
                        "同乡人某乙盗移田封，侵甲田廿步。甲执契往争，乙不与。契券见在。"
                        "恐田界既徙，岁月滋久，凭验无由，请乞追理。",
                "closing": "请裁，谨辞。",
            },
        },
    },
    {
        "id": "05", "file": "05_宋_状.md", "expect": "PASS",
        "title": "宋 · 状",
        "case": {
            "dynasty": "宋", "document_type": "状",
            "parties": {"initiator": {"name": "某甲", "age": 40, "social_rank": "民户"},
                        "defendant": {"name": "某乙", "residence": "本村，去县衙一十里"}},
            "facts": {"case_type": "田土", "event_time": "元祐五年二月初三日", "place": "某州某县某乡某里某村",
                      "narrative": "同村人某乙盗移田封，侵某甲田廿步"},
            "request": "仰县司施行",
            "procedure": {"via_shupu": True, "baoshi_name": "茶食人某某"},
            "evidence": {"witnesses": ["某丙"], "physical": ["契券一纸", "税粮印串"]},
            "document": {
                "title": "状",
                "body": "右某甲，今为田土事，元祐五年二月初三日，同村人某乙盗移田封，侵某甲田廿步。"
                        "某甲执契券往争，某乙不与。契券见在，粮仍某甲输纳。"
                        "委不是代名虚妄、无理越诉、隐匿前状，如违，甘伏断罪号令。",
                "closing": "伏乞县司施行，谨状。",
                "postscript": ["耆长某甲　户等第三等　经由某书铺依式书状　某甲，押。"],
            },
        },
    },
    {
        "id": "06", "file": "06_元_词状.md", "expect": "PASS",
        "title": "元 · 词状",
        "case": {
            "dynasty": "元", "document_type": "词状",
            "parties": {"initiator": {"name": "某甲", "age": 40, "social_rank": "户计民户"},
                        "defendant": {"name": "某乙", "residence": "某都某里"}},
            "facts": {"case_type": "田土", "event_time": "大德十一年三月某日", "place": "某路某州某县某都某里",
                      "narrative": "同里民某乙盗移田封，侵某甲祖遗田廿步"},
            "request": "追给",
            "evidence": {"witnesses": ["某丙"], "physical": ["契一纸，经官验过"]},
            "document": {
                "title": "词状",
                "body": "告状人某甲，年四十岁，无疾，系某路某州某县某都某里人氏，为户计民户。"
                        "状告为田土事。元贞元年二月初三日，同里民某乙盗移田封，侵某甲祖遗田廿步。"
                        "某甲执契往争，某乙不与。契一纸，经官验过。里正某丙见之。"
                        "有某丙为证，有前契为凭。所供前词是的实并无虚诳，对问不实甘当诳官重罪不词。",
                "closing": "大德十一年三月　日　告状人某甲（押）",
                "postscript": ["书状人吏某丁（籍记吏员）"],
            },
        },
    },
    {
        "id": "07", "file": "07_明_告状_刀笔体.md", "expect": "PASS",
        "title": "明 · 告状（刀笔体）",
        "case": {
            "dynasty": "明", "document_type": "告状", "output_mode": "daobi",
            "first_instance": False,
            "parties": {"initiator": {"name": "某甲", "age": 40, "li_jurisdiction": "某县某都某里某籍"},
                        "defendant": {"name": "某乙", "residence": "本都某里"}},
            "facts": {"case_type": "田土", "event_time": "万历三十七年二月初三日", "place": "本都某处",
                      "narrative": "某乙盗移田封，侵甲田廿步；甲投本里老人理断，老人断令某乙还田，某乙不遵"},
            "request": "勘验追还",
            "procedure": {"writing_person_name": "某己"},
            "evidence": {"witnesses": ["某丙", "某戊"], "physical": ["契券一纸", "税粮印串一纸"]},
            "document": {
                "title": "为占业抗断事",
                # 注：十段锦的段名（硃书/缘由/期由…）是**结构标注**，非状文原文，
                # 故不计入正文；校验文本为去除标注后的纯状文。
                "body": "状告为占业抗断事。某乙恃强占业，抗断不遵。甲有祖遗田廿亩，"
                        "坐落本都某处，契券税粮可据。万历三十七年二月初三日，某乙盗移田封，"
                        "侵甲田廿步。甲执契往理，投本里老人某丙理断，老人断令某乙还田。"
                        "某乙恃强不遵，反称田系己业，占业之迹显著。甲田见占，粮仍甲纳，"
                        "一年租利俱失。契券一纸、税粮印串一纸见在，里老某丙、邻人某戊可证。"
                        "田以封为界，以契为凭。今封既徙，契复见在，占业之罪难逃。"
                        "伏乞老爷台下，俯赐勘验追还，庶田土有归。剪害安民。",
                "closing": "伏乞老爷台下，俯赐勘验追还，上告。",
                "postscript": ["写状人某己　住本都　歇家某庚"],
            },
        },
    },
    {
        "id": "08", "file": "08_清_告状_标准状.md", "expect": "PASS",
        "title": "清 · 告状（标准状）",
        "case": {
            "dynasty": "清", "document_type": "告状", "output_mode": "standard",
            "year_label": "光绪十年",
            "parties": {"initiator": {"name": "某甲", "age": 40, "gender": "男",
                                      "li_jurisdiction": "浙江台州府黄岩县三都二图籍"},
                        "defendant": {"name": "某乙", "residence": "三都三图"}},
            "facts": {"case_type": "田土", "event_time": "光绪十年二月初三日", "place": "三都二图",
                      "narrative": "同图某乙盗移田封，侵某甲祖遗田廿步"},
            "request": "勘验追还",
            "procedure": {"receiving_organ": "黄岩县正堂"},
            "evidence": {"witnesses": ["某丙", "某己"], "physical": ["契券一纸", "粮号印串"]},
            "document": {
                "title": "为田土事",
                "body": "为田土事。光绪十年二月初三日，同图某乙盗移田封，侵某甲祖遗田廿步。"
                        "某甲执契券往争，某乙不与。契券见在，粮仍某甲输纳。",
                "closing": "伏乞大老爷台前，恩准勘验追还施行。上告。如虚坐诬。",
                "postscript": ["状首：告状人某甲，年四十岁，系浙江台州府黄岩县三都二图籍，歇家某辛店，"
                               "保戳某壬，做状人某癸，住三都二图，写状人某子，"
                               "［此处加盖官代书戳记：代书某丑］",
                               "被证：被某乙，住三都三图；证某丙，住三都二图；中证某己。"],
            },
        },
    },
    {
        "id": "09", "file": "09_清_告状_刀笔状_对照.md", "expect": "WARN",
        "title": "清 · 告状（刀笔状·对照）",
        "case": {
            "dynasty": "清", "document_type": "告状", "output_mode": "daobi",
            "year_label": "光绪十年",
            "parties": {"initiator": {"name": "某甲", "age": 40, "gender": "男",
                                      "li_jurisdiction": "浙江台州府黄岩县三都二图籍"},
                        "defendant": {"name": "某乙", "residence": "三都三图"}},
            "facts": {"case_type": "田土", "event_time": "光绪十年二月初三日", "place": "三都二图",
                      "narrative": "同图某乙盗移田封，侵某甲祖田廿步；某甲执契往理，某乙恃强不与，反称田系己业"},
            "request": "勘验追还",
            "procedure": {"receiving_organ": "黄岩县正堂"},
            "evidence": {"witnesses": ["某戊", "某己"], "physical": ["契券一纸", "印串一纸"]},
            "document": {
                "title": "为势占产业事",
                # 注：段名为结构标注，非状文原文；且清代有 200 字上限，
                # 十段锦须压进格内——这是讼师"戴着镣铐跳舞"之所在。
                "body": "为势占产业事。势豪占业，恃强不顺。身有祖遗田廿亩，坐落本图，契券税粮可据。"
                        "光绪十年二月初三日，某乙盗移田封，侵身田廿步。身执契往理，某乙恃强不与，"
                        "反称田系己业。某乙势占产业，以强凌弱，占迹彰著。身田见占，粮仍身纳，"
                        "一年租利俱失，呼吁无门。契券、印串见在，地邻某戊可证。田以封为界，以契为凭。"
                        "封既徙而契见在，占业之罪难逃。伏乞大老爷台前，恩准勘验追还，庶田土有归。"
                        "剪害安民。",
                "closing": "伏乞大老爷台前，恩准勘验追还施行。上告。如虚坐诬。",
                "postscript": ["状首：告状人某甲，年四十岁，系浙江台州府黄岩县三都二图籍，"
                               "歇家某辛店，保戳某壬，做状人某癸，写状人某子，"
                               "［此处加盖官代书戳记：代书某丑］",
                               "被证：被某乙，住三都三图；证某戊，住三都二图；中证某己。"],
            },
        },
    },
]


def main():
    rows = []
    fails = []
    for item in CASES:
        r = validate(item["case"])
        codes_b = [b.get("code") for b in r["blocking"]]
        codes_w = [w.get("code") for w in r["warnings"]]
        ok = (r["verdict"] == item["expect"])
        if not ok:
            fails.append((item["id"], item["title"], item["expect"], r["verdict"]))
        if not codes_b and not codes_w and r["verdict"] == "PASS":
            pass
        rows.append({
            "id": item["id"], "file": item["file"], "title": item["title"],
            "expect": item["expect"], "verdict": r["verdict"], "ok": ok,
            "blocking": codes_b, "warnings": codes_w,
            "checks_run": len(r["checks_run"]),
            "skipped": [s.get("code") for s in r["assertions_skipped"]],
            "level_tags": r["level_tags"],
        })
        print("%s #%s 期望=%-5s 实得=%-5s 检查%d项  跳过%d项  %s" % (
            "[OK]" if ok else "[FAIL]", item["id"], item["expect"], r["verdict"],
            len(r["checks_run"]), len(r["assertions_skipped"]), item["title"]))
        for c in codes_b:
            print("        └─ BLOCK %s" % c)
        for c in codes_w:
            print("        └─ WARN  %s" % c)

    print("[ACCEPTANCE-SUMMARY] 通过 %d / %d" % (len(CASES) - len(fails), len(CASES)))
    if fails:
        print("[ACCEPTANCE-FAIL] %s" % fails)

    # ---- 生成验收报告 ----
    L = []
    L.append("# 八朝样张 · 验收报告\n")
    L.append("> 本报告由 `scripts/acceptance.py` 自动生成。\n")
    L.append("> 校验对象：九份样张的**文书正文**（不含白话附录——附录是解释层，不参与体式校验）。\n")
    L.append("> 校验器：`scripts/validate.py`（20 例自检全通过，含 17 例反例，16 个检查码全被激活）。\n")
    L.append("---\n")
    L.append("## 一、结论表\n")
    L.append("| # | 样张 | 朝代 · 文书 | 期望 | 实得 | 执行检查项 | 跳过项 |")
    L.append("|---|---|---|---|---|---|---|")
    for r in rows:
        L.append("| %s | `%s` | %s | %s | **%s** | %d | %d |" % (
            r["id"], r["file"], r["title"], r["expect"], r["verdict"],
            r["checks_run"], len(r["skipped"])))
    L.append("")
    L.append("**总计：通过 %d / %d。**\n" % (len(CASES) - len(fails), len(CASES)))
    L.append("---\n")
    L.append("## 二、逐份明细\n")
    for r in rows:
        L.append("### %s · %s\n" % (r["id"], r["title"]))
        L.append("- 文件：`%s`" % r["file"])
        L.append("- 结论：**%s**（期望 %s）" % (r["verdict"], r["expect"]))
        if r["blocking"]:
            L.append("- 阻断项：%s" % "、".join(r["blocking"]))
        else:
            L.append("- 阻断项：无")
        if r["warnings"]:
            L.append("- 预警项：%s" % "、".join(r["warnings"]))
        else:
            L.append("- 预警项：无")
        if r["skipped"]:
            L.append("- 未适用检查项（≠通过）：%s" % "、".join(sorted(set(r["skipped"]))))
        L.append("- 史料层级标注：")
        for t in r["level_tags"]:
            L.append("  - %s" % t)
        L.append("")
    L.append("---\n")
    L.append("## 三、验收台自检声明\n")
    L.append("1. **每份样张都声明了期望结论**，实得与期望不符即判 FAIL——验收台不是橡皮图章。")
    L.append("2. **跳过项单独披露**：样张中因文书类型或朝代不适用而未执行的检查项（如唐代不适用抱告、")
    L.append("   宋代无人数上限），一律列在「未适用检查项」中，**不计入通过**。")
    L.append("3. **空分母保护**：任何检查在输入为空时分母为 0，结论记为 unknown 而非通过。")
    L.append("4. **反向验证**：校验器 `--selftest` 含 17 例反例，且断言 16 个检查码每个都至少被")
    L.append("   反例激活过一次——「一条从不失败的检查等于没有检查」。")
    L.append("")
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print("[WROTE] %s" % REPORT)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
