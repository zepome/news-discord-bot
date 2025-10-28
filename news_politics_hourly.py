#!/usr/bin/env python3
"""
政治ニュース自動収集Bot（世論分析機能付き）
毎時、複数のRSSフィードから政治関連ニュースを取得し、Discordに投稿
Yahoo!ニュースのコメントを分析して世論の傾向も表示
"""

import os
import sys
import re
import time
from datetime import datetime
from typing import List, Dict, Optional
import feedparser
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai

# 環境変数の取得
DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_POLITICS')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

# Gemini API設定
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')

# 政治関連キーワード（3段階フィルタリング用）
POLITICAL_KEYWORDS = [
    # 政党
    '自民', '国民民主', '参政', '維新', '立憲', '共産', '公明', '社民', '令和', 'れいわ',
    # 政治家
    '高市', '麻生', '片山', '小野田', '茂木', '鈴木俊一', '尾崎', '石原', '安倍晋三', '三日月',
    '岸田', '河野', '石破', '小泉', '野田', '枝野', '志位', '玉木', '馬場',
    # 役職
    '首相', '総理', '大臣', '官房長官', '財務大臣', '外相', '防衛相', '農水相', '環境相',
    '厚労相', '文科相', '経産相', '国交相', '総務相', '法相', '内閣府',
    # 政策・制度
    '増税', '減税', '防衛費', '社会保障', '財源', '憲法改正', '安全保障', '関税', '貿易',
    '少子化対策', '年金改革', '控除', '給付金', '補助金', '予算', '税制',
    # イベント・制度
    '国会', '予算委員会', '党首討論', '選挙', '内閣改造', '解散', '不信任', '政治資金',
    '政治献金', '支持率', '衆院選', '参院選', '補選', '地方選',
    # 国際政治
    '日米', '日中', '日韓', '米中', '米露', '米ロ', 'G7', 'G20', '国連', 'ASEAN',
    '会談', '首脳', 'サミット', 'トランプ', 'プーチン', '習近平', 'バイデン'
]

# 除外キーワード（スポーツ・芸能等）
EXCLUDE_KEYWORDS = [
    # スポーツ
    'プロレス', '新日本プロレス', 'サッカー', '野球', 'バスケ', 'テニス', 'ゴルフ',
    '格闘技', 'ボクシング', 'レスリング', '五輪', 'オリンピック', 'W杯',
    # 芸能
    '映画', 'ドラマ', 'アイドル', '俳優', '女優', 'タレント', 'ミュージシャン',
    '歌手', 'バンド', 'アニメ', 'ゲーム',
    # その他
    '鈴木みのる', '鈴木軍'  # 誤検出対策
]

# RSSフィードのURL
NEWS_FEEDS = {
    '日本経済新聞': 'https://www.nikkei.com/rss/',
    '読売新聞': 'https://www.yomiuri.co.jp/rss/l-news.xml',
    '朝日新聞': 'https://www.asahi.com/rss/asahi/newsheadlines.rdf',
    '毎日新聞': 'https://mainichi.jp/rss/etc/mainichi-flash.rss',
    'NHK': 'https://www.nhk.or.jp/rss/news/cat0.xml',
    'BBC News': 'https://feeds.bbci.co.uk/news/world/rss.xml',
    'Reuters': 'https://www.reutersagency.com/feed/?taxonomy=best-topics&post_type=best',
    'CNN': 'http://rss.cnn.com/rss/edition_world.rss'
}


def check_political_relevance(title: str, description: str) -> int:
    """
    Gemini APIを使用してニュースの政治関連度を判定
    
    Args:
        title: ニュースのタイトル
        description: ニュースの説明文
    
    Returns:
        政治関連度スコア（0-100点）
    """
    if not GEMINI_API_KEY:
        return 0
    
    try:
        prompt = f"""
以下のニュースが「日本の政治」にどれだけ関連しているか、0〜100点で評価してください。

評価基準：
- 90-100点: 日本の政治・政策の中核的な話題（選挙、国会、内閣、法案、政治家の重要発言等）
- 70-89点: 日本の政治に直接関係する話題（政府の政策決定、政治資金、支持率等）
- 50-69点: 政治と関連があるが間接的（経済政策の影響、国際関係等）
- 30-49点: 政治的要素を含むが主題ではない
- 0-29点: 政治とほぼ無関係（スポーツ、芸能、一般ニュース等）

タイトル: {title}
説明: {description}

数字のみで回答してください（例: 85）
"""
        
        response = model.generate_content(prompt)
        score_text = response.text.strip()
        
        # 数字のみ抽出
        score_match = re.search(r'\d+', score_text)
        if score_match:
            score = int(score_match.group())
            return min(100, max(0, score))  # 0-100に制限
        
        return 0
    
    except Exception as e:
        print(f"⚠️ Gemini API判定エラー: {e}")
        return 0


