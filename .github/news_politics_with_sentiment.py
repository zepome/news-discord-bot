#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
国内政治ニュース + 世論分析システム
Gemini APIによる高精度フィルタリング + Yahoo!ニュースコメント分析
"""

import os
import sys
import re
import requests
import json
import time
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import feedparser
from bs4 import BeautifulSoup
from urllib.parse import quote

# 環境変数から取得
DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_POLITICS')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

# 追跡キーワード
POLITICAL_KEYWORDS = [
    # 政党
    '自民党', '自民', '国民民主党', '国民民主', '参政党', '日本維新の会', '維新',
    
    # 政治家
    '高市早苗', '高市経済安保相', '高市大臣',
    '麻生太郎', '麻生副総裁',
    '片山さつき', '小野田紀美',
    '茂木敏充', '茂木幹事長',
    '鈴木俊一', '鈴木財務大臣', '鈴木財務相',
    '尾崎正直', '石原伸晃', '石原宏高',
    '安倍晋三', '三日月大造', '三日月知事',
    
    # 役職
    '首相', '総理大臣', '官房長官', '財務大臣', '外務大臣', '外相', 
    '農林水産大臣', '農水相', '環境大臣', '環境相', '防衛大臣', '防衛相',
    
    # 政治プロセス
    '国会', '臨時国会', '通常国会', '特別国会',
    '予算委員会', '本会議', '委員会質疑',
    '党首討論', '代表質問',
    '閣議決定', '閣議了解',
    '法案提出', '法案可決', '法案成立',
    '施政方針演説', '所信表明演説',
    
    # 政策
    '増税', '減税', '税制改正', '消費税', '所得税',
    '防衛費', '防衛予算', '防衛力強化',
    '社会保障', '年金制度', '年金改革',
    '財源', '予算案', '補正予算',
    '憲法改正', '安全保障',
    '関税', '貿易協定',
    '少子化対策', '子育て支援',
    '配偶者控除', '扶養控除', '住宅ローン控除',
    
    # 政治イベント
    '衆議院選挙', '参議院選挙', '統一地方選',
    '総裁選', '代表選', '党首選',
    '内閣改造', '組閣',
    '解散', '不信任案', '不信任決議',
    '政治資金', '政治献金', '政治とカネ',
    '内閣支持率', '政党支持率', '世論調査',
    
    # 国際政治
    '日米首脳会談', '日中首脳会談', '日韓首脳会談',
    '日米同盟', '日米安全保障',
    'G7サミット', 'G20サミット',
    '国連総会', '国連安保理',
    'ASEAN首脳会議',
    'トランプ大統領', 'プーチン大統領', '習近平国家主席',
]

# 除外キーワード
EXCLUDE_KEYWORDS = [
    'プロレス', '新日本プロレス', 'WWE', 'NJPW', 'DDT',
    'レスラー', '試合', 'チャンピオン', 'タイトルマッチ', 'リング',
    'サッカー', 'Jリーグ', 'ワールドカップ', 'プレミアリーグ',
    '野球', 'プロ野球', 'NPB', 'メジャーリーグ', 'MLB',
    'バスケ', 'NBA', 'Bリーグ',
    'テニス', 'ゴルフ', 'ボクシング', '格闘技', 'UFC',
    '芸能', 'アイドル', 'ジャニーズ', 'AKB',
    '映画', 'ドラマ', 'アニメ', '声優',
    '俳優', '女優', 'タレント', 'お笑い',
    '新製品', '新商品', 'キャンペーン', 'セール',
    'ゲーム', 'アプリ', 'スマホ',
]

# メディアのRSSフィード設定
NEWS_FEEDS = {
    '日経新聞': {'url': 'https://www.nikkei.com/rss/', 'language': '日本語'},
    'ロイター通信': {'url': 'https://jp.reuters.com/rssFeed/topNews', 'language': '日本語'},
    '東洋経済オンライン': {'url': 'https://toyokeizai.net/list/feed/rss', 'language': '日本語'},
    'PRタイムス': {'url': 'https://prtimes.jp/main/rss/', 'language': '日本語'},
    '時事ドットコム': {'url': 'https://www.jiji.com/rss/atom.xml', 'language': '日本語'},
    'Bloomberg': {'url': 'https://feeds.bloomberg.com/markets/news.rss', 'language': 'English'},
    'FXStreet': {'url': 'https://www.fxstreet.com/rss/news', 'language': 'English'},
    'Reuters (英語版)': {'url': 'https://www.reutersagency.com/feed/?taxonomy=best-topics&post_type=best', 'language': 'English'},
}

class YahooNewsCommentAnalyzer:
    """Yahoo!ニュースのコメント分析クラス"""
    
    def __init__(self, gemini_api_key: str):
        self.api_key = gemini_api_key
        self.api_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
    
    def search_yahoo_news(self, title: str) -> Optional[str]:
        """Yahoo!ニュースで記事を検索してURLを取得"""
        try:
            # Yahoo!ニュース検索
            search_query = quote(title[:50])
            search_url = f"https://news.yahoo.co.jp/search?p={search_query}"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(search_url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                # 最初の検索結果のリンクを取得
                article_link = soup.select_one('a.newsFeed_item_link')
                if article_link and article_link.get('href'):
                    yahoo_url = article_link['href']
                    print(f"  📰 Yahoo!ニュース記事発見: {yahoo_url}")
                    return yahoo_url
            
            print(f"  ⚠️ Yahoo!ニュースに該当記事なし")
            return None
            
        except Exception as e:
            print(f"  ⚠️ Yahoo!検索エラー: {e}")
            return None
    
    def get_yahoo_comments(self, article_url: str, max_comments: int = 100) -> List[Dict]:
        """Yahoo!ニュースのコメントを取得"""
        try:
            # Yahoo!ニュースのコメントAPIを使用
            # 注意: この部分は実際のYahoo! APIの仕様に合わせて調整が必要
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(article_url, headers=headers, timeout=10)
            
            if response.status_code != 200:
                print(f"  ⚠️ コメント取得失敗: {response.status_code}")
                return []
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # コメントを取得（実際の構造に合わせて調整）
            comments = []
            comment_elements = soup.select('.comment')[:max_comments]
            
            for elem in comment_elements:
                comment_text = elem.get_text(strip=True)
                if comment_text:
                    comments.append({
                        'text': comment_text,
                        'likes': 0  # いいね数も取得可能
                    })
            
            print(f"  💬 コメント取得: {len(comments)}件")
            return comments
            
        except Exception as e:
            print(f"  ⚠️ コメント取得エラー: {e}")
            return []
    
    def analyze_sentiment_with_gemini(self, title: str, comments: List[Dict]) -> Dict:
        """Gemini APIでコメントの感情分析"""
        if not comments:
            return self._empty_analysis()
        
        try:
            # コメントテキストを結合
            comments_text = "\n".join([f"- {c['text'][:200]}" for c in comments[:50]])
            
            prompt = f"""以下のニュース記事に対するコメント（Yahoo!ニュース）を分析してください。

