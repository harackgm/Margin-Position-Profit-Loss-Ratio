import os
import re
import time
from datetime import datetime, date, timedelta, timezone
import requests
from bs4 import BeautifulSoup
import json

# ==========================================
# 1. 設定情報
# ==========================================
LINE_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN")
LINE_USER_ID = os.environ.get("LINE_USER_ID")  # ★ 開発者の個別テスト用ID

# ★ テスト実行用安全スイッチ
# Trueの時は、条件を無視して全6種類のアラートを生成し、開発者のみにカルーセル送信します。
DEBUG_MODE = True 

THRES_DANGER = -10.0
THRES_RECOVERY = 0.0

# ==========================================
# 2. 祝日判定ロジック (日本 & アメリカ)
# ==========================================
def is_japanese_holiday(dt_jst):
    today_date = dt_jst.date()
    year, month, day, weekday = today_date.year, today_date.month, today_date.day, today_date.weekday()
    if (month == 12 and day == 31) or (month == 1 and day <= 3): return True
    fixed_holidays = [(1, 1), (2, 11), (2, 23), (4, 29), (5, 3), (5, 4), (5, 5), (8, 11), (11, 3), (11, 23)]
    vernal_equinox = 20 if (year % 4 == 0 or year % 4 == 1) else 21
    autumnal_equinox = 22 if (year % 4 == 0 or year % 4 == 1) else 23
    fixed_holidays.extend([(3, vernal_equinox), (9, autumnal_equinox)])
    if (month, day) in fixed_holidays: return True
    if weekday == 0:
        if (month == 1 and 8 <= day <= 14) or (month == 7 and 15 <= day <= 21) or \
           (month == 9 and 15 <= day <= 21) or (month == 10 and 8 <= day <= 14): return True
        yesterday = today_date - timedelta(days=1)
        if (yesterday.month, yesterday.day) in fixed_holidays: return True
    return False

def is_us_holiday(dt_jst):
    today_date = dt_jst.date()
    month, day, weekday = today_date.month, today_date.day, today_date.weekday()
    if (month == 1 and day == 1) or (month == 6 and day == 19) or (month == 7 and day == 4) or (month == 12 and day == 25): return True
    if weekday == 0:
        if (month == 1 and 15 <= day <= 21) or (month == 2 and 15 <= day <= 21) or \
           (month == 5 and 25 <= day <= 31) or (month == 9 and 1 <= day <= 7): return True
    if weekday == 3 and month == 11 and 22 <= day <= 28: return True
    return False

# ==========================================
# 3. Flex Message バブル生成用共通関数
# ==========================================
def create_flex_bubble(header_text, header_color, title, desc, footer_text=None, extra_contents=None):
    """個別のFlex Messageカード（Bubble）を生成する共通フォーマット"""
    body_contents = [
        {"type": "text", "text": title, "weight": "bold", "size": "xl", "wrap": True, "color": "#111111"},
        {"type": "separator", "margin": "md"},
        {"type": "text", "text": desc, "wrap": True, "size": "lg", "color": "#333333", "margin": "md"}
    ]
    
    # ★ Fear & Greed Indexの「目安リスト」など、追加の要素を本文の下に挿入できる仕組みを追加
    if extra_contents:
        body_contents.extend(extra_contents)

    bubble = {
        "type": "bubble",
        "size": "mega", 
        "styles": {"header": {"backgroundColor": header_color}},
        "header": {
            "type": "box", "layout": "vertical", "paddingAll": "10px",
            "contents": [{"type": "text", "text": header_text, "color": "#FFFFFF", "weight": "bold", "size": "md", "wrap": True}]
        },
        "body": {
            "type": "box", "layout": "vertical", "spacing": "sm", "paddingAll": "15px",
            "contents": body_contents
        }
    }
    if footer_text:
        bubble["footer"] = {
            "type": "box", "layout": "vertical", "paddingAll": "10px",
            "contents": [{"type": "text", "text": footer_text, "wrap": True, "size": "sm", "color": "#999999"}]
        }
    return bubble

# ==========================================
# 4. 各機能のバブル生成ロジック
# ==========================================
def get_sq_bubble(dt_jst, force_test=False):
    is_sq, is_major = False, False
    if not force_test:
        first_day = date(dt_jst.year, dt_jst.month, 1)
        days_to_first_friday = (4 - first_day.weekday()) % 7
        sq_date = first_day + timedelta(days=days_to_first_friday + 7)
        while True:
            if sq_date.weekday() in [5, 6] or is_japanese_holiday(datetime(sq_date.year, sq_date.month, sq_date.day, tzinfo=timezone(timedelta(hours=9)))):
                sq_date -= timedelta(days=1)
            else: break
        if dt_jst.date() == sq_date:
            is_sq, is_major = True, (dt_jst.month in [3, 6, 9, 12])
        
        if not is_sq: return None

    # テスト時は強制的にメジャーSQとして生成
    is_major = True if force_test else is_major
    header = "🚨 メジャーSQ日！" if is_major else "⚠️ 本日SQ算出日"
    color = "#C0392B" # 濃い赤
    title = f"{'🔥 メジャーSQ通過日' if is_major else '📢 SQ算出日'}\n価格変動に厳重警戒！"
    desc = "寄り付き(9:00)前後を中心に、思惑が交錯し株価が突発的に乱高下する傾向があります。無理な高値掴みに注意し、指値管理を徹底してください。"
    return create_flex_bubble(header, color, title, desc, "※SQ値算出のための決済注文が集中します。")

