#!/usr/bin/env python3
"""横市プロマネAI 進捗報告メールのHTML/テキストを組み立てる。

使い方:
    python3 build_mail.py data.json out_prefix
    -> out_prefix.html と out_prefix.txt を書き出す

HTMLはこのファイル内のテンプレート定数だけで組み立てる。呼び出し側は
data.json に数値と文字列を入れるだけで、HTMLには一切触れない。
これによりメールの体裁が実行ごとにぶれない。

メール用HTMLの制約（意図的にこの範囲だけを使う）:
- レイアウトは table のみ。flexbox / grid / position は使わない
- 幅は px 固定。% は使わない（モバイルGmailで潰れるため）
- CSSはインライン style のみ。<style> タグや class は使わない
- 骨格は width / bgcolor / align / border のHTML属性でも二重に指定する
- 背景画像とWebフォントは使わない
"""
import html
import json
import sys

WBS_URL = ("https://docs.google.com/spreadsheets/d/"
           "1f0f7T5GYQQJO84ht2XKHIYUckuMIfb_A/edit?gid=150842212#gid=150842212")

BAR_WIDTH = 400  # 進捗バーの全幅(px)

GREETING = ("お疲れさまです。WBSをもとに、現在の進捗状況をお送りします。"
            "お手すきのタイミングでご確認いただけますと幸いです。")
NO_DONE = ("直近2週間の完了実績のご記入はありませんでした。"
           "完了済みのものがございましたら、WBSへのご記入をお願いします。")
NO_PLAN = "今後2週間に期限を迎えるタスクはございません。"
NO_DELAY = "現時点で期限を過ぎているタスクはございません。"
PENDING_NOTE = ("フェーズは「完了」ですが、完了実績日が空欄のため未完了として集計しています。"
                "完了日のご記入をお願いします。")
FOOTER = "本メールは自動送信です。ご返信は不要です。"
FOOTER_TEST = "本メールは自動送信です。（横市プロマネAI テスト運用）"


def footer_text(test_mode):
    """テスト送信中は従来の短いフッター、本番運用では案内文つきのフッター。"""
    return FOOTER_TEST if test_mode else FOOTER

C_NAVY = "#1F4E79"
C_NAVY_LT = "#B8D4EC"
C_HEAD_BG = "#EDF2F7"
C_HEAD_TX = "#33475B"
C_BORDER = "#C9D6E2"
C_BORDER_LT = "#DDDDDD"
C_GREEN = "#2E7D32"
C_GRAY = "#DDDDDD"
C_RED = "#B3261E"
C_RED_LT = "#E8B4B0"
C_RED_BG = "#FDF3F2"
C_RED_TX = "#7A2E29"

TD_LABEL = ('<td width="120" bgcolor="%s" style="background-color:%s;'
            'border:1px solid %s;padding:9px 10px;">' % (C_HEAD_BG, C_HEAD_BG, C_BORDER))
TD_VALUE = '<td style="border:1px solid %s;padding:9px 10px;">' % C_BORDER
TD_CELL = '<td style="border:1px solid %s;padding:8px 10px;">' % C_BORDER_LT
TD_CELL_C = ('<td align="center" style="border:1px solid %s;padding:8px 10px;">'
             % C_BORDER_LT)


def esc(value):
    """HTMLに入れる文字列をエスケープする。空なら「なし」。"""
    text = "" if value is None else str(value).strip()
    if not text:
        return "なし"
    return html.escape(text, quote=False)


