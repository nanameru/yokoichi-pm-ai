#!/usr/bin/env python3
"""横市プロマネAI 進捗報告メールを Resend API で送信する。

使い方:
    RESEND_API_KEY=re_xxx python3 send_resend.py send.json
        -> send.json に並べたメールを順に送信し、結果を標準出力に出す

送信内容そのものは build_mail.py が作った .html / .txt をそのまま読む。
このスクリプトは本文を一切書き換えない。

send.json の形:
{
  "from": "横市プロマネAI <yokoichi-ai@example.com>",
  "reply_to": "someone@example.com",          # 任意
  "dry_run": false,                            # true なら送信せず宛先だけ出す
  "messages": [
    {
      "label": "I列",
      "to":  ["a@example.com"],
      "cc":  ["b@example.com"],                # 任意
      "bcc": ["c@example.com"],                # 任意
      "subject": "【横市】高木先生進捗報告 2026年9月11日",
      "html_file": "out_I.html",
      "text_file": "out_I.txt"
    }
  ]
}

終了コード:
    0 = 全通成功 / 1 = 1通でも失敗
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

API_URL = "https://api.resend.com/emails"
USER_AGENT = "yokoichi-pm-ai/1.0"
# Resend の既定レート上限は 2 リクエスト/秒。余裕をもって間隔を空ける
SEND_INTERVAL_SEC = 0.75
MAX_ATTEMPTS = 3


def die(msg):
    print("エラー: %s" % msg, file=sys.stderr)
    sys.exit(1)


def as_list(v):
    """文字列でも配列でも受け取れるようにする。空なら None を返す。"""
    if v is None:
        return None
    if isinstance(v, str):
        v = [x.strip() for x in v.split(",")]
    v = [x for x in v if x]
    return v or None


def read_body(path, kind):
    if not os.path.exists(path):
        die("%s が見つかりません: %s" % (kind, path))
    with open(path, encoding="utf-8") as f:
        body = f.read()
    if not body.strip():
        die("%s が空です: %s" % (kind, path))
    return body


def post(payload, api_key):
    """Resend に1件POSTする。(成功したか, 表示用メッセージ) を返す。"""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    for attempt in range(1, MAX_ATTEMPTS + 1):
        req = urllib.request.Request(
            API_URL,
            data=data,
            method="POST",
            headers={
                "Authorization": "Bearer %s" % api_key,
                "Content-Type": "application/json",
                # 既定の python-urllib は Resend 前段の Cloudflare に 403(1010) で弾かれる
                "User-Agent": USER_AGENT,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                body = json.loads(res.read().decode("utf-8"))
                return True, body.get("id", "(id不明)")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            # 429(レート上限)と5xxだけ待って再試行する。4xxは設定ミスなので即座に返す
            if e.code == 429 or e.code >= 500:
                if attempt < MAX_ATTEMPTS:
                    time.sleep(2 * attempt)
                    continue
            return False, "HTTP %s %s" % (e.code, detail)
        except Exception as e:  # ネットワーク断など
            if attempt < MAX_ATTEMPTS:
                time.sleep(2 * attempt)
                continue
            return False, "%s: %s" % (type(e).__name__, e)
    return False, "再試行の上限に達しました"


def main():
    if len(sys.argv) != 2:
        die("使い方: python3 send_resend.py send.json")

    api_key = os.environ.get("RESEND_API_KEY", "").strip()

    with open(sys.argv[1], encoding="utf-8") as f:
        cfg = json.load(f)

    sender = cfg.get("from")
    if not sender:
        die("send.json に from がありません")

    messages = cfg.get("messages") or []
    if not messages:
        die("send.json に messages がありません")

    dry_run = bool(cfg.get("dry_run"))
    reply_to = as_list(cfg.get("reply_to"))

    if not dry_run and not api_key:
        die("環境変数 RESEND_API_KEY が設定されていません")

    print("差出人: %s" % sender)
    print("通数: %d%s" % (len(messages), "（ドライラン）" if dry_run else ""))
    print("-" * 60)

    failures = 0
    for i, m in enumerate(messages, 1):
        label = m.get("label") or "#%d" % i
        to = as_list(m.get("to"))
        if not to:
            print("[%s] 失敗: to が空です" % label)
            failures += 1
            continue
        subject = m.get("subject")
        if not subject:
            print("[%s] 失敗: subject が空です" % label)
            failures += 1
            continue

        html = read_body(m["html_file"], "HTML")
        text = read_body(m["text_file"], "テキスト")

        payload = {"from": sender, "to": to, "subject": subject,
                   "html": html, "text": text}
        for key, src in (("cc", m.get("cc")), ("bcc", m.get("bcc"))):
            val = as_list(src)
            if val:
                payload[key] = val
        if reply_to:
            payload["reply_to"] = reply_to

        dest = "To:%s" % ",".join(to)
        if payload.get("cc"):
            dest += " / Cc:%s" % ",".join(payload["cc"])
        if payload.get("bcc"):
            dest += " / Bcc:%s" % ",".join(payload["bcc"])

        if dry_run:
            print("[%s] 送信せず: %s" % (label, dest))
            print("        件名: %s" % subject)
            print("        本文: HTML %d文字 / テキスト %d文字" % (len(html), len(text)))
            continue

        ok, info = post(payload, api_key)
        if ok:
            print("[%s] 送信成功 id=%s" % (label, info))
            print("        %s" % dest)
        else:
            print("[%s] 送信失敗 %s" % (label, info))
            print("        %s" % dest)
            failures += 1

        if i < len(messages):
            time.sleep(SEND_INTERVAL_SEC)

    print("-" * 60)
    if failures:
        print("結果: %d通中 %d通が失敗しました" % (len(messages), failures))
        sys.exit(1)
    print("結果: %d通すべて成功しました" % len(messages))


if __name__ == "__main__":
    main()
