#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
政治・経済ニュース自動要約＆Discord投稿システム（完全日本語版）
毎朝6:30に実行され、複数メディア（日本語・英語）からニュースを取得
AIが全て日本語で要約してDiscordに投稿
"""

import os
import sys
import json
import requests
from datetime import datetime
from typing import List, Dict, Optional
import feedparser

# 環境変数から取得
DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')

# メディアのRSSフィード設定
NEWS_FEEDS = {
    # 日本語メディア
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
    
    # 英語メディア（AIが日本語で要約）
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

class NewsAggregator:
    """ニュース収集・要約クラス"""
    
    def __init__(self):
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY環境変数が設定されていません")
        
        # OpenAI APIクライアントの初期化（新旧両対応）
        self.openai_api_key = OPENAI_API_KEY
        self.client = None
        self.use_new_sdk = False
        
        try:
            # 新しいSDK (v1.0+) を試す
            from openai import OpenAI
            self.client = OpenAI(api_key=OPENAI_API_KEY)
            self.use_new_sdk = True
            print("✅ OpenAI SDK v1.0+ を使用")
        except (ImportError, TypeError) as e:
            # 古いSDKを使用
            print(f"⚠️ 新しいSDKの初期化失敗: {e}")
            print("📦 古いOpenAI SDKを使用します")
            import openai
            openai.api_key = OPENAI_API_KEY
            self.use_new_sdk = False
        
    def fetch_news_from_feed(self, feed_url: str, source_name: str, max_items: int = 5) -> List[Dict]:
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
    
    def summarize_news(self, all_news: Dict[str, List[Dict]]) -> str:
        """OpenAI APIでニュースを日本語で要約"""
        # ニュースを整形してプロンプトに含める
        news_text = ""
        
        # 日本語メディア
        news_text += "\n【日本語メディアのニュース】\n"
        for source_name, config in NEWS_FEEDS.items():
            if config['language'] == '日本語' and source_name in all_news:
                articles = all_news[source_name]
                if articles:
                    news_text += f"\n■{source_name}\n"
                    for i, article in enumerate(articles, 1):
                        news_text += f"{i}. {article['title']}\n"
                        if article['summary']:
                            summary = self._clean_html(article['summary'])
                            news_text += f"   概要: {summary[:300]}...\n"
                        news_text += f"   URL: {article['link']}\n\n"
        
        # 英語メディア
        news_text += "\n【英語メディアのニュース（日本語で要約してください）】\n"
        for source_name, config in NEWS_FEEDS.items():
            if config['language'] == 'English' and source_name in all_news:
                articles = all_news[source_name]
                if articles:
                    news_text += f"\n■{source_name}\n"
                    for i, article in enumerate(articles, 1):
                        news_text += f"{i}. {article['title']}\n"
                        if article['summary']:
                            summary = self._clean_html(article['summary'])
                            news_text += f"   Summary: {summary[:300]}...\n"
                        news_text += f"   URL: {article['link']}\n\n"
        
        # システムプロンプト
        system_prompt = """あなたは優秀な政治・経済ニュースアナリストです。
日本語と英語のニュースを分析し、**全て日本語**で以下の形式で要約してください：

【📅 本日のニュース要約】

**🔥 今日の注目トピック**
- 最も重要なニュース5-7件を簡潔に（政治・経済・金融市場）
- 国内外の重要な動きを含める

**📰 国内メディアの報道**
各メディアごとに主要ニュースを2-3行で要約
- 日経新聞
- ロイター通信
- 東洋経済オンライン
- PRタイムス
- 時事ドットコム

**🌍 海外メディアの報道（日本語で要約）**
英語のニュースも全て日本語で要約してください
- Bloomberg: 金融市場の動向
- FXStreet: 為替・金融市場
- Reuters英語版: 国際情勢

**💡 今日のポイント**
- 全体を通じた重要なポイント（2-3点）
- 日本への影響や市場への影響

