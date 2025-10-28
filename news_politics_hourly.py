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
    'ロイター日本語': 'https://jp.reuters.com/rssFeed/topNews',
    'Yahoo!ニュース': 'https://news.yahoo.co.jp/rss/topics/top-picks.xml'
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
    
    # 世論分析がある場合
    if sentiment_analysis:
        content += "\n" + "━━━━━━━━━━━━━━━━━━\n"
        content += "📊 **世論分析**\n"
        content += sentiment_analysis.get('formatted_analysis', '分析結果なし')
    
    return {'content': content}
def search_yahoo_news(title):
    """
    Yahoo!ニュースでタイトル検索してURLを取得
    """
    try:
        import urllib.parse
        search_url = f"https://news.yahoo.co.jp/search?p={urllib.parse.quote(title)}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(search_url, headers=headers, timeout=10)
        response.raise_for_status()
        
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # 検索結果の最初のリンクを取得
        first_result = soup.select_one('a[href*="news.yahoo.co.jp/articles/"]')
        if first_result:
            return first_result['href']
        
        return None
    
    except Exception as e:
        print(f"  ⚠️ Yahoo!ニュース検索エラー: {e}")
        return None


def get_yahoo_comments(article_url, max_comments=100):
    """
    Yahoo!ニュースのコメントを取得
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(article_url, headers=headers, timeout=10)
        response.raise_for_status()
        
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(response.content, 'html.parser')
        
        comments = []
        
        # Yahoo!ニュースのコメント構造に対応
        comment_elements = soup.select('.comment')[:max_comments]
        
        for elem in comment_elements:
            text_elem = elem.select_one('.commentText')
            if text_elem:
                comment_text = text_elem.get_text(strip=True)
                if comment_text:
                    comments.append({'text': comment_text})
        
        # コメントが取得できない場合の代替方法
        if not comments:
            # 別の構造を試す
            alt_comments = soup.select('div[class*="comment"]')[:max_comments]
            for elem in alt_comments:
                text = elem.get_text(strip=True)
                if text and len(text) > 10:
                    comments.append({'text': text})
        
        return comments[:max_comments]
    
    except Exception as e:
        print(f"  ⚠️ コメント取得エラー: {e}")
        return []


def analyze_sentiment(comments):
    """
    Gemini APIでコメントの感情分析
    """
    if not comments or not GEMINI_API_KEY:
        return None
    
    try:
        # 上位20件のコメントを分析対象にする
        top_comments = comments[:20]
        comments_text = "\n".join([f"- {c['text']}" for c in top_comments])
        
        prompt = f"""
以下のYahoo!ニュースコメントを分析してください。

【コメント一覧】
{comments_text}

以下の形式で回答してください：

感情分布:
賛成: XX%
反対: XX%
中立: XX%

議論の熱量: XX点

主要論点:
• 論点1
• 論点2
"""
        
        response = model.generate_content(prompt)
        analysis_text = response.text.strip()
        
        # 感情分布の抽出
        result = {'raw_text': analysis_text}
        
        agree_match = re.search(r'賛成[：:]\s*(\d+)%', analysis_text)
        oppose_match = re.search(r'反対[：:]\s*(\d+)%', analysis_text)
        neutral_match = re.search(r'中立[：:]\s*(\d+)%', analysis_text)
        
        if agree_match and oppose_match and neutral_match:
            result['sentiment'] = {
                'agree': int(agree_match.group(1)),
                'oppose': int(oppose_match.group(1)),
                'neutral': int(neutral_match.group(1))
            }
        
        # 熱量スコアの抽出
        heat_match = re.search(r'(\d+)点', analysis_text)
        if heat_match:
            result['heat_score'] = int(heat_match.group(1))
        
        # フォーマット化された分析結果を作成
        formatted = "\n💭 **感情分布**\n"
        if 'sentiment' in result:
            s = result['sentiment']
            formatted += f"   賛成: {s['agree']}% | 反対: {s['oppose']}% | 中立: {s['neutral']}%\n\n"
        
        formatted += "🔥 **議論の熱量**: "
        if 'heat_score' in result:
            formatted += f"{result['heat_score']}点\n\n"
        else:
            formatted += "不明\n\n"
        
        # 主要論点の抽出
        formatted += "📌 **主要論点**\n"
        points = re.findall(r'[•・]\s*(.+)', analysis_text)
        if points:
            for point in points[:3]:  # 最大3つ
                formatted += f"   • {point.strip()}\n"
        else:
            formatted += "   • 分析データ不足\n"
        
        result['formatted_analysis'] = formatted
        
        return result
    
    except Exception as e:
        print(f"  ⚠️ 感情分析エラー: {e}")
        return None
        
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
        print(f"\n処理中: {news['title']}")
        
        # Yahoo!ニュース検索
        sentiment_analysis = None
        yahoo_url = search_yahoo_news(news['title'])
        
        if yahoo_url:
            print(f"  ✅ Yahoo!ニュース発見: {yahoo_url}")
            comments = get_yahoo_comments(yahoo_url, max_comments=100)
            
            if comments:
                print(f"  ✅ コメント取得: {len(comments)}件")
                sentiment_analysis = analyze_sentiment(comments)
                if sentiment_analysis:
                    print(f"  ✅ 感情分析完了")
                time.sleep(1)  # API制限対策
            else:
                print(f"  ⚠️ コメント取得失敗")
        else:
            print(f"  ⚠️ Yahoo!ニュースが見つかりませんでした")
        
        # メッセージ作成（世論分析付き）
        message = create_discord_message(news, sentiment_analysis)
        
        try:
            requests.post(DISCORD_WEBHOOK_URL, json=message, timeout=10)
            posted += 1
            print(f"  ✅ Discord投稿成功")
            time.sleep(2)
        except Exception as e:
            print(f"  ❌ 投稿エラー: {e}")
    
    print(f"\n✅ 完了: {posted}件を投稿しました")

if __name__ == "__main__":
    main()
