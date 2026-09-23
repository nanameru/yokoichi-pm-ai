#!/usr/bin/env python3
"""横市プロマネAI 週次進捗メールを、集計から送信まで一括で実行する。

使い方:
    RESEND_API_KEY=re_xxx python3 run_weekly.py \
        --wbs wbs.xlsx \
        --from "横市プロマネAI <ai@pm.rebucul.com>" \
        --to you@example.com \
        [--work /tmp/yokoichi] [--date YYYY-MM-DD] [--dry-run] [--reply-to a@b.com]

--to を指定した場合、全列をそのアドレスだけに送る（テスト送信）。
本番配信は --production を付け、config.json の recipients に実アドレスを書く。

このスクリプト1本で aggregate_wbs.py -> build_mail.py -> send_resend.py を順に呼ぶ。
呼び出し側（ルーティンのプロンプト）は、WBSをダウンロードしてこれを実行するだけでよい。
"""

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def die(msg):
    print("エラー: %s" % msg, file=sys.stderr)
    sys.exit(1)


def run(cmd):
    print("$ %s" % " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.stdout:
        print(r.stdout.rstrip())
    if r.returncode != 0:
        if r.stderr:
            print(r.stderr.rstrip(), file=sys.stderr)
        die("失敗しました: %s" % cmd[1])
    return r.stdout


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--wbs", required=True, help="ダウンロード済みのWBS xlsx")
    p.add_argument("--from", dest="sender", required=True, help='差出人 "名前 <アドレス>"')
    p.add_argument("--to", help="テスト送信先。全列をこのアドレスに送る")
    p.add_argument("--production", action="store_true",
                   help="config.json の recipients に従って実際の宛先へ送る")
    p.add_argument("--reply-to", help="返信先アドレス")
    p.add_argument("--work", default="/tmp/yokoichi", help="作業ディレクトリ")
    p.add_argument("--date", help="集計基準日 YYYY-MM-DD（省略時は当日）")
    p.add_argument("--config", default=os.path.join(HERE, "config.json"))
    p.add_argument("--dry-run", action="store_true", help="送信せず宛先だけ出す")
    a = p.parse_args()

    if not a.to and not a.production:
        die("--to （テスト送信先）か --production のどちらかを指定してください")
    if a.production and not a.dry_run:
        # 本番は実在の相手に届く。取り違えを防ぐため設定の有無を先に確かめる
        with open(a.config, encoding="utf-8") as f:
            cfg = json.load(f)
        missing = [t["key"] for t in cfg["targets"] if not t.get("recipients", {}).get("to")]
        if missing:
            die("本番配信には config.json の recipients が必要です。未設定の列: %s"
                % ", ".join(missing))
    if not a.dry_run and not os.environ.get("RESEND_API_KEY", "").strip():
        die("環境変数 RESEND_API_KEY が設定されていません")

    os.makedirs(a.work, exist_ok=True)
    with open(a.config, encoding="utf-8") as f:
        cfg = json.load(f)

    print("=" * 64)
    print("1. WBSを集計する")
    print("=" * 64)
    cmd = [sys.executable, os.path.join(HERE, "aggregate_wbs.py"), a.wbs, a.config, a.work]
    if a.date:
        cmd.append("--date=" + a.date)
    run(cmd)

    print()
    print("=" * 64)
    print("2. メール本文を組み立てる")
    print("=" * 64)
    messages = []
    for t in cfg["targets"]:
        key = t["key"]
        data = os.path.join(a.work, "data_%s.json" % key)
        prefix = os.path.join(a.work, "out_%s" % key)
        if a.production:
            # 本番配信では黄色いテスト帯とテスト用フッターを外す
            with open(data, encoding="utf-8") as f:
                d = json.load(f)
            d["test_mode"] = False
            with open(data, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
        run([sys.executable, os.path.join(HERE, "build_mail.py"), data, prefix])

        with open(data, encoding="utf-8") as f:
            d = json.load(f)
        subject_date = d["fetched_at"].split(" ")[0].replace("/", "年", 1).replace("/", "月", 1) + "日"
        tag = "" if a.production else "/テスト送信"
        msg = {"label": "%s列" % key,
               "subject": "【横市%s】%s進捗報告 %s" % (tag, t["label"], subject_date),
               "html_file": prefix + ".html", "text_file": prefix + ".txt"}
        if a.production:
            r = t["recipients"]
            msg["to"] = r["to"]
            if r.get("cc"):
                msg["cc"] = r["cc"]
            if r.get("bcc"):
                msg["bcc"] = r["bcc"]
        else:
            msg["to"] = [a.to]
        messages.append(msg)

    send = {"from": a.sender, "messages": messages}
    if a.reply_to:
        send["reply_to"] = a.reply_to
    if a.dry_run:
        send["dry_run"] = True
    send_path = os.path.join(a.work, "send.json")
    with open(send_path, "w", encoding="utf-8") as f:
        json.dump(send, f, ensure_ascii=False, indent=2)

    print()
    print("=" * 64)
    print("3. 送信する%s" % ("（本番配信）" if a.production else "（テスト送信）"))
    print("=" * 64)
    run([sys.executable, os.path.join(HERE, "send_resend.py"), send_path])
    print()
    print("完了しました。")


if __name__ == "__main__":
    main()
