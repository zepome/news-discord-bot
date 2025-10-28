#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
国内政治ニュース自動監視システム（1時間ごと）
Gemini APIによる高精度フィルタリング
"""

import os
import sys
import re
import requests
import json
from datetime import datetime
from typing import List, Dict, Optional
import feedparser

# 環境変数から取得
DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_POLITICS')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

# 追跡キーワード（改善版：具体的で政治特有のもの）
POLITICAL_KEYWORDS = [
    # 政党
    '自民党', '自民', '国民民主党', '国民民主', '参政党', '日本維新の会', '維新',
    
    # 政治家（フルネームまたは役職付き）
    '高市早苗', '高市経済安保相', '高市大臣',
    '麻生太郎', '麻生副総裁',
    '片山さつき',
    '小野田紀美',
    '茂木敏充', '茂木幹事長',
    '鈴木俊一', '鈴木財務大臣', '鈴木財務相',
    '尾崎正直',
    '石原伸晃', '石原宏高',
    '安倍晋三',
    '三日月大造', '三日月知事',
    
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

# 除外キーワード（政治と無関係）
EXCLUDE_KEYWORDS = [
    # スポーツ
    'プロレス', '新日本プロレス', 'WWE', 'NJPW', 'DDT',
    'レスラー', '試合', 'チャンピオン', 'タイトルマッチ', 'リング',
    'サッカー', 'Jリーグ', 'ワールドカップ', 'プレミアリーグ',
    '野球', 'プロ野球', 'NPB', 'メジャーリーグ', 'MLB',
    'バスケ', 'NBA', 'Bリーグ',
    'テニス', 'ゴルフ', 'ボクシング', '格闘技', 'UFC',
    
    # 芸能
    '芸能', 'アイドル', 'ジャニーズ', 'AKB',
    '映画', 'ドラマ', 'アニメ', '声優',
    '俳優', '女優', 'タレント', 'お笑い',
    
    # ビジネス（政治と無関係）
    '新製品', '新商品', 'キャンペーン', 'セール',
    'ゲーム', 'アプリ', 'スマホ',
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

class GeminiPoliticalFilter:
    """Gemini APIを使った政治ニュースフィルタリングクラス"""
    
    def __init__(self):
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY環境変数が設定されていません")
        self.api_key = GEMINI_API_KEY
        self.api_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
        self.keywords = POLITICAL_KEYWORDS
        self.exclude_keywords = EXCLUDE_KEYWORDS
        
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
    
    def contains_keywords(self, text: str) -> tuple[bool, List[str]]:
        """キーワードチェック"""
        if not text:
            return False, []
        
        matched_keywords = []
        text_lower = text.lower()
        
        for keyword in self.keywords:
            if keyword.lower() in text_lower:
                matched_keywords.append(keyword)
        
        return len(matched_keywords) > 0, matched_keywords
    
    def contains_exclude_keywords(self, text: str) -> tuple[bool, List[str]]:
        """除外キーワードチェック"""
        if not text:
            return False, []
        
        matched_exclude = []
        text_lower = text.lower()
        
        for keyword in self.exclude_keywords:
            if keyword.lower() in text_lower:
                matched_exclude.append(keyword)
        
        return len(matched_exclude) > 0, matched_exclude
    
    def check_political_relevance_with_gemini(self, title: str, summary: str) -> tuple[int, str]:
        """Gemini APIで政治関連度を判定"""
        try:
            prompt = f"""以下のニュースが「日本の国内政治」に関連しているか0-100点で評価してください。

判定基準:
- 90-100点: 国会、内閣、政党、選挙、法案、政策など明確な政治ニュース
- 70-89点: 政治家の政治的発言、政治イベント、政治的影響のある経済ニュース
- 50-69点: 政治家が登場するが政治活動以外の話題（私生活、趣味など）
- 30-49点: 国際政治や経済ニュースで日本の政治への影響が間接的
- 0-29点: スポーツ、芸能、ビジネス、事件事故など政治と無関係

ニュース:
タイトル: {title}
内容: {summary[:300]}

