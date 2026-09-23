#!/usr/bin/env python3
"""WBSのxlsxを読み、担当列ごとの集計JSONを書き出す。

使い方:
    python3 aggregate_wbs.py wbs.xlsx config.json 出力先ディレクトリ [--date YYYY-MM-DD]
        -> 出力先/data_I.json ... data_L.json を書き出す

集計ルールはすべてこのファイルに書く。プロンプト側には書かない。
実行のたびにAIが解釈し直すと件数がぶれるため、判定は全部コードで行う。
"""

import datetime
import json
import os
import sys

DONE_PHASE = "完了"


def die(msg):
    print("エラー: %s" % msg, file=sys.stderr)
    sys.exit(1)


def as_date(v):
    """セルの値を date にする。日付でなければ None。"""
    if isinstance(v, datetime.datetime):
        return v.date()
    if isinstance(v, datetime.date):
        return v
    return None


def fmt(d):
    return "%d/%d/%d" % (d.year, d.month, d.day) if d else ""


def text(v):
    return str(v).strip() if v is not None else ""


def build_comment(label, agg):
    """コメントを決定論的に組み立てる。

    AIに書かせると件数を取り違えるため（実際に遅延を12件と書いて13件に直した
    実行があった）、数字を含む文は必ずこの関数が作る。文体は依頼形で統一する。
    """
    lines = []
    tc, dc = agg["target_count"], agg["done_count"]
    if tc == 0:
        return "%s のご担当として登録されているタスクは現在ございません。" % label
    lines.append("%s ご担当のタスクは、対象%d件のうち%d件が完了し、進捗率は%s%%です。"
                 % (label, tc, dc, agg["rate"]))

    rd = agg["recent_done"]
    if rd:
        names = "、".join("「%s」" % r["task"] for r in rd[:3])
        more = "ほか%d件" % (len(rd) - 3) if len(rd) > 3 else ""
        lines.append("直近2週間では%d件が完了しております（%s%s）。" % (len(rd), names, more))
    else:
        lines.append("直近2週間に完了したタスクはございませんでした。")

    dl = agg["delays"]
    if dl:
        lines.append("遅延タスクは%d件あり、当初予定から日数が経っています。"
                     "お手すきの際にご確認いただければ幸いです。" % len(dl))

    pr = agg["pending_record"]
    if pr:
        lines.append("%d件のタスクはフェーズが完了となっておりますが、"
                     "完了実績日が未記入のため進捗率に含めておりません。"
                     "完了日のご記入をお願いできますと幸いです。" % len(pr))

    pl = agg["plans"]
    if pl:
        lines.append("今後2週間では%d件が期限を迎えます。ご確認をお願いいたします。" % len(pl))

    if len(lines) == 1:
        lines.append("特記事項はございません。")
    return "\n".join(lines)