def filter_political_news(entries: List[Dict]) -> List[Dict]:
    """
    3段階フィルタリングで政治ニュースを抽出
    
    1. キーワードマッチ（高速）
    2. 除外ワードチェック（誤検出除去）
    3. Gemini AI判定（精度向上）
    """
    print(f"\n📊 フィルタリング開始: {len(entries)}件")
    
    # ステップ1: キーワードマッチ
    keyword_matched = []
    for entry in entries:
        title = entry.get('title', '')
        description = entry.get('description', '')
        combined = f"{title} {description}"
        
        if any(keyword in combined for keyword in POLITICAL_KEYWORDS):
            keyword_matched.append(entry)
    
    print(f"✅ キーワードマッチ: {len(keyword_matched)}件")
    
    # ステップ2: 除外ワードチェック
    exclude_filtered = []
    for entry in keyword_matched:
        title = entry.get('title', '')
        description = entry.get('description', '')
        combined = f"{title} {description}"
        
        if not any(exclude in combined for exclude in EXCLUDE_KEYWORDS):
            exclude_filtered.append(entry)
    
    print(f"✅ 除外ワード後: {len(exclude_filtered)}件")
    
    # ステップ3: Gemini AI判定
    political_news = []
    for entry in exclude_filtered:
        title = entry.get('title', '')
        description = entry.get('description', '')
        
        score = check_political_relevance(title, description)
        entry['political_score'] = score
        
        if score >= 70:  # 70点以上のみ通過
            political_news.append(entry)
            print(f"  ✅ [{score}点] {title}")
        else:
            print(f"  ❌ [{score}点] {title}")
        
        time.sleep(0.5)  # API制限対策
    
    print(f"✅ 最終結果: {len(political_news)}件\n")
    return political_news


def search_yahoo_news(title: str) -> Optional[str]:
    """
    Yahoo!ニュースでタイトル検索してURLを取得
    
    Args:
        title: 検索するニュースタイトル
    
    Returns:
        Yahoo!ニュースのURL（見つからない場合はNone）
    """
    try:
        search_url = f"https://news.yahoo.co.jp/search?p={requests.utils.quote(title)}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(search_url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'lxml')
        
        # 検索結果の最初のリンクを取得
        first_result = soup.select_one('a[href*="news.yahoo.co.jp/articles/"]')
        if first_result:
            return first_result['href']
        
        return None
    
    except Exception as e:
        print(f"⚠️ Yahoo!ニュース検索エラー: {e}")
        return None


def get_yahoo_comments(article_url: str, max_comments: int = 100) -> List[Dict]:
    """
    Yahoo!ニュースのコメントを取得
    
    Args:
        article_url: Yahoo!ニュース記事のURL
        max_comments: 取得する最大コメント数
    
    Returns:
        コメントのリスト
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(article_url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'lxml')
        
        comments = []
        comment_elements = soup.select('.comment-item')[:max_comments]
        
        for elem in comment_elements:
            text_elem = elem.select_one('.comment-text')
            likes_elem = elem.select_one('.likes-count')
            
            if text_elem:
                comment = {
                    'text': text_elem.get_text(strip=True),
                    'likes': int(likes_elem.get_text(strip=True)) if likes_elem else 0
                }
                comments.append(comment)
        
        return comments
    
    except Exception as e:
        print(f"⚠️ コメント取得エラー: {e}")
        return []


def analyze_sentiment(comments: List[Dict]) -> Dict:
    """
    Gemini APIでコメントの感情分析
    
    Args:
        comments: コメントのリスト
    
    Returns:
        分析結果
    """
    if not comments or not GEMINI_API_KEY:
        return None
    
    try:
        # 上位20件のコメントを分析対象にする
        top_comments = sorted(comments, key=lambda x: x['likes'], reverse=True)[:20]
        comments_text = "\n".join([f"- {c['text']}" for c in top_comments])
        
        prompt = f"""
以下のYahoo!ニュースコメントを分析してください。

【コメント一覧】
{comments_text}

以下の形式で回答してください：

1. 感情分布（%で表記）
賛成: XX%
反対: XX%
中立: XX%

2. 議論の熱量（0-100点）
XX点

3. 主要論点（3つ）
- 論点1
- 論点2
- 論点3

4. 代表的コメント（賛成・反対から各1つ）
【賛成】コメント内容
【反対】コメント内容

