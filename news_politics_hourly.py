#!/usr/bin/env python3
"""
政治ニュース自動収集Bot（基本版）
"""

import os
import sys
import re
import time
from datetime import datetime
import feedparser
import requests
import google.generativeai as genai

# 環境変数の取得
DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_POLITICS')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
POLITICAL_SCORE_THRESHOLD = int(os.environ.get('POLITICAL_SCORE_THRESHOLD', '60'))
MAX_NEWS_TO_POST = int(os.environ.get('MAX_NEWS_TO_POST', '3'))


# Gemini API設定
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash')

# 政治関連キーワード
POLITICAL_KEYWORDS = [
    '自民', '国民民主', '参政', '維新', '立憲', '共産', '公明', '社民',
    '高市', '麻生', '片山', '小野田', '茂木', '鈴木俊一', '岸田', '河野', '石破',
    '首相', '総理', '大臣', '官房長官', '財務大臣', '外相', '防衛相',
    '増税', '減税', '防衛費', '社会保障', '財源', '憲法改正',
    '国会', '予算委員会', '党首討論', '選挙', '内閣改造', '政治資金',
    '日米', '日中', '日韓', 'トランプ', 'プーチン', '習近平'
]

# 除外キーワード
EXCLUDE_KEYWORDS = [
    'プロレス', '新日本プロレス', 'サッカー', '野球', 'バスケ',
    '映画', 'ドラマ', 'アイドル', '鈴木みのる'
]

# RSSフィード
NEWS_FEEDS = {
    '日経新聞・速報': 'https://assets.wor.jp/rss/rdf/nikkei/news.rdf',
    '日経新聞・政治経済': 'https://assets.wor.jp/rss/rdf/nikkei/economy.rdf',
    '47NEWS・地域速報': 'https://assets.wor.jp/rss/rdf/ynlocalnews/news.rdf',
    'Bloomberg・トップ': 'https://assets.wor.jp/rss/rdf/bloomberg/top.rdf',
    'Yahoo!ニュース': 'https://news.yahoo.co.jp/rss/topics/top-picks.xml',
    '時事ドットコム': 'https://www.jiji.com/rss/ranking.rdf',
    'ロイター日本語': 'https://jp.reuters.com/rssFeed/topNews',
    '共同通信': 'https://www.47news.jp/rss/national.xml',
    'BBC News Japan': 'https://feeds.bbci.co.uk/news/world/asia/rss.xml',
    'CNN Top Stories': 'http://rss.cnn.com/rss/edition_world.rss'
}

def check_political_relevance(title, description):
    """政治関連度を判定（Gemini API）"""
    if not GEMINI_API_KEY:
        return 0
    
    try:
        prompt = f"""
以下のニュースが日本の政治にどれだけ関連しているか、0〜100点で評価してください。
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

def create_discord_message(news_item, sentiment_analysis=None):
    """
    Discord投稿用のメッセージを作成（改良版）
    """
    from datetime import datetime, timezone, timedelta
    
    title = news_item.get('title', 'タイトルなし')
    link = news_item.get('link', '')
    source = news_item.get('source', '不明')
    score = news_item.get('score', 0)
    
    # スコアに応じた星評価
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
    
    # 現在時刻（日本時間）
    jst = timezone(timedelta(hours=9))
    now = datetime.now(jst)
    time_str = now.strftime('%H:%M')
    
    # メッセージ作成
    content = f"🏛️ **【政治】{title}**\n"
    content += f"━━━━━━━━━━━━━━━━━━\n"
    content += f"📰 **出典**: {source}\n"
    content += f"🎯 **関連度**: {score}点 {stars}\n"
    content += f"⏰ **取得時刻**: {time_str}\n"
    content += f"🔗 {link}\n"
    
    # 世論分析がある場合（将来の拡張用）
    if sentiment_analysis:
        content += "\n" + "━━━━━━━━━━━━━━━━━━\n"
        content += "📊 **世論分析**\n\n"
        content += sentiment_analysis.get('raw_analysis', '分析結果なし')
    
    return {'content': content}

def main():
    print("=" * 60)
    print("🏛️ 政治ニュース自動収集Bot")
    print("=" * 60)
    print(f"実行時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    if not DISCORD_WEBHOOK_URL:
        print("❌ DISCORD_WEBHOOK_POLITICS が設定されていません")
        sys.exit(1)
    
    if not GEMINI_API_KEY:
        print("❌ GEMINI_API_KEY が設定されていません")
        sys.exit(1)
    
    # ニュース取得
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
                
                if title:
                    all_entries.append({
                        'title': title,
                        'description': description,
                        'link': entry.get('link', ''),
                        'source': source_name
                    })
            print(f"  ✅ {len(feed.entries[:20])}件取得")
        except Exception as e:
            print(f"  ❌ エラー: {e}")
    
    print(f"\n合計: {len(all_entries)}件のニュースを取得")
    
    # キーワードフィルタリング
    keyword_matched = []
    for entry in all_entries:
        combined = f"{entry['title']} {entry['description']}"
        if any(kw in combined for kw in POLITICAL_KEYWORDS):
            if not any(ex in combined for ex in EXCLUDE_KEYWORDS):
                keyword_matched.append(entry)
    
    print(f"✅ キーワードマッチ: {len(keyword_matched)}件")
    
    # Gemini判定
    political_news = []
    for entry in keyword_matched[:10]:  # 最大10件チェック
        score = check_political_relevance(entry['title'], entry['description'])
        entry['score'] = score
        
        if score >= POLITICAL_SCORE_THRESHOLD:
            political_news.append(entry)
            print(f"  ✅ [{score}点] {entry['title']}")
        else:
            print(f"  ❌ [{score}点] {entry['title']}")
        
        time.sleep(0.5)
    
    print(f"\n✅ 最終結果: {len(political_news)}件")
    
    # Discord投稿
    if not political_news:
        message = {'content': '📭 政治関連ニュースはありませんでした'}
        requests.post(DISCORD_WEBHOOK_URL, json=message)
        print("\n政治関連ニュースが見つかりませんでした")
        return
    
    posted = 0
    for news in political_news[:MAX_NEWS_TO_POST]:
        # メッセージ作成（改良版フォーマット）
        message = create_discord_message(news)
        
        try:
            requests.post(DISCORD_WEBHOOK_URL, json=message, timeout=10)

            posted += 1
            print(f"✅ Discord投稿: {news['title']}")
            time.sleep(2)
        except Exception as e:
            print(f"❌ 投稿エラー: {e}")
    
    print(f"\n✅ 完了: {posted}件を投稿しました")

if __name__ == "__main__":
    main()
