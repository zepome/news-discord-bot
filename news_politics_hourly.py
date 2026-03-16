#!/usr/bin/env python3
"""
政治ニュース自動収集Bot（AIコメント付き重複防止版）
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

# 環境変数の取得
DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_POLITICS')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
POLITICAL_SCORE_THRESHOLD = int(os.environ.get('POLITICAL_SCORE_THRESHOLD', '70'))
MAX_NEWS_TO_POST = int(os.environ.get('MAX_NEWS_TO_POST', '10'))

# 投稿履歴ファイルのパス
HISTORY_FILE = 'posted_news_history.json'
HISTORY_RETENTION_HOURS = 24  # 24時間以内の重複をチェック

# Gemini API設定
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-3-flash-preview')

# 政治関連キーワード
POLITICAL_KEYWORDS = [
    '自民', '国民民主', '参政', '維新', '立憲', '共産', '公明', '社民',
    '高市', '麻生', '片山', '小野田', '茂木', '鈴木俊一', '岸田', '河野', '石破',
    '首相', '総理', '大臣', '官房長官', '財務大臣', '外相', '防衛相',
    '増税', '減税', '防衛費', '社会保障', '財源', '憲法改正',
    '国会', '予算委員会', '党首討論', '選挙', '内閣改造', '政治資金',
    '日米', '日中', '日韓', 'トランプ', 'プーチン', '習近平',
    # 追加した時事・国際情勢ワード
    'レアアース', '石油', '原油', '戦争', 'イラン', 'エプスタイン'
]

# 除外キーワード
EXCLUDE_KEYWORDS = [
    'プロレス', '新日本プロレス', 'サッカー', '野球', 'バスケ',
    '映画', 'ドラマ', 'アイドル', '鈴木みのる'
]

# RSSフィード
NEWS_FEEDS = {
    '日経新聞・速報': 'https://assets.wor.jp/rss/rdf/nikkei/news.rdf',
    'ロイター通信・速報': 'https://assets.wor.jp/rss/rdf/reuters/top.rdf',
    'Yahoo!ニュース': 'https://news.yahoo.co.jp/rss/topics/top-picks.xml'
}

def generate_news_hash(title, link):
    """
    ニュースの一意な識別子を生成（タイトル + URLのハッシュ値）
    """
    normalized_title = re.sub(r'\s+', ' ', title.strip())
    normalized_title = re.sub(r'[【】『』「」\[\]()（）]', '', normalized_title)
    
    content = f"{normalized_title}|{link}"
    return hashlib.md5(content.encode('utf-8')).hexdigest()

def load_posted_history():
    """
    過去の投稿履歴を読み込む
    """
    if not os.path.exists(HISTORY_FILE):
        return {}
    
    try:
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            history = json.load(f)
        
        cutoff_time = datetime.now() - timedelta(hours=HISTORY_RETENTION_HOURS)
        cutoff_timestamp = cutoff_time.timestamp()
        
        cleaned_history = {
            hash_id: timestamp 
            for hash_id, timestamp in history.items() 
            if timestamp > cutoff_timestamp
        }
        
        if len(cleaned_history) < len(history):
            save_posted_history(cleaned_history)
            print(f"📝 履歴クリーンアップ: {len(history)} → {len(cleaned_history)}件")
        
        return cleaned_history
    
    except Exception as e:
        print(f"⚠️ 履歴読み込みエラー: {e}")
        return {}

def save_posted_history(history):
    """
    投稿履歴を保存
    """
    try:
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ 履歴保存エラー: {e}")

def is_duplicate(title, link, posted_history):
    """
    重複チェック
    """
    news_hash = generate_news_hash(title, link)
    return news_hash in posted_history

def mark_as_posted(title, link, posted_history):
    """
    投稿済みとしてマーク
    """
    news_hash = generate_news_hash(title, link)
    posted_history[news_hash] = datetime.now().timestamp()

def check_political_relevance(title, description):
    """政治関連度を判定（Gemini API）"""
    if not GEMINI_API_KEY:
        return 0
    
    try:
        prompt = f"""
以下のニュースが日本の政治や国際情勢にどれだけ関連しているか、0〜100点で評価してください。
数字のみで回答してください。

タイトル: {title}
説明: {description}
"""
        response = model.generate_content(prompt)
        score_text = response.text.strip()
        score_match = re.search(r'\d+', score_text)
        if score_match:
            return min(100, max(0, int(score_match.group())))
        return 0
    except Exception as e:
        print(f"⚠️ Gemini APIエラー: {e}")
        return 0

def generate_ai_comment(title, description):
    """
    AIコメントを生成：記事から日本・世界の動向を予測
    """
    if not GEMINI_API_KEY:
        return None
    
    try:
        prompt = f"""
以下のニュースを分析し、この出来事が今後の日本や世界にどのような影響を及ぼすか予測してください。

【ニュース】
タイトル: {title}
内容: {description}

以下の形式で簡潔に回答してください（各項目2-3行程度）：

🇯🇵 日本への影響:
（日本の政治・経済・社会への具体的な影響を予測）

🌏 世界への影響:
（国際関係や世界情勢への影響を予測）

