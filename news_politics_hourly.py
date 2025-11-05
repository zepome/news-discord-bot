#!/usr/bin/env python3
"""
政治ニュース自動収集Bot（AIコメント付き重複防止＆Google Drive記録版）
"""

import os
import sys
import re
import time
import json
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
import feedparser
import requests
import google.generativeai as genai

# --- Google Drive 連携用の import ---
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
# ------------------------------------

# 環境変数の取得
DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_POLITICS')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
POLITICAL_SCORE_THRESHOLD = int(os.environ.get('POLITICAL_SCORE_THRESHOLD', '70'))
MAX_NEWS_TO_POST = int(os.environ.get('MAX_NEWS_TO_POST', '3'))

# --- Google Drive 連携用の環境変数 ---
DRIVE_CREDENTIALS_JSON = os.environ.get('GOOGLE_DRIVE_CREDENTIALS')
DRIVE_FOLDER_NAME = os.environ.get('DRIVE_FOLDER_NAME', 'GitHub_Political_News_Logs')
LOG_FILE_NAME = os.environ.get('LOG_FILE_NAME', 'political_news_summary.txt')
# ------------------------------------

# 投稿履歴ファイルのパス
HISTORY_FILE = 'posted_news_history.json'
HISTORY_RETENTION_HOURS = 24  # 24時間以内の重複をチェック

# Gemini API設定
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.0-flash-exp')

# 互換性チェック: JSON強制出力はMarkdown形式に戻すため使用しませんが、
# 既存のコード構造を残すため、フラグだけ保持します。
# ⚠️ 今回、JSON形式の出力は使用しないため、このブロックは実質的に影響を与えません。
try:
    from google.generativeai.types import GenerateContentConfig
    GEMINI_CONFIG_AVAILABLE = True
except ImportError:
    GEMINI_CONFIG_AVAILABLE = False
    print("⚠️ GenerateContentConfig はMarkdown出力のため使用しません。")


# 政治関連キーワード (省略なし)
POLITICAL_KEYWORDS = [
    '自民', '国民民主', '参政', '維新', '立憲', '共産', '公明', '社民',
    '高市', '麻生', '片山', '小野田', '茂木', '鈴木俊一', '岸田', '河野', '石破',
    '首相', '総理', '大臣', '官房長官', '国会', '与党', '野党', '解散総選挙',
    '内閣支持率', '外交', '安保', '憲法改正', '防衛', '予算案', '経済対策',
    '金融政策', '増税', '減税', '少子化', '賃上げ', '円安', '為替', '日銀',
    '規制改革', 'デジタル庁', 'マイナ', 'エネルギー', '原発', '環境', 'GX'
]

# RSSフィード設定 (省略なし)
NEWS_FEEDS = {
    '日経新聞': 'https://www.nikkei.com/rss/001.xml',
    'ロイター通信': 'https://jp.reuters.com/rssFeed/topNews',
    'Yahoo!ニュース': 'https://news.yahoo.co.jp/rss/topics/top-picks.xml'
}

# (load_posted_history, save_posted_history, is_posted, mark_as_posted, fetch_news, filter_by_keywords は変更なし)

def load_posted_history():
    """投稿履歴を読み込む"""
    if Path(HISTORY_FILE).exists():
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            try:
                history = json.load(f)
                # 古い履歴を削除 (24時間以上前のもの)
                cutoff_time = datetime.now().timestamp() - HISTORY_RETENTION_HOURS * 3600
                history = {k: v for k, v in history.items() if v > cutoff_time}
                return history
            except json.JSONDecodeError:
                print("⚠️ 履歴ファイルが破損しています。新規作成します。")
                return {}
    return {}

def save_posted_history(history):
    """投稿履歴を保存する"""
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

def is_posted(title, link, history):
    """ニュースが既に投稿されているかチェック"""
    # タイトルとURLからハッシュを生成
    content = title + link
    _hash = hashlib.md5(content.encode('utf-8')).hexdigest()
    return _hash in history

def mark_as_posted(title, link, history):
    """ニュースを投稿済みとしてマーク"""
    content = title + link
    _hash = hashlib.md5(content.encode('utf-8')).hexdigest()
    history[_hash] = datetime.now().timestamp()

def fetch_news(feed_url):
    """RSSフィードからニュースを取得"""
    try:
        d = feedparser.parse(feed_url)
        return d.entries
    except Exception as e:
        print(f"  ❌ RSSフィード取得エラー: {e}")
        return []