【記事タイトル】
{title}

【コメント（50件）】
{comments_text}

以下の項目を分析して、JSON形式で回答してください：

{{
  "sentiment_ratio": {{
    "positive": 賛成・好意的な割合（0-100）,
    "negative": 反対・否定的な割合（0-100）,
    "neutral": 中立・その他の割合（0-100）
  }},
  "temperature_score": 議論の熱量スコア（0-100、100が最も熱い）,
  "main_opinions": [
    {{"stance": "positive", "opinion": "賛成派の主な意見"}},
    {{"stance": "negative", "opinion": "反対派の主な意見"}},
    {{"stance": "neutral", "opinion": "中立派の主な意見"}}
  ],
  "representative_comments": [
    {{"stance": "positive", "comment": "賛成派の代表的コメント"}},
    {{"stance": "negative", "comment": "反対派の代表的コメント"}},
    {{"stance": "neutral", "comment": "中立派の代表的コメント"}}
  ],
  "summary": "世論の全体的な傾向を1-2文で要約"
}}"""

            headers = {'Content-Type': 'application/json'}
            data = {
                "contents": [{
                    "parts": [{"text": prompt}]
                }]
            }
            
            response = requests.post(
                f"{self.api_url}?key={self.api_key}",
                headers=headers,
                json=data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                text_response = result['candidates'][0]['content']['parts'][0]['text']
                
                # JSONを抽出
                json_match = re.search(r'\{.*\}', text_response, re.DOTALL)
                if json_match:
                    analysis = json.loads(json_match.group())
                    print(f"  ✅ 世論分析完了")
                    return analysis
            
            print(f"  ⚠️ Gemini分析エラー: {response.status_code}")
            return self._empty_analysis()
            
        except Exception as e:
            print(f"  ⚠️ 世論分析エラー: {e}")
            return self._empty_analysis()
    
    def _empty_analysis(self) -> Dict:
        """空の分析結果"""
        return {
            "sentiment_ratio": {"positive": 0, "negative": 0, "neutral": 0},
            "temperature_score": 0,
            "main_opinions": [],
            "representative_comments": [],
            "summary": "コメント分析データなし"
        }

class GeminiPoliticalFilter:
    """Gemini APIを使った政治ニュースフィルタリングクラス"""
    
    def __init__(self):
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY環境変数が設定されていません")
        self.api_key = GEMINI_API_KEY
        self.api_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
        self.keywords = POLITICAL_KEYWORDS
        self.exclude_keywords = EXCLUDE_KEYWORDS
        self.comment_analyzer = YahooNewsCommentAnalyzer(GEMINI_API_KEY)
        
    def fetch_news_from_feed(self, feed_url: str, source_name: str, max_items: int = 10) -> List[Dict]:
        """RSSフィードからニュースを取得"""
        try:
            feed = feedparser.parse(feed_url)
            articles = []
            
            for entry in feed.entries[:max_items]:
                article = {
                    'source': source_name,
                    'title': entry.get('title', ''),
                    'link': entry.get('link', ''),
                    'summary': entry.get('summary', entry.get('description', '')),
                    'published': entry.get('published', ''),
                }
                articles.append(article)
            
            return articles
        except Exception as e:
            print(f"⚠️ {source_name}のフィード取得エラー: {e}")
            return []
    
    def contains_keywords(self, text: str) -> Tuple[bool, List[str]]:
        """キーワードチェック"""
        if not text:
            return False, []
        
        matched_keywords = []
        text_lower = text.lower()
        
        for keyword in self.keywords:
            if keyword.lower() in text_lower:
                matched_keywords.append(keyword)
        
        return len(matched_keywords) > 0, matched_keywords
    
    def contains_exclude_keywords(self, text: str) -> Tuple[bool, List[str]]:
        """除外キーワードチェック"""
        if not text:
            return False, []
        
        matched_exclude = []
        text_lower = text.lower()
        
        for keyword in self.exclude_keywords:
            if keyword.lower() in text_lower:
                matched_exclude.append(keyword)
        
        return len(matched_exclude) > 0, matched_exclude
    
    def check_political_relevance_with_gemini(self, title: str, summary: str) -> Tuple[int, str]:
        """Gemini APIで政治関連度を判定"""
        try:
            prompt = f"""以下のニュースが「日本の国内政治」に関連しているか0-100点で評価してください。

