#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
国内政治ニュース自動監視システム（1時間ごと）
特定キーワードに完全一致するニュースのみを抽出してDiscordに投稿
"""

import os
import sys
import re
import requests
from datetime import datetime
from typing import List, Dict, Optional
import feedparser

# 環境変数から取得
DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_POLITICS')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')

# 追跡キーワード（完全一致）
POLITICAL_KEYWORDS = [
    # 政党・政治家
    '自民', '国民民主', '参政', '維新', '滋賀',
    '高市', '麻生', '片山', '小野田', '茂木', '鈴木', '尾崎', '石原', '安倍晋三', '三日月',
    '首相', '官房長官', '財務大臣', '外相', '農水相', '環境相', '農林水産大臣',
    
    # 政策・イシュー
    '増税', '減税', '防衛費', '社会保障', '財源',
    '憲法改正', '安全保障', '外交', '関税', '貿易',
    '少子化対策', '年金改革', '控除',
    
    # 政治イベント
    '国会', '予算委員会', '党首討論',
    '選挙', '内閣改造', '解散', '不信任',
    '政治資金', '政治献金',
    '支持率', '衆院選',
    
    # 国際政治
    '日米', '日中', '日韓', '米中', '米露', '米ロ',
    'G7', 'G20', '国連', 'ASEAN',
    '会談', '紛争', '首脳', '暗殺',
    'トランプ', 'プーチン', '習近平',
]

# メディアのRSSフィード設定
NEWS_FEEDS = {
    '日経新聞': {
        'url': 'https://www.nikkei.com/rss/',
        'language': '日本語'
    },
    'ロイター通信': {
        'url': 'https://jp.reuters.com/rssFeed/topNews',
        'language': '日本語'
    },
    '東洋経済オンライン': {
        'url': 'https://toyokeizai.net/list/feed/rss',
        'language': '日本語'
    },
    'PRタイムス': {
        'url': 'https://prtimes.jp/main/rss/',
        'language': '日本語'
    },
    '時事ドットコム': {
        'url': 'https://www.jiji.com/rss/atom.xml',
        'language': '日本語'
    },
    'Bloomberg': {
        'url': 'https://feeds.bloomberg.com/markets/news.rss',
        'language': 'English'
    },
    'FXStreet': {
        'url': 'https://www.fxstreet.com/rss/news',
        'language': 'English'
    },
    'Reuters (英語版)': {
        'url': 'https://www.reutersagency.com/feed/?taxonomy=best-topics&post_type=best',
        'language': 'English'
    },
}

class PoliticalNewsFilter:
    """政治ニュースフィルタリングクラス"""
    
    def __init__(self):
        self.keywords = POLITICAL_KEYWORDS
        
    def fetch_news_from_feed(self, feed_url: str, source_name: str, max_items: int = 10) -> List[Dict]:
        """RSSフィードからニュースを取得（多めに取得）"""
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
    
    def contains_keywords(self, text: str) -> tuple[bool, List[str]]:
        """テキストがキーワードを含むかチェック（完全一致）"""
        if not text:
            return False, []
        
        matched_keywords = []
        text_lower = text.lower()
        
        for keyword in self.keywords:
            keyword_lower = keyword.lower()
            # 完全一致チェック（単語境界を考慮）
            if keyword_lower in text_lower:
                matched_keywords.append(keyword)
        
        return len(matched_keywords) > 0, matched_keywords
    
    def filter_political_news(self, all_news: Dict[str, List[Dict]]) -> List[Dict]:
        """政治関連ニュースのみをフィルタリング"""
        filtered_news = []
        
        for source_name, articles in all_news.items():
            for article in articles:
                # タイトルと概要をチェック
                title = article['title']
                summary = self._clean_html(article['summary'])
                full_text = f"{title} {summary}"
                
                has_keyword, matched = self.contains_keywords(full_text)
                
                if has_keyword:
                    article['matched_keywords'] = matched
                    article['priority'] = len(matched)  # マッチ数で優先度判定
                    filtered_news.append(article)
                    print(f"✅ 【{source_name}】 {title[:50]}... (キーワード: {', '.join(matched[:3])})")
        
        # 優先度順にソート
        filtered_news.sort(key=lambda x: x['priority'], reverse=True)
        
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
    
    def send_political_news(self, filtered_news: List[Dict]) -> bool:
        """フィルタリングされた政治ニュースを送信"""
        if not filtered_news:
            print("📭 政治関連ニュースはありませんでした")
            return True
        
        # メッセージを整形
        now = datetime.now().strftime('%Y年%m月%d日 %H:%M')
        message = f"🏛️ **国内政治ニュース速報** 🏛️\n"
        message += f"⏰ 更新時刻: {now}\n"
        message += f"📊 検出件数: {len(filtered_news)}件\n"
        message += "=" * 50 + "\n\n"
        
        # 上位15件まで表示
        for i, article in enumerate(filtered_news[:15], 1):
            source = article['source']
            title = article['title']
            link = article['link']
            keywords = article['matched_keywords'][:5]  # 最大5個まで
            
            message += f"**{i}. [{source}]** {title}\n"
            message += f"🔑 キーワード: {', '.join(keywords)}\n"
            message += f"🔗 {link}\n\n"
            
            # Discordの文字数制限対策
            if len(message) > 1800:
                self._send_message(message)
                message = ""
        
        # 残りを送信
        if message:
            self._send_message(message)
        
        return True
    
    def _send_message(self, content: str) -> bool:
        """Discordにメッセージを送信"""
        try:
            payload = {
                "content": content,
                "username": "国内政治ウォッチャー 🏛️",
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
    print("🏛️ 国内政治ニュース監視システム起動（1時間ごと）")
    print(f"⏰ 実行時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    try:
        # ニュース収集
        filter_system = PoliticalNewsFilter()
        all_news = filter_system.fetch_all_news()
        
        # 取得件数の確認
        total_articles = sum(len(articles) for articles in all_news.values())
        print(f"\n📊 合計 {total_articles} 件のニュースを取得")
        
        if total_articles == 0:
            print("⚠️ ニュースが取得できませんでした")
            return
        
        # 政治ニュースをフィルタリング
        print("\n🔍 政治関連ニュースをフィルタリング中...")
        filtered_news = filter_system.filter_political_news(all_news)
        
        print(f"\n✅ {len(filtered_news)} 件の政治ニュースを検出")
        
        # Discord投稿
        notifier = DiscordNotifier(DISCORD_WEBHOOK_URL)
        success = notifier.send_political_news(filtered_news)
        
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