**重要**: 
- 英語のニュースも必ず日本語で要約してください
- 専門用語は日本語に訳してください
- 読者が理解しやすい表現を使ってください"""
        
        # OpenAI APIで日本語要約
        print("🤖 OpenAI APIで日本語要約を生成中...")
        
        try:
            if self.use_new_sdk:
                # 新しいSDK (v1.0+)
                response = self.client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"以下のニュースを全て日本語で要約してください：\n\n{news_text}"}
                    ],
                    temperature=0.7,
                    max_tokens=3000
                )
                summary = response.choices[0].message.content
            else:
                # 古いSDK
                import openai
                response = openai.ChatCompletion.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"以下のニュースを全て日本語で要約してください：\n\n{news_text}"}
                    ],
                    temperature=0.7,
                    max_tokens=3000
                )
                summary = response['choices'][0]['message']['content']
            
            return summary
            
        except Exception as e:
            print(f"❌ OpenAI API エラー: {e}")
            import traceback
            traceback.print_exc()
            return f"要約の生成に失敗しました: {e}"
    
    def _clean_html(self, text: str) -> str:
        """HTMLタグを除去"""
        import re
        # 簡易的なHTMLタグ除去
        text = re.sub(r'<[^>]+>', '', text)
        text = text.replace('&nbsp;', ' ').replace('&amp;', '&')
        text = text.replace('&lt;', '<').replace('&gt;', '>')
        text = text.replace('&quot;', '"')
        return text.strip()

class DiscordNotifier:
    """Discord通知クラス"""
    
    def __init__(self, webhook_url: str):
        if not webhook_url:
            raise ValueError("DISCORD_WEBHOOK_URL環境変数が設定されていません")
        self.webhook_url = webhook_url
    
    def send_message(self, content: str, title: str = None) -> bool:
        """Discordにメッセージを送信"""
        try:
            # Discordの文字数制限（2000文字）を考慮
            if len(content) > 1900:
                # 長すぎる場合は分割
                self._send_long_message(content, title)
                return True
            
            payload = {
                "content": content,
                "username": "政治・経済ニュースBot 📰",
                "avatar_url": "https://cdn-icons-png.flaticon.com/512/3037/3037079.png"
            }
            
            if title:
                payload["embeds"] = [{
                    "title": title,
                    "color": 3447003,  # 青色
                    "timestamp": datetime.utcnow().isoformat()
                }]
            
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
    
    def _send_long_message(self, content: str, title: str = None):
        """長いメッセージを分割して送信"""
        # より賢い分割：見出しで分割
        import re
        
        # セクションで分割
        sections = re.split(r'(\*\*[^\*]+\*\*)', content)
        
        chunks = []
        current_chunk = ""
        
        for section in sections:
            if len(current_chunk) + len(section) < 1900:
                current_chunk += section
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = section
        
        if current_chunk:
            chunks.append(current_chunk)
        
        # 分割して送信
        for i, chunk in enumerate(chunks):
            chunk_title = f"{title} ({i+1}/{len(chunks)})" if title else None
            self.send_message(chunk, chunk_title)
            import time
            time.sleep(1)  # レート制限対策

def main():
    """メイン処理"""
    print("=" * 60)
    print("📰 政治・経済ニュース自動要約システム起動（完全日本語版）")
    print(f"⏰ 実行時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    try:
        # ニュース収集
        aggregator = NewsAggregator()
        all_news = aggregator.fetch_all_news()
        
        # 取得件数の確認
        total_articles = sum(len(articles) for articles in all_news.values())
        print(f"\n📊 合計 {total_articles} 件のニュースを取得")
        
        if total_articles == 0:
            print("⚠️ ニュースが取得できませんでした")
            return
        
        # ニュース要約（全て日本語で）
        summary = aggregator.summarize_news(all_news)
        
        # Discord投稿
        notifier = DiscordNotifier(DISCORD_WEBHOOK_URL)
        success = notifier.send_message(
            content=summary,
            title="📰 本日の政治・経済ニュース（国内外）"
        )
        
        if success:
            print("\n🎉 処理完了！全て日本語で要約されました！")
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