📊 注目ポイント:
（今後注視すべき点や展開の可能性）
"""
        
        response = model.generate_content(prompt)
        ai_comment = response.text.strip()
        
        if ai_comment and len(ai_comment) > 20:
            return ai_comment
        else:
            return None
    
    except Exception as e:
        print(f"  ⚠️ AIコメント生成エラー: {e}")
        return None

def create_discord_message(news_item, ai_comment=None):
    """
    Discord投稿用のメッセージを作成（AIコメント付き）
    """
    from datetime import datetime, timezone, timedelta
    
    title = news_item.get('title', 'タイトルなし')
    link = news_item.get('link', '')
    source = news_item.get('source', '不明')
    score = news_item.get('score', 0)
    
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
    
    jst = timezone(timedelta(hours=9))
    now = datetime.now(jst)
    time_str = now.strftime('%H:%M')
    
    content = f"🏛️ **【政治・時事】{title}**\n"
    content += f"━━━━━━━━━━━━━━━━━━\n"
    content += f"📰 **出典**: {source}\n"
    content += f"🎯 **関連度**: {score}点 {stars}\n"
    content += f"⏰ **取得時刻**: {time_str}\n"
    content += f"🔗 {link}\n"
    
    if ai_comment:
        content += "\n" + "━━━━━━━━━━━━━━━━━━\n"
        content += "🤖 **AIによる動向予測**\n\n"
        content += ai_comment
        content += "\n"
    
    return {'content': content}

def main():
    print("=" * 60)
    print("🏛️ 政治ニュース自動収集Bot（AIコメント付き）")
    print("=" * 60)
    print(f"実行時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    if not DISCORD_WEBHOOK_URL:
        print("❌ DISCORD_WEBHOOK_POLITICS が設定されていません")
        sys.exit(1)
    
    if not GEMINI_API_KEY:
        print("❌ GEMINI_API_KEY が設定されていません")
        sys.exit(1)
    
    posted_history = load_posted_history()
    print(f"📚 投稿履歴: {len(posted_history)}件\n")
    
    all_entries = []
    for source_name, feed_url in NEWS_FEEDS.items():
        print(f"📡 {source_name} から取得中...")
        try:
            feed = feedparser.parse(
                feed_url,
                agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
            
            print(f"  📊 status={getattr(feed, 'status', 'N/A')}, entries={len(feed.entries)}")
            
            for entry in feed.entries[:20]:
                title = entry.get('title', '')
                description = entry.get('description', '') or entry.get('summary', '')
                link = entry.get('link', '')
                
                if title and link:
                    all_entries.append({
                        'title': title,
                        'description': description,
                        'link': link,
                        'source': source_name
                    })
            print(f"  ✅ {len(feed.entries[:20])}件取得")
        except Exception as e:
            print(f"  ❌ エラー: {e}")
    
    print(f"\n合計: {len(all_entries)}件のニュースを取得")
    
    new_entries = []
    duplicate_count = 0
    for entry in all_entries:
        if is_duplicate(entry['title'], entry['link'], posted_history):
            duplicate_count += 1
            print(f"  ⏩ スキップ（重複）: {entry['title'][:40]}...")
        else:
            new_entries.append(entry)
    
    print(f"🔍 重複チェック: {duplicate_count}件スキップ, {len(new_entries)}件が新規")
    
    keyword_matched = []
    for entry in new_entries:
        combined = f"{entry['title']} {entry['description']}"
        if any(kw in combined for kw in POLITICAL_KEYWORDS):
            if not any(ex in combined for ex in EXCLUDE_KEYWORDS):
                keyword_matched.append(entry)
    
    print(f"✅ キーワードマッチ: {len(keyword_matched)}件")
    
    political_news = []
    # 候補を10件から20件に拡張
    for entry in keyword_matched[:20]:
        score = check_political_relevance(entry['title'], entry['description'])
        entry['score'] = score
        
        if score >= POLITICAL_SCORE_THRESHOLD:
            political_news.append(entry)
            print(f"  ✅ [{score}点] {entry['title']}")
        else:
            print(f"  ❌ [{score}点] {entry['title']}")
        
        time.sleep(3)
    
    print(f"\n✅ 最終結果: {len(political_news)}件")
    
    if not political_news:
        print("\n📭 投稿するニュースがありません")
        return
    
    posted = 0
    for news in political_news[:MAX_NEWS_TO_POST]:
        print(f"\n━━━━━━━━━━━━━━━━━━")
        print(f"処理中: {news['title']}")
        
        ai_comment = generate_ai_comment(news['title'], news['description'])
        
        if ai_comment:
            print(f"  ✅ AIコメント生成完了")
        else:
            print(f"  ⚠️ AIコメント生成失敗")
        
        time.sleep(3)
        
        message = create_discord_message(news, ai_comment)
        
        try:
            requests.post(DISCORD_WEBHOOK_URL, json=message, timeout=10)
            
            mark_as_posted(news['title'], news['link'], posted_history)
            posted += 1
            print(f"  ✅ Discord投稿成功")
            time.sleep(2)
        except Exception as e:
            print(f"  ❌ 投稿エラー: {e}")
    
    save_posted_history(posted_history)
    
    print(f"\n━━━━━━━━━━━━━━━━━━")
    print(f"✅ 完了: {posted}件を投稿しました")
    print(f"📚 現在の履歴件数: {len(posted_history)}件")

if __name__ == "__main__":
    main()