def bar(rate):
    """進捗バー。幅はpx固定。rate が None なら空文字。"""
    if rate is None:
        return ""
    green = int(round(BAR_WIDTH * float(rate) / 100.0))
    green = max(0, min(BAR_WIDTH, green))
    gray = BAR_WIDTH - green
    cells = []
    if green > 0:
        cells.append(
            '<td width="%d" height="12" bgcolor="%s" style="width:%dpx;height:12px;'
            'background-color:%s;font-size:0;line-height:0;">&nbsp;</td>'
            % (green, C_GREEN, green, C_GREEN))
    if gray > 0:
        cells.append(
            '<td width="%d" height="12" bgcolor="%s" style="width:%dpx;height:12px;'
            'background-color:%s;font-size:0;line-height:0;">&nbsp;</td>'
            % (gray, C_GRAY, gray, C_GRAY))
    return ('<table cellpadding="0" cellspacing="0" border="0" width="%d" '
            'style="width:%dpx;border-collapse:collapse;"><tr>%s</tr></table>'
            % (BAR_WIDTH, BAR_WIDTH, "".join(cells)))


def empty_row(text):
    return ('<tr><td colspan="2" style="border:1px solid %s;padding:8px 10px;">'
            '<font size="2" color="#777777">%s</font></td></tr>'
            % (C_BORDER_LT, esc(text)))


def done_rows(items):
    if not items:
        return empty_row(NO_DONE)
    out = []
    for it in items:
        out.append(
            '<tr>%s<font size="2" color="#333333">%s</font></td>'
            '%s<font size="2" color="%s">%s</font></td></tr>'
            % (TD_CELL, esc(it.get("task")), TD_CELL_C, C_GREEN, esc(it.get("date"))))
    return "".join(out)


def plan_rows(items):
    if not items:
        return empty_row(NO_PLAN)
    out = []
    for it in items[:10]:
        out.append(
            '<tr>%s<font size="2" color="#333333">%s</font><br>'
            '<font size="1" color="#777777">%s ／ フェーズ: %s</font></td>'
            '%s<font size="2" color="%s">%s</font></td></tr>'
            % (TD_CELL, esc(it.get("task")), esc(it.get("kind")), esc(it.get("phase")),
               TD_CELL_C, C_NAVY, esc(it.get("due"))))
    return "".join(out)


def delay_row(label, value, extra=None, extra_color=C_RED):
    cell = ('<td width="128" bgcolor="%s" style="background-color:%s;border:1px solid %s;'
            'padding:7px 10px;"><font size="2" color="%s">%s</font></td>'
            % (C_RED_BG, C_RED_BG, C_RED_LT, C_RED_TX, esc(label)))
    body = '<font size="2" color="#111111">%s</font>' % esc(value)
    if extra:
        body += '　<font size="2" color="%s"><b>%s</b></font>' % (extra_color, esc(extra))
    return ('<tr>%s<td style="border:1px solid %s;padding:7px 10px;">%s</td></tr>'
            % (cell, C_RED_LT, body))


def delay_blocks(items):
    if not items:
        return ('<br><table width="100%" cellpadding="0" cellspacing="0" border="0" '
                'style="width:100%;border-collapse:collapse;"><tr>'
                '<td bgcolor="#F1F8F2" style="background-color:#F1F8F2;'
                'border:1px solid #C8E6C9;padding:10px 12px;">'
                '<font size="2" color="#2E7D32">' + NO_DELAY +
                '</font></td></tr></table>')
    out = []
    for it in items:
        rows = [
            '<tr><td colspan="2" bgcolor="%s" style="background-color:%s;'
            'border:1px solid %s;padding:9px 10px;">'
            '<font size="2" color="#FFFFFF"><b>%s</b></font></td></tr>'
            % (C_RED, C_RED, C_RED, esc(it.get("task"))),
            delay_row("当初完了予定", it.get("planned"),
                      "当初予定から%s日経過" % it.get("planned_over", 0)),
            delay_row("変更予定", it.get("revised"), it.get("revised_state")),
            delay_row("フェーズ", it.get("phase")),
        ]
        if str(it.get("remark") or "").strip():
            rows.append(
                '<tr><td width="128" bgcolor="%s" style="background-color:%s;'
                'border:1px solid %s;padding:7px 10px;">'
                '<font size="2" color="%s">備考</font></td>'
                '<td style="border:1px solid %s;padding:7px 10px;">'
                '<font size="2" color="#555555">%s</font></td></tr>'
                % (C_RED_BG, C_RED_BG, C_RED_LT, C_RED_TX, C_RED_LT,
                   esc(it.get("remark"))))
        out.append(
            '<br><table width="100%%" cellpadding="0" cellspacing="0" border="1" '
            'bordercolor="%s" style="width:100%%;border-collapse:collapse;">%s</table>'
            % (C_RED_LT, "".join(rows)))
    return "".join(out)


