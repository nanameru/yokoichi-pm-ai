# 横市プロマネAI

毎週金曜の朝9時に、AMED全体WBSを読んで担当者ごとの進捗報告メールを自動送信する仕組みです。

## 構成

```
毎週金曜 09:00 JST
  ↓
Claude のスケジュール実行が起動
  ↓
このリポジトリを取得
  ↓
Google Drive から WBS をダウンロード
  ↓
run_weekly.py が 集計 → 本文生成 → 送信 を実行
```

集計もメール本文も、すべてこのリポジトリのコードが行います。AIは数えません。
実行のたびに判定がぶれないようにするためです。

| ファイル | 役割 |
|---|---|
| `aggregate_wbs.py` | WBSを読んで集計する。対象行・進捗率・遅延・記入待ちの判定 |
| `build_mail.py` | メールのHTMLとテキストを組み立てる |
| `send_resend.py` | Resend API で送信する |
| `run_weekly.py` | 上の3つを1コマンドで順に実行する |
| `config.json` | 列の位置・担当者名・宛先の設定 |

## 準備するもの

**1. Resend の API キー**

Resend の API keys から発行します。権限は Sending access で足ります。
ルーティンの環境変数に `RESEND_API_KEY` として設定してください。
プロンプト本文には書かないでください。

**2. 差出人アドレス**

Resend の Domains で認証済みのドメインが必要です。
現在は `ai@pm.rebucul.com` を使っています。

**3. WBSの閲覧権限**

`2026年度AMED全体WBS.xlsx`（fileId: `1f0f7T5GYQQJO84ht2XKHIYUckuMIfb_A`）を
Google Drive で共有してもらってください。閲覧のみで動きます。書き込みはしません。

**4. コネクタ**

Claude の設定で Google Drive を接続してください。Gmail は不要です。

## ルーティンの設定

| 項目 | 値 |
|---|---|
| スケジュール | `0 0 * * 5`（UTC 00:00 = JST 毎週金曜 09:00） |
| リポジトリ | このリポジトリ |
| モデル | Claude Sonnet |
| 使用ツール | Bash / Read / Glob / Grep / Google Drive |
| 環境変数 | `RESEND_API_KEY` |

プロンプトは `prompt.txt` の内容をそのまま貼り付けてください。

## 手元で試す

```bash
pip install openpyxl
export RESEND_API_KEY=re_xxx

# 送信せず、宛先と集計結果だけ確認する
python3 run_weekly.py --wbs wbs.xlsx \
  --from "横市プロマネAI <ai@pm.rebucul.com>" \
  --to 自分のアドレス --dry-run

# 実際に自分宛へ送る
python3 run_weekly.py --wbs wbs.xlsx \
  --from "横市プロマネAI <ai@pm.rebucul.com>" \
  --to 自分のアドレス
```

`--date 2026-09-15` を付けると、その日を基準日として集計できます。

## 集計ルール

| 項目 | 定義 |
|---|---|
| 対象行 | 担当列が `●`（主担当）の行。`○` と空欄は対象外 |
| 完了案件数 | 対象行のうち、完了実績（O列）に日付がある行数 |
| 進捗率 | 完了案件数 ÷ 対象行数 |
| 直近2週間の完了 | 完了実績日が実行日の13日前〜当日に入る行 |
| 今後2週間の予定 | 完了実績が空欄で、期限日が実行日〜14日後に入る行。期限は変更予定を優先 |
| 遅延タスク | 完了予定を過ぎ、完了実績が空欄で、**フェーズが「完了」でない**行 |
| 完了実績未記入 | 完了実績が空欄で、**フェーズが「完了」**の行 |

最後の2行が重要です。フェーズを「完了」にしても完了実績日を書いていない行は、
遅延ではなく「完了実績のご記入をお願いしたいタスク」という別の節に出ます。

## 本番配信に切り替える

テスト送信では、黄色い帯と「テスト運用」のフッターが付き、全列が1つのアドレスに届きます。

本番配信にするには、`config.json` の各列に `recipients` を追加してください。

```json
{"key": "K", "label": "田中さん・諸我さん",
 "recipients": {
   "to": ["someone@example.com"],
   "cc": ["another@example.com"],
   "bcc": ["motoyama@example.com"]
 }}
```

そのうえで `--to` の代わりに `--production` を付けて実行します。
`recipients` が未設定の列があると、送信せずに止まります。

**この切り替えで実在の相手にメールが届きます。** 1列ずつ開放することをおすすめします。

## メールの見た目を変えるとき

`build_mail.py` を直してコミットするだけです。プロンプトは触りません。次の実行から反映されます。

Outlook（Wordレンダリングエンジン）でも崩れないように、次の制約で書かれています。変更するときも守ってください。

- レイアウトは `<table>` のみ。flexbox / grid / position は使わない
- 進捗バーの幅は px 固定。% を使うとモバイルGmailで潰れる
- CSSはインライン `style` のみ。`<style>` タグと `class` は使わない
- 背景画像とWebフォントは使わない
- 骨格は `width` `bgcolor` `align` `border` のHTML属性でも二重指定する

## うまく動かないとき

| 症状 | 確認する場所 |
|---|---|
| `RESEND_API_KEY が設定されていません` | ルーティンの環境変数 |
| `シート「WBS_AMED_R8」がありません` | WBSのシート名が変わっていないか |
| `ヘッダーが想定と違います` | WBSの列が増減していないか。`config.json` の `columns` を直す |
| メールが届かない | Resend の Logs。ドメインが Verified か |
| バーが細い線になる | 取得したコードが古い。ブランチを確認 |