5. 全体的傾向（1-2文）
"""
        
        response = model.generate_content(prompt)
        analysis_text = response.text.strip()
        
        # 結果をパース
        result = {'raw_analysis': analysis_text}
        
        # 感情分布の抽出
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
        
        return result
    
    except Exception as e:
        print(f"⚠️ 感情分析エラー: {e}")
        return None


def create_discord_message(news_item: Dict, sentiment_analysis: Optional[Dict]) -> Dict:
    """
    Discord投稿用のメッセージを作成
    
    Args:
        news_item: ニュース項目
        sentiment_analysis: 世論分析結果
    
    Returns:
        Discordメッセージ
    """
    title = news_item.get('title', 'タイトルなし')
    link = news_item.get('link', '')
    source = news_item.get('source', '不明')
    score = news_item.get('political_score', 0)
    
    # 基本メッセージ
    content = f"**【政治ニュース】{title}**\n"
    content += f"📰 出典: {source}\n"
    content += f"🎯 関連度: {score}点\n"
    content += f"🔗 {link}\n"
    
    # 世論分析が利用可能な場合
    if sentiment_analysis:
        content += "\n" + "="*50 + "\n"
        content += "**📊 世論分析**\n\n"
        content += sentiment_analysis.get('raw_analysis', '分析結果なし')
    
    return {'content': content}


def send_to_discord(message: Dict) -> bool:
    """
    Discordに投稿
    
    Args:
        message: 投稿メッセージ
    
    Returns:
        成功した場合True
    """
    if not DISCORD_WEBHOOK_URL:
        print("❌ Discord Webhook URLが設定されていません")
        return False
    
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=message, timeout=10)
        response.raise_for_status()
        return True
    
    except Exception as e:
        print(f"❌ Discord投稿エラー: {e}")
        return False


def main():
    """メイン処理"""
    print("=" * 60)
    print("🏛️ 政治ニュース自動収集Bot（世論分析機能付き）")
    print("=" * 60)
    print(f"実行時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # 環境変数チェック
    if not DISCORD_WEBHOOK_URL:
        print("❌ DISCORD_WEBHOOK_POLITICS が設定されていません")
        sys.exit(1)
    
    if not GEMINI_API_KEY:
        print("❌ GEMINI_API_KEY が設定されていません")
        sys.exit(1)
    
   # 全フィードからニュースを取得
    all_entries = []
    for source_name, feed_url in NEWS_FEEDS.items():
        print(f"📡 {source_name} から取得中...")
        try:
            # User-Agentを設定してブラウザとして認識させる
            feed = feedparser.parse(
                feed_url,
                agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            
            # デバッグ情報を追加
            print(f"  📊 フィード情報: status={getattr(feed, 'status', 'N/A')}, version={getattr(feed, 'version', 'N/A')}")
            print(f"  📊 エントリ数: {len(feed.entries)}")
            
            # エラーチェック
            if hasattr(feed, 'bozo') and feed.bozo:
                print(f"  ⚠️ フィード解析エラー: {feed.bozo_exception}")
            
            # エントリが0件の場合の詳細情報
            if len(feed.entries) == 0:
                print(f"  ⚠️ エントリが取得できませんでした")
                print(f"  📊 フィードURL: {feed_url}")
                if hasattr(feed, 'headers'):
                    print(f"  📊 レスポンスヘッダー: {feed.headers}")
            
            for entry in feed.entries[:20]:  # 各ソース最大20件
                title = entry.get('title', '')
                description = entry.get('description', '') or entry.get('summary', '')
                
                if title:  # タイトルがある場合のみ追加
                    all_entries.append({
                        'title': title,
                        'description': description,
                        'link': entry.get('link', ''),
                        'source': source_name
                    })
            print(f"  ✅ {len(feed.entries[:20])}件取得")
        except Exception as e:
            print(f"  ❌ エラー: {type(e).__name__}: {e}")
            import traceback
            print(f"  📊 詳細: {traceback.format_exc()}")
    
    # 政治ニュースをフィルタリング
    political_news = filter_political_news(all_entries)
    
    if not political_news:
        print("\n政治関連ニュースが見つかりませんでした")
        return
    
    # 各ニュースを処理
    posted_count = 0
    for news in political_news[:5]:  # 上位5件のみ処理
        print(f"\n処理中: {news['title']}")
        
        # Yahoo!ニュース検索
        yahoo_url = search_yahoo_news(news['title'])
        
        # 世論分析
        sentiment_analysis = None
        if yahoo_url:
            print(f"  ✅ Yahoo!ニュース発見: {yahoo_url}")
            comments = get_yahoo_comments(yahoo_url, max_comments=100)
            
            if comments:
                print(f"  ✅ コメント取得: {len(comments)}件")
                sentiment_analysis = analyze_sentiment(comments)
                time.sleep(1)  # API制限対策
        
        # Discord投稿
        message = create_discord_message(news, sentiment_analysis)
        if send_to_discord(message):
            posted_count += 1
            print(f"  ✅ Discord投稿成功")
            time.sleep(2)  # Webhook制限対策
        else:
            print(f"  ❌ Discord投稿失敗")
    
    print("\n" + "=" * 60)
    print(f"✅ 完了: {posted_count}件のニュースを投稿しました")
    print("=" * 60)


if __name__ == "__main__":
    main()