def filter_by_keywords(entries):
    """キーワードでフィルタリング"""
    filtered = []
    for entry in entries:
        title = entry.get('title', '')
        description = entry.get('summary', '')
        
        # タイトルまたは概要に政治関連キーワードが含まれているかチェック
        is_political = any(keyword in title or keyword in description for keyword in POLITICAL_KEYWORDS)
        
        # 芸能・スポーツなどの除外キーワードチェック（スマート除外）
        is_excluded = ('スポーツ' in title or 'エンタメ' in title or '野球' in title or 'サッカー' in title or '恋愛' in title)
        
        if is_political and not is_excluded:
            filtered.append(entry)
            
    return filtered

def score_and_filter_with_ai(entries):
    """Geminiで政治関連度をスコアリングし、動向予測コメントを生成 (Markdown出力に変更)"""
    if not GEMINI_API_KEY:
        print("❌ Gemini APIキーが設定されていません。AIスコアリングをスキップします。")
        for entry in entries:
            entry['score'] = 100 # スコアを最大にして通過させる
        return entries
    
    scored_news = []
    
    # プロンプトのテンプレートをMarkdown形式に変更
    prompt_template = """
    あなたは日本の政治動向を分析する専門家です。以下のニュース記事を分析し、**全て日本語**で以下の形式で出力してください。

    【ニュース】
    タイトル: {title}
    ニュース概要: {description}

    **重要**: 回答はこの形式のみとし、他の説明文、マークダウン（例: ```json）や余分な文字は付けないでください。

    ---
    🎯 **関連度**: [0〜100点の数字]点
    ━━━━━━━━━━━━━━━━━━
    **🇯🇵 日本への影響:**
    - （日本の政治・経済・社会への具体的な影響を予測。箇条書き）
    **🌏 世界への影響:**
    - （国際関係や世界情勢への影響を予測。箇条書き）
    **📊 注目ポイント:**
    - （今後注視すべき点や展開の可能性。箇条書き）
    """

    for entry in entries:
        title = entry.get('title', '不明')
        description = entry.get('summary', '概要なし')
        
        user_prompt = prompt_template.format(title=title, description=description)
        
        try:
            # configなしで実行 (Markdown形式の文字列を期待)
            response = model.generate_content(user_prompt)
            response_text = response.text.strip()
            
            # 1. スコアを抽出
            score_match = re.search(r'🎯 \*\*関連度\*\*: (\d+)点', response_text)
            score = int(score_match.group(1)) if score_match else 0
            
            # 2. AIコメント（Markdown全文）を保存
            ai_comment = response_text
            
            entry['score'] = score
            entry['ai_comment'] = ai_comment
            
        except Exception as e:
            # エラー時にログを出力
            print(f"  ⚠️ Gemini APIエラー発生（スコアリング）: {e}")
            entry['score'] = 0 
            entry['ai_comment'] = 'AIコメント生成とスコアリングに失敗しました。'
        
        scored_news.append(entry)
        
        time.sleep(2) # ⚠️ APIレート制限回避のため、待ち時間を2秒に増加
        
    return scored_news

def generate_ai_comment(title, description):
    """Discord投稿用のAIコメントを生成 (未使用)"""
    if not GEMINI_API_KEY:
        return ""
    return ""


def create_discord_message(news, ai_comment):
    """Discord投稿メッセージを作成 (Markdown形式に戻す)"""
    score = news.get('score', 0)
    title = news.get('title', 'タイトル不明')
    link = news.get('link', '#')
    source = news.get('source', '不明')
    
    # スコアに応じた星評価 (元の形式に合わせる)
    if score >= 90:
        stars = '⭐⭐⭐⭐⭐'
    elif score >= 80:
        stars = '⭐⭐⭐⭐'
    elif score >= 70:
        stars = '⭐⭐⭐'
    elif score >= 60:
        stars = '⭐⭐'
    else:
        stars = '⭐'
    
    # メッセージ作成
    content = f"🏛️ **[出典: {source}] {title}**\n"
    content += f"━━━━━━━━━━━━━━━━━━\n"
    content += f"🎯 **関連度**: {score}点 {stars}\n"
    content += f"🔗 {link}\n"
    
    # AIコメントを追記
    content += f"\n━━━━━━━━━━━━━━━━━━\n🤖 **AIによる動向予測**\n\n{ai_comment}"
    
    # Embedを使わず、contentのみを返す
    return {'content': content}