def get_margin_bubble(force_test=False):
    latest_date, latest_value = "2026/09/04", -11.50 # テスト用ダミーデータ
    if not force_test:
        try:
            res = requests.get("https://www.traders.co.jp/margin_derivatives/margin_transition", headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            soup = BeautifulSoup(res.text, "html.parser")
            for row in soup.find_all("tr"):
                cells = row.find_all(["td", "th"])
                if len(cells) >= 11 and "/" in cells[0].get_text(strip=True):
                    eval_str = cells[9].get_text(strip=True)
                    if eval_str not in ["-", "－"]:
                        latest_value = float(eval_str)
                        latest_date = cells[0].get_text(strip=True)
                        break
        except: return None
        if latest_value is None: return None

        jst = timezone(timedelta(hours=9))
        is_sunday = (datetime.now(jst).weekday() == 6)
        if not (is_sunday or latest_value <= THRES_DANGER or latest_value >= THRES_RECOVERY): return None

    color = "#E74C3C" if latest_value <= THRES_DANGER else ("#27AE60" if latest_value >= 0 else "#2980B9")
    header = "📉 信用評価損益率 (危険水域)" if latest_value <= THRES_DANGER else "📊 信用評価損益率"
    title = f"現在値: 【 {latest_value}% 】\n({latest_date})"
    desc = "追証発生や追い込まれた個人の投げ売りが出る危険性が高まっています。" if latest_value <= THRES_DANGER else "現在の個人投資家の損益状況は正常範囲内です。"
    return create_flex_bubble(header, color, title, desc, "ソース: トレーダーズ・ウェブ")

def get_anomaly_bubble(dt_jst, force_test=False):
    title, desc = "", ""
    if force_test:
        # テスト用ダミー（サンクスギビング）
        title, desc = "🦃 サンクスギビング・ラリー", "明日の米国感謝祭から「ブラックフライデー」にかけて、年末商戦への期待感から米国株が上がりやすい期間です。突発的な動きに注意。"
    else:
        # 実際の判定ロジック
        m, d = dt_jst.month, dt_jst.day
        if m == 9 and d == 8: # 簡易判定（テストコード用省略）
            title, desc = "🍂 9月効果 (September Effect)", "レイバーデイ明けで機関投資家が本格復帰。秋に向けた節税売りが出やすく、年間で最も株価が下落しやすい警戒時期のスタートです。"
        if not title: return None
    
    return create_flex_bubble("🗓️ 相場カレンダー", "#2C3E50", title, desc, "※アノマリーは経験則です。一つの目安として活用ください。")

def get_fomc_bubble(dt_jst, force_test=False):
    if not force_test: return None # 本来は日付判定が入るが、テスト用に短縮
    title = "🏛️🇺🇸 FOMC政策金利発表"
    desc = "日本時間の今夜深夜(3:00〜4:00頃)に政策金利が発表されます。\n発表前後でドル円や米国株が激しく乱高下する警戒夜です。ポジションの持ち越しに注意！"
    return create_flex_bubble("🚨 最重要イベント", "#8E44AD", title, desc)

def get_gmo_bubble(force_test=False):
    events = ["⏰ 21:30 | 米・新規失業保険申請件数", "⏰ 23:00 | 米・ISM非製造業景況指数"]
    if not force_test:
        try:
            res = requests.get("https://www.gaikaex.com/gaikaex/mark/calendar/", headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            pass
        except: return None
    
    if not events: return None
    if len(events) > 10: return None # ★ 大量通知ストッパー

    desc = "\n".join(events)
    return create_flex_bubble("🇺🇸 米国★★★重要指標", "#F39C12", "本日発表の注目経済指標", desc, "ソース: GMO証券カレンダー")

def get_fgi_bubble(force_test=False):
    score, rating = 45, "Neutral" # テスト用ダミーデータ（目安リストがわかりやすいようスコアを変更）
    if not force_test:
        try:
            res = requests.get("https://production.dataviz.cnn.io/index/fearandgreed/graphdata", headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            if res.status_code == 200:
                score = int(round(res.json().get("fear_and_greed", {}).get("score", 0)))
                rating = res.json().get("fear_and_greed", {}).get("rating", "Neutral")
        except: return None
    
    if score is None: return None
    color = "#E74C3C" if score <= 24 else ("#27AE60" if score >= 56 else "#34495E")
    
    if score <= 24: desc = "市場は極限のパニック状態です！みんなが恐怖で逃げ出しています。大バーゲンか底なし沼か…！？"
    elif score <= 55: desc = "市場はきわめて冷静です。嵐の前の静けさか、方向感を探る展開が続いています。"
    else: desc = "市場は強気ムード上昇中！買いの勢いがついています。"

    # ★ スコア目安リストの生成ロジックを追加
    m0 = "[★]" if score <= 10 else "[  ]"
    m1 = "[★]" if 11 <= score <= 24 else "[  ]"
    m2 = "[★]" if 25 <= 44 else "[  ]"
    m3 = "[★]" if 45 <= score <= 55 else "[  ]"
    m4 = "[★]" if 56 <= score <= 75 else "[  ]"
    m5 = "[★]" if score >= 76 else "[  ]"

    guide_text = (
        f"💡 【スコアの目安】\n"
        f"{m0} 0〜10：超絶買い場\n"
        f"{m1} 11〜24：極度の恐怖\n"
        f"{m2} 25〜44：恐怖\n"
        f"{m3} 45〜55：中立・平穏\n"
        f"{m4} 56〜75：強気モード\n"
        f"{m5} 76〜100：超イケイケ"
    )

    # ★ 本文の下に目安リストを別のテキストブロックとして追加
    extra_contents = [
        {"type": "separator", "margin": "md"},
        {"type": "text", "text": guide_text, "wrap": True, "size": "md", "color": "#555555", "margin": "md"}
    ]

    return create_flex_bubble("🧭 Fear & Greed Index", color, f"スコア: 【 {score} / 100 】\n判定: {rating}", desc, "ソース: CNN Markets", extra_contents)

# ==========================================
# 5. カルーセル一括送信処理
# ==========================================
def send_carousel_message(bubbles):
    """複数のバブル（最大12個）を横スワイプのカルーセル形式で送信する"""
    if not bubbles:
        return
    if not LINE_ACCESS_TOKEN:
        print("❌ LINE_ACCESS_TOKEN が設定されていません。")
        return

    payload = {
        "messages": [
            {
                "type": "flex",
                "altText": "相場アラート（複数通知があります）",
                "contents": {
                    "type": "carousel",
                    "contents": bubbles
                }
            }
        ]
    }

    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"}
    url = "https://api.line.me/v2/bot/message/push" if DEBUG_MODE else "https://api.line.me/v2/bot/message/broadcast"
    
    if DEBUG_MODE:
        if not LINE_USER_ID: return
        payload["to"] = LINE_USER_ID

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        if res.status_code == 200:
            print(f"🚀 LINE カルーセル送信成功！（バブル数: {len(bubbles)}）")
        else:
            print(f"❌ LINE配信失敗: {res.status_code} - {res.text}")
    except Exception as e:
        print(f"❌ LINE送信エラー: {e}")

# ==========================================
# 6. メイン処理
# ==========================================
def main():
    jst = timezone(timedelta(hours=9))
    now_jst = datetime.now(jst)
    bubbles = []

    print(f"🤖 チェック開始... (DEBUG_MODE={DEBUG_MODE})")

    if DEBUG_MODE:
        # ★テストモード: 全種類のバブルを強制生成してカルーセルに詰め込む
        print("🛠️ テスト用カルーセルを強制生成します...")
        bubbles.append(get_sq_bubble(now_jst, force_test=True))
        bubbles.append(get_margin_bubble(force_test=True))
        bubbles.append(get_anomaly_bubble(now_jst, force_test=True))
        bubbles.append(get_fomc_bubble(now_jst, force_test=True))
        bubbles.append(get_gmo_bubble(force_test=True))
        bubbles.append(get_fgi_bubble(force_test=True))
        
        # Noneを除去して送信
        bubbles = [b for b in bubbles if b is not None]
        send_carousel_message(bubbles)
        print("🏁 テスト処理完了。")
        return

    # --- 以下、本番運用時のロジック ---
    today_wd = now_jst.weekday()
    now_hour = now_jst.hour

    if today_wd == 5: return # 土曜スキップ

    if today_wd == 6:
        # 日曜日の定期報告
        b_margin = get_margin_bubble()
        b_fgi = get_fgi_bubble()
        if b_margin: bubbles.append(b_margin)
        if b_fgi: bubbles.append(b_fgi)

    elif now_hour == 8:
        # 朝の部
        if not is_japanese_holiday(now_jst):
            b_sq = get_sq_bubble(now_jst)
            b_margin = get_margin_bubble()
            b_anomaly = get_anomaly_bubble(now_jst)
            if b_sq: bubbles.append(b_sq)
            if b_margin: bubbles.append(b_margin)
            if b_anomaly: bubbles.append(b_anomaly)

    else:
        # 夜の部
        if not is_us_holiday(now_jst):
            b_fomc = get_fomc_bubble(now_jst)
            b_gmo = get_gmo_bubble()
            b_fgi = get_fgi_bubble()
            if b_fomc: bubbles.append(b_fomc)
            if b_gmo: bubbles.append(b_gmo)
            if b_fgi: bubbles.append(b_fgi)

    # 蓄積したバブルがあればカルーセルで送信
    if bubbles:
        send_carousel_message(bubbles)

if __name__ == "__main__":
    main()
