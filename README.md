# 🏛️ 政治ニュース自動収集Bot (Google Drive記録機能付き)

日本の政治ニュースを自動収集し、AIによる動向予測とともにDiscordに通知し、さらにそのログをGoogle Driveに記録するGitHub Actions対応のBotです。

## ✨ 主な機能

### 🤖 AI搭載機能
- **政治関連度判定**: Gemini AIが各ニュースの政治関連度を0〜100点でスコアリング
- **動向予測**: AIが日本・世界への影響と注目ポイントを自動分析し、**簡潔にコメント**
- **重複防止**: 過去24時間の投稿履歴を管理し、同じニュースの重複投稿を防止

### 🔗 記録・管理機能 (NEW!)
- **Google Driveへ自動記録**: Discordに投稿したニュース（タイトル、リンク、AIコメント含む）の全文ログを、**Google Drive上のテキストファイルに自動追記**します。
- **NotebookLM連携の土台**: 記録されたDrive上のファイルをNotebookLMにソースとして読み込ませることで、**月別・年別のニュース動向分析**や**過去の振り返り**が可能になります。

### 📰 ニュース収集
- **複数のニュースソース**:
  - 日経新聞・速報
  - ロイター通信・速報
  - Yahoo!ニュース
- **キーワードフィルタリング**: 政治関連キーワードで自動フィルタリング
- **スマート除外**: スポーツ・エンタメなど無関係なニュースを除外

### ⏰ 自動実行
- **日本時間 6:00〜22:00** の間、毎時自動実行
- **夜間（23:00〜5:00）** は通知を停止

---

## 📋 必要な環境とシークレット設定

このBotを実行するには、以下の情報が必要です。これらはGitHubリポジトリの **Settings > Secrets and variables > Actions** に設定してください。

| シークレット名 | 説明 | 取得先 |
| :--- | :--- | :--- |
| `DISCORD_WEBHOOK_POLITICS` | ニュースを投稿するDiscordチャンネルのWebhook URL | Discord |
| `GEMINI_API_KEY` | ニュースのスコアリングとコメント生成に使用するAPIキー | Google AI Studio |
| `GOOGLE_DRIVE_CREDENTIALS` | Google Driveへの書き込み権限を持つ**サービスアカウント**のJSONキー全文 | Google Cloud Platform (GCP) |

**💡 Google Drive設定の注意点:**
`GOOGLE_DRIVE_CREDENTIALS`に設定したサービスアカウントに対し、ログファイルを保存するGoogle Driveフォルダ（デフォルトでは`GitHub Political News Logs`）に**編集者権限**を付与する必要があります。

---

## 🚀 セットアップ手順

1. **リポジトリのフォーク/クローン**
2. **`requirements.txt` の更新**: `pydrive2==1.6.8` を追記します。
3. **APIキーとWebhook URLの取得と設定**
4. **Google Driveサービスアカウントの作成とJSONキーの取得** ([GCP IAM と管理] から)
5. **GitHub Secretsに3つのキーを設定** (`DISCORD_WEBHOOK_POLITICS`, `GEMINI_API_KEY`, `GOOGLE_DRIVE_CREDENTIALS`)
6. **`news_politics_hourly.py` と `hourly-politics.yml` を最新版に更新**し、コミット＆プッシュします。