def pending_rows(items):
    """フェーズは完了だが完了実績が空欄の行。1件につき1行。"""
    out = []
    for it in items:
        due = it.get("revised") or it.get("planned")
        label = "変更予定" if it.get("revised") else "完了予定"
        out.append(
            '<tr>%s<font size="2" color="#333333">%s</font><br>'
            '<font size="1" color="#777777">フェーズ: %s</font></td>'
            '%s<font size="2" color="#8A6D1F">%s<br>'
            '<font size="1" color="#777777">%s</font></font></td></tr>'
            % (TD_CELL, esc(it.get("task")), esc(it.get("phase")),
               TD_CELL_C, esc(due), esc(label)))
    return "".join(out)


def section_head(title, note=""):
    extra = ('<font size="2" color="#777777">　%s</font>' % esc(note)) if note else ""
    return ('<font size="3" color="%s"><b>%s</b></font>%s<br><br>'
            % (C_NAVY, esc(title), extra))


def list_table(header_left, header_right, rows):
    return ('<table width="100%%" cellpadding="0" cellspacing="0" border="1" '
            'bordercolor="%s" style="width:100%%;border-collapse:collapse;">'
            '<tr><td bgcolor="%s" style="background-color:%s;border:1px solid %s;'
            'padding:8px 10px;"><font size="2" color="%s"><b>%s</b></font></td>'
            '<td width="104" align="center" bgcolor="%s" style="background-color:%s;'
            'border:1px solid %s;padding:8px 10px;">'
            '<font size="2" color="%s"><b>%s</b></font></td></tr>%s</table>'
            % (C_BORDER_LT, C_HEAD_BG, C_HEAD_BG, C_BORDER_LT, C_HEAD_TX,
               esc(header_left), C_HEAD_BG, C_HEAD_BG, C_BORDER_LT, C_HEAD_TX,
               esc(header_right), rows))


def pending_section(items):
    """完了実績が未記入の行をまとめた節。0件なら節ごと出さない。"""
    if not items:
        return ""
    return ("".join([
        section_head("完了実績のご記入をお願いしたいタスク"),
        '<table width="100%%" cellpadding="0" cellspacing="0" border="0" '
        'style="width:100%%;border-collapse:collapse;"><tr>'
        '<td bgcolor="#FFF8E1" style="background-color:#FFF8E1;'
        'border:1px solid #E6D18F;padding:10px 12px;">'
        '<font size="2" color="#7A5C1E">%s</font></td></tr></table>'
        % esc(PENDING_NOTE),
        list_table("タスク", "期限", pending_rows(items)),
        "<br>",
    ]))