以下のJSON形式で回答してください:
{{"score": 数値, "reason": "簡潔な理由"}}"""

            headers = {
                'Content-Type': 'application/json',
            }
            
            data = {
                "contents": [{
                    "parts": [{
                        "text": prompt
                    }]
                }]
            }
            
            response = requests.post(
                f"{self.api_url}?key={self.api_key}",
                headers=headers,
                json=data,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                text_response = result['candidates'][0]['content']['parts'][0]['text']
                
                # JSONを抽出
                import re
                json_match = re.search(r'\{[^}]+\}', text_response)
                if json_match:
                    json_data = json.loads(json_match.group())
                    score = int(json_data.get('score', 0))
                    reason = json_data.get('reason', '')
                    return score, reason
                else:
                    # JSONが見つからない場合、数値を探す
                    score_match = re.search(r'(\d+)点', text_response)
                    if score_match:
                        return int(score_match.group(1)), text_response[:100]
                    return 0, "判定失敗"
            else:
                print(f"⚠️ Gemini APIエラー: {response.status_code}")
                return 50, "API エラー（デフォルト50点）"
                
        except Exception as e:
            print(f"⚠️ Gemini判定エラー: {e}")
            return 50, f"エラー: {str(e)}"
    
    def filter_political_news(self, all_news: Dict[str, List[Dict]]) -> List[Dict]:
        """政治関連ニュースをフィルタリング"""
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
                    # ステップ2: 除外キーワードチェック
                    has_exclude, exclude_matched = self.contains_exclude_keywords(full_text)
                    
                    if has_exclude:
                        print(f"❌ 除外: 【{source_name}】 {title[:50]}... (除外ワード: {', '.join(exclude_matched[:2])})")
                        continue
                    
                    article['matched_keywords'] = matched
                    candidate_news.append(article)
                    print(f"✅ 候補: 【{source_name}】 {title[:50]}... (キーワード: {', '.join(matched[:3])})")
        
        print(f"\n📊 キーワードマッチ: {len(candidate_news)}件")
        
        # ステップ3: Gemini AIで最終判定
        print("\n🤖 ステップ2: Gemini AIによる政治関連度判定")
        filtered_news = []
        
        for article in candidate_news:
            title = article['title']
            summary = self._clean_html(article['summary'])
            
            score, reason = self.check_political_relevance_with_gemini(title, summary)
            article['political_score'] = score
            article['ai_reason'] = reason
            
            if score >= 70:  # 70点以上で合格
                filtered_news.append(article)
                print(f"✅ 合格 [{score}点]: {title[:50]}... (理由: {reason[:50]})")
            else:
                print(f"❌ 不合格 [{score}点]: {title[:50]}... (理由: {reason[:50]})")
        
        # スコア順にソート
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
    
    def send_political_news(self, filtered_news: List[Dict]) -> bool:
        """フィルタリングされた政治ニュースを送信"""
        if not filtered_news:
            print("📭 政治関連ニュースはありませんでした")
            # 空でも通知する場合
            self._send_message("🏛️ **国内政治ニュース速報** 🏛️\n\n📭 この1時間で政治関連ニュースは検出されませんでした。")
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
            score = article.get('political_score', 0)
            keywords = article['matched_keywords'][:3]
            
            message += f"**{i}. [{source}]** {title}\n"
            message += f"🎯 政治関連度: {score}点 | 🔑 {', '.join(keywords)}\n"
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
    print("🏛️ 国内政治ニュース監視システム起動（Gemini AI搭載）")
    print(f"⏰ 実行時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    try:
        # ニュース収集
        filter_system = GeminiPoliticalFilter()
        all_news = filter_system.fetch_all_news()
        
        # 取得件数の確認
        total_articles = sum(len(articles) for articles in all_news.values())
        print(f"\n📊 合計 {total_articles} 件のニュースを取得")
        
        if total_articles == 0:
            print("⚠️ ニュースが取得できませんでした")
            return
        
        # 政治ニュースをフィルタリング
        filtered_news = filter_system.filter_political_news(all_news)
        
        print(f"\n✅ {len(filtered_news)} 件の政治ニュースを検出（70点以上）")
        
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