# --------------------------------------------------------------------------------
# --- Google Drive 連携関数 (変更なし) ---
# --------------------------------------------------------------------------------

def authenticate_google_drive():
    """Google Drive APIの認証"""
    if not DRIVE_CREDENTIALS_JSON:
        print("❌ Google Drive認証情報が設定されていません。")
        return None

    try:
        # クレデンシャルJSONファイルを一時的に作成
        creds_path = Path('gdrive_creds.json')
        # JSON文字列をファイルに書き込む
        with open(creds_path, 'w', encoding='utf-8') as f:
            f.write(DRIVE_CREDENTIALS_JSON)
            
        gauth = GoogleAuth()
        # サービスアカウント認証
        gauth.LoadServiceAccountCredentials(str(creds_path.resolve()))
        drive = GoogleDrive(gauth)
        
        # 一時ファイルを削除
        creds_path.unlink()
        
        print("✅ Google Drive認証成功")
        return drive
    except Exception as e:
        print(f"⚠️ Google Drive認証エラー: {e}")
        # エラー発生時も一時ファイルが残る可能性を考慮して再度削除を試みる
        if 'creds_path' in locals() and creds_path.exists():
             creds_path.unlink()
        return None

def find_or_create_file(drive, folder_name, file_name):
    """指定フォルダ内のファイルを検索、なければ作成して返す"""
    
    # フォルダを検索・作成
    folder_list = drive.ListFile({
        'q': f"title='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    }).GetList()
    
    if folder_list:
        folder = folder_list[0]
        folder_id = folder['id']
        print(f"📂 既存のフォルダ '{folder_name}' を発見 (ID: {folder_id})")
    else:
        folder = drive.CreateFile({
            'title': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        })
        folder.Upload()
        folder_id = folder['id']
        print(f"📂 新しいフォルダ '{folder_name}' を作成 (ID: {folder_id})")
        # 新しいフォルダを作成した場合、サービスアカウントの権限設定が手動で必要になる場合があるため注意喚起
        print("⚠️ 新しいフォルダを作成しました。このフォルダにサービスアカウントの編集権限が付与されていることを確認してください。")


    # ファイルを検索
    file_list = drive.ListFile({
        'q': f"title='{file_name}' and '{folder_id}' in parents and trashed=false"
    }).GetList()

    if file_list:
        file = file_list[0]
        print(f"📝 既存のログファイル '{file_name}' を発見")
    else:
        # ファイルが存在しない場合は新規作成
        file = drive.CreateFile({
            'title': file_name,
            'parents': [{'id': folder_id}],
            'mimeType': 'text/plain' # テキストファイルとして作成
        })
        # 初期コンテンツとして空文字列を設定（必須ではないが安全策として）
        file.SetContentString("")
        file.Upload()
        print(f"📝 新しいログファイル '{file_name}' を作成")

    return file

def append_to_drive_log(drive, news_list, drive_folder_name, log_file_name):
    """Google Drive上のファイルにニュースまとめを追記"""
    print("\n☁️ Google Driveへの追記を開始...")
    
    try:
        log_file = find_or_create_file(drive, drive_folder_name, log_file_name)
        
        # 現在の内容をダウンロード
        current_content = ""
        try:
             current_content = log_file.GetContentString(encoding='utf-8')
        except Exception:
             print("ℹ️ ファイル内容のダウンロードに失敗しましたが、新規ファイルとして処理を続行します。")

        
        # 追記する内容を作成
        append_content = ""
        now = datetime.now()
        append_content += "\n" + "=" * 80 + "\n"
        append_content += f"📰 投稿時刻: {now.strftime('%Y年%m月%d日 %H:%M:%S')} (JST)\n"
        append_content += "=" * 80 + "\n"
        
        for news in news_list:
            append_content += f"🏛️ 【政治】{news['title']}\n"
            append_content += f"🎯 関連度: {news.get('score', 0)}点\n"
            append_content += f"🔗 {news['link']}\n"
            
            # AIコメントも含める
            if news.get('ai_comment'):
                # Markdown形式のコメントをそのまま追記
                append_content += "\n🤖 AIによる動向予測:\n"
                # AIコメントの整形を解除し、そのままログに書き込む（Markdownがそのまま残る）
                append_content += news['ai_comment'] + "\n"
            
            append_content += "-" * 80 + "\n"
            
        # 追記してアップロード
        log_file.SetContentString(current_content + append_content)
        log_file.Upload()
        
        print("✅ Google Driveログファイルに追記成功")

    except Exception as e:
        print(f"❌ Google Drive追記処理中にエラー: {e}")

# --------------------------------------------------------------------------------
# --- メイン処理 (変更なし) ---
# --------------------------------------------------------------------------------

def main():
    """メイン処理"""
    print("=" * 60)
    print("📰 政治ニュース自動収集Bot（Drive連携版）")
    print(f"⏰ 実行時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🔑 Gemini APIキー: {'設定済み' if GEMINI_API_KEY else '未設定'}")
    print(f"🔑 Drive認証情報: {'設定済み' if DRIVE_CREDENTIALS_JSON else '未設定'}")
    print("=" * 60)
    
    if not DISCORD_WEBHOOK_URL:
        print("❌ DISCORD_WEBHOOK_POLITICS が設定されていません")
        sys.exit(1)

    # 投稿履歴の読み込み
    posted_history = load_posted_history()
    print(f"📚 履歴件数: {len(posted_history)}")
    
    all_entries = []
    print("\n🔎 ニュースソースの確認:")
    for source, url in NEWS_FEEDS.items():
        print(f"  [{source}] から取得中...")
        entries = fetch_news(url)
        print(f"    - {len(entries)}件取得")
        all_entries.extend(entries)

    print(f"\n📊 合計 {len(all_entries)} 件の記事を取得")
    
    # 重複チェック (Discord投稿履歴に基づく)
    new_entries = [entry for entry in all_entries if not is_posted(entry.get('title', ''), entry.get('link', ''), posted_history)]
    print(f"🗑️ 重複を除いた新規記事: {len(new_entries)} 件")

    if not new_entries:
        print("\n📭 投稿・処理する新しいニュースがありません")
        return

    # キーワードフィルタリング
    keyword_filtered_news = filter_by_keywords(new_entries)
    print(f"📰 キーワードフィルタ後: {len(keyword_filtered_news)} 件")

    # Gemini判定
    print("\n🤖 Geminiによるスコアリングと動向予測:")
    # ここでエラーが発生していた
    scored_news = score_and_filter_with_ai(keyword_filtered_news)
    
    # スコアで最終フィルタリング
    political_news = [news for news in scored_news if news['score'] >= POLITICAL_SCORE_THRESHOLD]
    
    print("\n📜 最終選考結果:")
    for entry in political_news:
        print(f"  ✅ [{entry['score']}点] {entry['title']}")
    
    print(f"✅ 最終投稿対象: {len(political_news)}件")
    
    # Discord投稿
    if not political_news:
        print("\n📭 投稿するニュースがありません")
        return
    
    posted = 0
    posted_news_items = [] # 投稿したニュースを保持するためのリスト
    
    for news in political_news[:MAX_NEWS_TO_POST]:
        print(f"\n━━━━━━━━━━━━━━━━━━")
        print(f"処理中: {news['title']}")
        
        # AIコメントをnews['ai_comment']から取得
        ai_comment = news.get('ai_comment', 'AIコメント生成に失敗しました。')
        
        if ai_comment:
            print(f"  ✅ AIコメント: {ai_comment[:30]}...")
        
        time.sleep(2)  # ⚠️ API制限対策のため、2秒に増加
        
        # メッセージ作成（AIコメント付き）
        message = create_discord_message(news, ai_comment)
        
        try:
            requests.post(DISCORD_WEBHOOK_URL, json=message, timeout=10)
            
            # 投稿成功したら履歴に追加
            mark_as_posted(news['title'], news['link'], posted_history)
            posted += 1
            posted_news_items.append(news) # 投稿成功したニュースをリストに追加
            print(f"  ✅ Discord投稿成功")
            time.sleep(3) # ⚠️ Discord APIのレート制限回避のため、3秒に増加
        except Exception as e:
            print(f"  ❌ Discord投稿エラー: {e}")
            time.sleep(1)
            
    # 履歴を保存
    save_posted_history(posted_history)
    
    # === 新規追加箇所: Google Driveへの追記 ===
    if posted_news_items and DRIVE_CREDENTIALS_JSON:
        drive_service = authenticate_google_drive()
        if drive_service:
            append_to_drive_log(drive_service, posted_news_items, DRIVE_FOLDER_NAME, LOG_FILE_NAME)
    # ==========================================
    
    print(f"\n🎉 処理完了。{posted}件のニュースを投稿し、Driveに記録しました。")

if __name__ == "__main__":
    main()