def build_html(d):
    rate = d.get("rate")
    rate_text = "対象なし" if rate is None else ("%s%%" % rate)
    summary = (
        '<table width="100%%" cellpadding="0" cellspacing="0" border="1" bordercolor="%s" '
        'style="width:100%%;border-collapse:collapse;">'
        '<tr>%s<font size="2" color="%s"><b>完了案件数</b></font></td>'
        '%s<font size="2" color="#111111"><b>%d件</b> ／ 対象 %d件</font></td></tr>'
        '<tr>%s<font size="2" color="%s"><b>進捗率</b></font></td>'
        '%s<font size="4" color="%s"><b>%s</b></font><br>%s</td></tr>'
        '<tr>%s<font size="2" color="%s"><b>遅延タスク</b></font></td>'
        '%s<font size="2" color="%s"><b>%d件</b></font></td></tr>'
        '</table>'
        % (C_BORDER,
           TD_LABEL, C_HEAD_TX, TD_VALUE, d.get("done_count", 0), d.get("target_count", 0),
           TD_LABEL, C_HEAD_TX, TD_VALUE, C_NAVY, esc(rate_text), bar(rate),
           TD_LABEL, C_HEAD_TX, TD_VALUE, C_RED, len(d.get("delays") or [])))

    body = "".join([
        '<font size="2" color="#333333">%s</font><br><br>' % esc(GREETING),
        section_head("進捗状況"),
        summary,
        "<br>",
        section_head("直近2週間の完了案件",
                     "%s〜%s" % (d.get("recent_from"), d.get("recent_to"))),
        list_table("タスク", "完了実績日", done_rows(d.get("recent_done") or [])),
        "<br>",
        section_head("今後2週間の予定案件",
                     "%s〜%s" % (d.get("plan_from"), d.get("plan_to"))),
        list_table("タスク", "期限", plan_rows(d.get("plans") or [])),
        "<br>",
        '<font size="3" color="%s"><b>遅延タスク（%d件）</b></font>'
        % (C_RED, len(d.get("delays") or [])),
        delay_blocks(d.get("delays") or []),
        "<br>",
        pending_section(d.get("pending_record") or []),
        '<font size="3" color="%s"><b>AIプロマネからのコメント</b></font>' % C_NAVY,
        '<table width="100%%" cellpadding="0" cellspacing="0" border="0" '
        'style="width:100%%;border-collapse:collapse;"><tr>'
        '<td bgcolor="#F4F7FA" style="background-color:#F4F7FA;border-left:4px solid %s;'
        'padding:12px 14px;"><font size="2" color="#333333">%s</font></td></tr></table>'
        % (C_NAVY, esc(d.get("comment")).replace("\n", "<br>")),
        "<br>",
        '<table width="100%" cellpadding="0" cellspacing="0" border="0" '
        'style="width:100%;border-collapse:collapse;"><tr>'
        '<td bgcolor="#F1F8F2" style="background-color:#F1F8F2;border:1px solid #C8E6C9;'
        'padding:12px 14px;"><font size="2" color="#2E5A32">'
        '<b>ご確認いただき、タスクの更新をお願いします🙏</b></font><br>'
        '<font size="2"><a href="' + WBS_URL + '" style="color:' + C_NAVY + ';">'
        '2026年度AMED全体WBS を開く</a></font></td></tr></table>',
    ])

    notice = ""
    if d.get("test_mode", True):
        notice = ('<tr><td bgcolor="#FFF8E1" style="background-color:#FFF8E1;'
                  'padding:10px 20px;border-bottom:1px solid #E6D18F;">'
                  '<font size="2" color="#7A5C1E">※テスト送信です。本番の宛先は '
                  'To: %s ／ Cc: %s ／ Bcc: %s</font></td></tr>'
                  % (esc(d.get("to")), esc(d.get("cc")), esc(d.get("bcc"))))

    return ('<table width="600" cellpadding="0" cellspacing="0" border="0" '
            'style="width:600px;border-collapse:collapse;'
            "font-family:'Hiragino Kaku Gothic ProN','Yu Gothic',Meiryo,sans-serif;\">"
            '<tr><td bgcolor="%s" style="background-color:%s;padding:18px 20px;">'
            '<font color="#FFFFFF" size="4"><b>%s 進捗報告</b></font><br>'
            '<font color="%s" size="2">%s 時点 ／ 2026年度AMED全体WBS</font></td></tr>'
            '%s'
            '<tr><td style="padding:20px;">%s</td></tr>'
            '<tr><td bgcolor="#F0F0F0" style="background-color:#F0F0F0;padding:12px 20px;">'
            '<font size="1" color="#777777">%s</font></td></tr></table>'
            % (C_NAVY, C_NAVY, esc(d.get("column_label")), C_NAVY_LT,
               esc(d.get("fetched_at")), notice, body,
               esc(footer_text(d.get("test_mode", True)))))