def aggregate(ws, cfg, target, today):
    c = cfg["columns"]
    recent_from = today - datetime.timedelta(days=cfg["recent_days"])
    plan_to = today + datetime.timedelta(days=cfg["plan_days"])

    rows = []
    for r in range(cfg["header_row"] + 1, ws.max_row + 1):
        task = text(ws.cell(row=r, column=c["task"]).value)
        if not task:
            continue                      # タスク名が空の見出し行は対象外
        if text(ws.cell(row=r, column=target["col"]).value) != "●":
            continue                      # ○（サブ担当）と空欄は対象外
        rows.append({
            "task": task,
            "phase": text(ws.cell(row=r, column=c["phase"]).value),
            "due": as_date(ws.cell(row=r, column=c["due"]).value),
            "actual": as_date(ws.cell(row=r, column=c["actual"]).value),
            "revised": as_date(ws.cell(row=r, column=c["revised"]).value),
            "remark": text(ws.cell(row=r, column=c["remark"]).value),
        })

    done = [x for x in rows if x["actual"]]
    target_count, done_count = len(rows), len(done)
    rate = round(done_count / target_count * 100, 1) if target_count else None

    recent_done = sorted([x for x in done if recent_from <= x["actual"] <= today],
                         key=lambda x: x["actual"], reverse=True)

    # フェーズは完了だが完了実績が空欄の行。遅延には入れず、記入のお願いに回す
    pending_record = [x for x in rows
                      if not x["actual"] and x["phase"] == DONE_PHASE]

    plans = []
    for x in rows:
        if x["actual"] or x["phase"] == DONE_PHASE:
            continue
        due = x["revised"] or x["due"]
        if due and today <= due <= plan_to:
            plans.append((due, x, "変更予定" if x["revised"] else "完了予定"))
    plans.sort(key=lambda t: t[0])

    delays = [x for x in rows
              if x["due"] and x["due"] < today
              and not x["actual"] and x["phase"] != DONE_PHASE]
    delays.sort(key=lambda x: x["due"])

    delay_out = []
    for x in delays:
        if x["revised"]:
            n = abs((today - x["revised"]).days)
            state = ("変更予定から%d日経過" % n if x["revised"] < today
                     else "未到来（あと%d日）" % n)
        else:
            state = "変更予定なし"
        delay_out.append({
            "task": x["task"], "planned": fmt(x["due"]),
            "planned_over": (today - x["due"]).days,
            "revised": fmt(x["revised"]), "revised_state": state,
            "phase": x["phase"], "remark": x["remark"],
        })

    agg = {
        "column_label": target["label"],
        "fetched_at": datetime.datetime.now().strftime("%Y/%-m/%-d %H:%M"),
        "test_mode": True,
        "to": target["to"], "cc": target["cc"], "bcc": target["bcc"],
        "done_count": done_count, "target_count": target_count, "rate": rate,
        "recent_from": fmt(recent_from), "recent_to": fmt(today),
        "plan_from": fmt(today), "plan_to": fmt(plan_to),
        "recent_done": [{"task": x["task"], "date": fmt(x["actual"])} for x in recent_done],
        "plans": [{"task": x["task"], "due": fmt(d), "kind": k, "phase": x["phase"]}
                  for d, x, k in plans],
        "delays": delay_out,
        "pending_record": [{"task": x["task"], "planned": fmt(x["due"]),
                            "revised": fmt(x["revised"]), "phase": x["phase"]}
                           for x in pending_record],
    }
    agg["comment"] = build_comment(target["label"], agg)
    return agg


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 3:
        die("使い方: python3 aggregate_wbs.py wbs.xlsx config.json 出力先ディレクトリ [--date YYYY-MM-DD]")
    xlsx, cfg_path, outdir = args

    today = datetime.date.today()
    for a in sys.argv[1:]:
        if a.startswith("--date="):
            today = datetime.datetime.strptime(a.split("=", 1)[1], "%Y-%m-%d").date()

    try:
        import openpyxl
    except ImportError:
        die("openpyxl がありません。pip install openpyxl を実行してください")

    if not os.path.exists(xlsx):
        die("WBSファイルが見つかりません: %s" % xlsx)
    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)

    wb = openpyxl.load_workbook(xlsx, data_only=True)
    if cfg["sheet_name"] not in wb.sheetnames:
        die("シート「%s」がありません。あるのは: %s" % (cfg["sheet_name"], wb.sheetnames))
    ws = wb[cfg["sheet_name"]]

    # ヘッダーが想定どおりか確かめる。列がずれたまま集計すると気づけないため
    expect = ["No", "大項目", "中項目", "小項目", "タスク"]
    actual = [text(ws.cell(row=cfg["header_row"], column=i).value) for i in range(1, 6)]
    if actual != expect:
        die("ヘッダーが想定と違います。%d行目: %s" % (cfg["header_row"], actual))

    os.makedirs(outdir, exist_ok=True)
    print("集計日: %s / シート: %s" % (fmt(today), cfg["sheet_name"]))
    print("-" * 64)
    for t in cfg["targets"]:
        agg = aggregate(ws, cfg, t, today)
        path = os.path.join(outdir, "data_%s.json" % t["key"])
        with open(path, "w", encoding="utf-8") as f:
            json.dump(agg, f, ensure_ascii=False, indent=2)
        print("%s列 %-20s 対象%3d 完了%3d 率%5s%% 直近%2d 予定%2d 遅延%3d 記入待ち%2d"
              % (t["key"], t["label"], agg["target_count"], agg["done_count"],
                 agg["rate"], len(agg["recent_done"]), len(agg["plans"]),
                 len(agg["delays"]), len(agg["pending_record"])))
    print("-" * 64)
    print("%s に %d 件書き出しました" % (outdir, len(cfg["targets"])))


if __name__ == "__main__":
    main()