判定基準:
- 90-100点: 国会、内閣、政党、選挙、法案、政策など明確な政治ニュース
- 70-89点: 政治家の政治的発言、政治イベント、政治的影響のある経済ニュース
- 50-69点: 政治家が登場するが政治活動以外の話題
- 0-49点: 政治と無関係

ニュース:
タイトル: {title}
内容: {summary[:300]}

以下のJSON形式で回答してください:
{{"score": 数値, "reason": "簡潔な理由"}}"""

            headers = {'Content-Type': 'application/json'}
            data = {"contents": [{"parts": [{"text": prompt}]}]}
            
            response = requests.post(
                f"{self.api_url}?key={self.api_key}",
                headers=headers,
                json=data,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                text_response = result['candidates'][0]['content']['parts'][0]['text']
                
                json_match = re.search(r'\{[^}]+\}', text_response)
                if json_match:
                    json_data = json.loads(json_match.group())
                    score = int(json_data.get('score', 0))
                    reason = json_data.get('reason', '')
                    return score, reason
                    
            return 50, "API エラー"
                
        except Exception as e:
            print(f"⚠️ Gemini判定エラー: {e}")
            return 50, f"エラー: {str(e)}"
    
    def filter_political_news(self, all_news: Dict[str, List[Dict]]) -> List[Dict]:
        """政治関連ニュースをフィルタリング + 世論分析"""
        candidate_news = []
        
        # ステップ1: キーワードフィルタ
        print("\n🔍 ステップ1: キーワードフィルタリング")
        for source_name, articles in all_news.items():
            for article in articles:
                title = article['title']
                summary = self._clean_html(article['summary'])
                full_text = f"{title} {summary}"
                
                has_keyword, matched = self.contains_keywords(full_text)
                
                if has_keyword:
                    has_exclude, exclude_matched = self.contains_exclude_keywords(full_text)
                    
                    if has_exclude:
                        print(f"❌ 除外: 【{source_name}】 {title[:50]}... (除外: {', '.join(exclude_matched[:2])})")
                        continue
                    
                    article['matched_keywords'] = matched
                    candidate_news.append(article)
                    print(f"✅ 候補: 【{source_name}】 {title[:50]}... (キー: {', '.join(matched[:3])})")
        
        print(f"\n📊 キーワードマッチ: {len(candidate_news)}件")
        
        # ステップ2: Gemini AIで政治関連度判定
        print("\n🤖 ステップ2: Gemini AIによる政治関連度判定")
        filtered_news = []
        
        for article in candidate_news:
            title = article['title']
            summary = self._clean_html(article['summary'])
            
            score, reason = self.check_political_relevance_with_gemini(title, summary)
            article['political_score'] = score
            article['ai_reason'] = reason
            
            if score >= 70:
                # ステップ3: 世論分析
                print(f"\n📰 世論分析開始: {title[:50]}...")
                yahoo_url = self.comment_analyzer.search_yahoo_news(title)
                
                if yahoo_url:
                    comments = self.comment_analyzer.get_yahoo_comments(yahoo_url)
                    sentiment_analysis = self.comment_analyzer.analyze_sentiment_with_gemini(title, comments)
                    article['sentiment_analysis'] = sentiment_analysis
                    article['yahoo_url'] = yahoo_url
                else:
                    article['sentiment_analysis'] = None
                    article['yahoo_url'] = None
                
                filtered_news.append(article)
                print(f"✅ 合格 [{score}点]: {title[:50]}")
                time.sleep(2)  # API制限対策
            else:
                print(f"❌ 不合格 [{score}点]: {title[:50]}")
        
        filtered_news.sort(key=lambda x: x['political_score'], reverse=True)
        return filtered_news
    
    def fetch_all_news(self) -> Dict[str, List[Dict]]:
        """全メディアからニュースを取得"""
        all_news = {}
        
        for source_name, config in NEWS_FEEDS.items():
            feed_url = config['url']
            language = config['language']
            print(f"📰 {source_name}（{language}）からニュースを取得中...")
            articles = self.fetch_news_from_feed(feed_url, source_name)
            all_news[source_name] = articles
            print(f"  → {len(articles)}件取得")
        
        return all_news
    
    def _clean_html(self, text: str) -> str:
        """HTMLタグを除去"""
        text = re.sub(r'<[^>]+>', '', text)
        text = text.replace('&nbsp;', ' ').replace('&amp;', '&')
        text = text.replace('&lt;', '<').replace('&gt;', '>')
        text = text.replace('&quot;', '"')
        return text.strip()

class DiscordNotifier:
    """Discord通知クラス"""
    
    def __init__(self, webhook_url: str):
        if not webhook_url:
            raise ValueError("DISCORD_WEBHOOK_POLITICS環境変数が設定されていません")
        self.webhook_url = webhook_url
    
    def send_political_news_with_sentiment(self, filtered_news: List[Dict]) -> bool:
        """政治ニュース + 世論分析を送信"""
        if not filtered_news:
            print("📭 政治関連ニュースはありませんでした")
            self._send_message("🏛️ **国内政治ニュース速報** 🏛️\n\n📭 この時間で政治関連ニュースは検出されませんでした。")
            return True
        
        now = datetime.now().strftime('%Y年%m月%d日 %H:%M')
        
        for article in filtered_news[:5]:  # 上位5件
            message = self._format_article_with_sentiment(article, now)
            self._send_message(message)
            time.sleep(1)
        
        return True
    
    def _format_article_with_sentiment(self, article: Dict, timestamp: str) -> str:
        """記事 + 世論分析のフォーマット"""
        source = article['source']
        title = article['title']
        link = article['link']
        score = article.get('political_score', 0)
        keywords = article['matched_keywords'][:3]
        sentiment = article.get('sentiment_analysis')
        
        message = f"🏛️ **国内政治ニュース + 世論分析** 🏛️\n"
        message += f"⏰ {timestamp}\n"
        message += "=" * 50 + "\n\n"
        
        message += f"📰 **ニュース**\n"
        message += f"【{source}】{title}\n"
        message += f"🎯 政治関連度: {score}点 | 🔑 {', '.join(keywords)}\n"
        message += f"🔗 {link}\n\n"
        
        if sentiment and sentiment.get('sentiment_ratio'):
            message += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            message += "📊 **世論の反応**（Yahoo!ニュースコメント分析）\n\n"
            
            ratio = sentiment['sentiment_ratio']
            message += f"🎭 感情分析:\n"
            message += f"├─ 👍 賛成: {ratio.get('positive', 0)}%\n"
            message += f"├─ 👎 反対: {ratio.get('negative', 0)}%\n"
            message += f"└─ 😐 中立: {ratio.get('neutral', 0)}%\n\n"
            
            temp = sentiment.get('temperature_score', 0)
            fire = '🔥' * min(5, temp // 20)
            empty = '⚪' * (5 - len(fire))
            message += f"🌡️ 議論の熱量: {fire}{empty} ({temp}点)\n\n"
            
            if sentiment.get('main_opinions'):
                message += "💬 主な論点:\n"
                for i, opinion in enumerate(sentiment['main_opinions'][:3], 1):
                    message += f"{i}️⃣ {opinion.get('opinion', '')}\n"
                message += "\n"
            
            if sentiment.get('representative_comments'):
                message += "🗣️ 代表的なコメント:\n"
                for comment in sentiment['representative_comments'][:3]:
                    stance = comment.get('stance', '')
                    text = comment.get('comment', '')
                    emoji = {'positive': '👍', 'negative': '👎', 'neutral': '😐'}.get(stance, '💬')
                    message += f"{emoji} {text}\n"
                message += "\n"
            
            message += f"📝 {sentiment.get('summary', '')}\n"
        else:
            message += "\n⚠️ Yahoo!ニュースにコメントがありませんでした\n"
        
        return message
    
    def _send_message(self, content: str) -> bool:
        """Discordにメッセージを送信"""
        try:
            payload = {
                "content": content,
                "username": "国内政治ウォッチャー Pro 🏛️",
                "avatar_url": "https://cdn-icons-png.flaticon.com/512/3649/3649371.png"
            }
            
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code == 204:
                print("✅ Discordへの投稿成功")
                return True
            else:
                print(f"❌ Discord投稿エラー: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Discord送信エラー: {e}")
            return False

def main():
    """メイン処理"""
    print("=" * 60)
    print("🏛️ 国内政治ニュース + 世論分析システム起動")
    print(f"⏰ 実行時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    try:
        filter_system = GeminiPoliticalFilter()
        all_news = filter_system.fetch_all_news()
        
        total_articles = sum(len(articles) for articles in all_news.values())
        print(f"\n📊 合計 {total_articles} 件のニュースを取得")
        
        if total_articles == 0:
            print("⚠️ ニュースが取得できませんでした")
            return
        
        filtered_news = filter_system.filter_political_news(all_news)
        
        print(f"\n✅ {len(filtered_news)} 件の政治ニュースを検出（70点以上）")
        
        notifier = DiscordNotifier(DISCORD_WEBHOOK_URL)
        success = notifier.send_political_news_with_sentiment(filtered_news)
        
        if success:
            print("\n🎉 処理完了！")
        else:
            print("\n⚠️ Discord投稿に失敗しました")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n❌ エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