def build_text(d):
    rate = d.get("rate")
    lines = []
    if d.get("test_mode", True):
        lines.append("※テスト送信です。本番の宛先は To:%s / Cc:%s / Bcc:%s"
                     % (d.get("to"), d.get("cc"), d.get("bcc")))
    lines += [
        GREETING,
        "",
        "対象WBS: 2026年度AMED全体WBS.xlsx",
        "取得日時: %s" % d.get("fetched_at"),
        "対象列: %s（●主担当のみ）" % d.get("column_label"),
        "",
        "【進捗状況】",
        "・完了案件数: %d件 / %d件" % (d.get("done_count", 0), d.get("target_count", 0)),
        "・進捗率: %s" % ("対象なし" if rate is None else "%s%%" % rate),
        "・遅延タスク: %d件" % len(d.get("delays") or []),
        "",
        "【直近2週間の完了案件】(%s〜%s)" % (d.get("recent_from"), d.get("recent_to")),
    ]
    recent = d.get("recent_done") or []
    if recent:
        lines += ["- %s（完了: %s）" % (i.get("task"), i.get("date")) for i in recent]
    else:
        lines.append(NO_DONE)
    lines += ["", "【今後2週間の予定案件】(%s〜%s)" % (d.get("plan_from"), d.get("plan_to"))]
    plans = (d.get("plans") or [])[:10]
    if plans:
        lines += ["- %s（期限: %s / %s / フェーズ: %s）"
                  % (i.get("task"), i.get("due"), i.get("kind"), i.get("phase"))
                  for i in plans]
    else:
        lines.append(NO_PLAN)
    lines += ["", "【遅延タスク】"]
    delays = d.get("delays") or []
    if delays:
        for i in delays:
            lines += [
                "- %s" % i.get("task"),
                "  当初完了予定: %s（当初予定から%s日経過）"
                % (i.get("planned"), i.get("planned_over")),
                "  変更予定: %s（%s）" % (i.get("revised"), i.get("revised_state")),
                "  フェーズ: %s / 備考: %s" % (i.get("phase"), i.get("remark") or "なし"),
            ]
    else:
        lines.append(NO_DELAY)
    pending = d.get("pending_record") or []
    if pending:
        lines += ["", "【完了実績のご記入をお願いしたいタスク】", PENDING_NOTE]
        for i in pending:
            due = i.get("revised") or i.get("planned")
            label = "変更予定" if i.get("revised") else "完了予定"
            lines.append("- %s（%s: %s / フェーズ: %s）"
                         % (i.get("task"), label, due, i.get("phase")))
    lines += [
        "",
        "【AIプロマネからのコメント】",
        str(d.get("comment") or "特記事項なし"),
        "",
        "ご確認いただき、タスクの更新をお願いします🙏",
        WBS_URL,
        "",
        "--",
        footer_text(d.get("test_mode", True)),
    ]
    return "\n".join(lines)


def main():
    if len(sys.argv) != 3:
        print("usage: build_mail.py data.json out_prefix", file=sys.stderr)
        return 1
    with open(sys.argv[1], encoding="utf-8") as f:
        data = json.load(f)
    prefix = sys.argv[2]
    with open(prefix + ".html", "w", encoding="utf-8") as f:
        f.write(build_html(data))
    with open(prefix + ".txt", "w", encoding="utf-8") as f:
        f.write(build_text(data))
    print("wrote %s.html and %s.txt" % (prefix, prefix))
    return 0


if __name__ == "__main__":
    sys.exit(main())
