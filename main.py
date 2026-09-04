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
LINE_USER_ID = os.environ.get("LINE_USER_ID")  # 開発者の個別テスト用ID

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
    body_contents = []
    
    # タイトルが辞書（構造体）で渡された場合は自由レイアウト、文字列の場合はデフォルト表示
    if isinstance(title, list):
        body_contents.extend(title)
    else:
        body_contents.append({"type": "text", "text": title, "weight": "bold", "size": "lg", "wrap": True, "color": "#111111"})

    body_contents.append({"type": "separator", "margin": "md"})
    body_contents.append({"type": "text", "text": desc, "wrap": True, "size": "lg", "color": "#333333", "margin": "md"})
    
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

    is_major = True if force_test else is_major
    header = "🚨 メジャーSQ日！" if is_major else "⚠️ 本日SQ算出日"
    color = "#C0392B"
    title = f"{'🔥 メジャーSQ通過日' if is_major else '📢 SQ算出日'}\n価格変動に厳重警戒！"
    
    desc = (
        "寄り付き(9:00)前後を中心に、機関投資家の巨額な決済注文が交錯し、株価が突発的に上下へブレやすくなります。\n\n"
        "💡 【豆知識】\n"
        "メジャーSQは3・6・9・12月の第2金曜日周辺に訪れ、先物とオプションの決済が重なる超重要日です。通過後は相場のトレンドがガラリと変わることも多いため、慎重な立ち回りが必要です。"
    )
    return create_flex_bubble(header, color, title, desc, "※SQ算出にかかわる板の急変にご注意ください。")

def get_margin_bubble(force_test=False):
    latest_date, latest_value = "2026/09/04", -11.50
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
    
    if latest_value <= THRES_DANGER:
        desc = (
            "個人投資家の含み損が拡大しており、追証回避の投げ売り（追い込まれた売却）が出やすい危険水域です。\n\n"
            "💡 【相場のセオリー】\n"
            "歴史的に-10%〜-15%に達すると個人の投げ売りが一巡し、セリングクライマックス（底打ち・絶好の買い場）を形成しやすいとされています。"
        )
    else:
        desc = (
            "個人投資家の損益状況は正常範囲内（平穏）です。\n\n"
            "💡 【相場のセオリー】\n"
            "一般的に-5%〜-9%程度が平時の水準です。0%（プラス圏）に近づくほど個人投資家の懐が温まり、相場全体の買い勢力が強まります。"
        )

    return create_flex_bubble(header, color, title, desc, "ソース: トレーダーズ・ウェブ")

def get_anomaly_bubble(dt_jst, force_test=False):
    title, desc = "", ""
    if force_test:
        title = "🦃 サンクスギビングラリー"
        desc = (
            "明日の米国感謝祭から週末の「ブラックフライデー」にかけて、年末商戦への期待感から米国株が上昇しやすいアノマリー期間に入ります！\n\n"
            "💡 【注目ポイント】\n"
            "機関投資家が休暇に入るため市場の商い（取引量）は薄くなります。少しの注文で株価が大きく動く可能性があるため注意してください。"
        )
    else:
        m, d = dt_jst.month, dt_jst.day
        if m == 9 and d == 8:
            title = "🍂 9月効果 (September Effect)"
            desc = (
                "レイバーデイ明けで機関投資家が市場に本格復帰します。秋に向けたポジション調整や決算前の節税売りが出やすく、年間で最も株価が下落しやすい警戒時期のスタートです。\n\n"
                "💡 【注意点】\n"
                "無理な買い増しは避け、キャッシュ比率を高めて押し目を待つのが定石とされています。"
            )
        if not title: return None
    
    return create_flex_bubble("🗓️ 相場カレンダー", "#2C3E50", title, desc, "※アノマリーは経験則であり、確定事項ではありません。")

def get_fomc_bubble(dt_jst, force_test=False):
    if not force_test: return None
    title = "🏛️🇺🇸 FOMC政策金利発表"
    desc = (
        "日本時間の今夜深夜(3:00〜4:00頃)に米国の政策金利と声明文が発表され、パウエルFRB議長の記者会見が行われます。\n\n"
        "💡 【影響と注意点】\n"
        "全世界の株価・ドル円（為替）のトレンドを左右する最重要イベントです。発表直後は上下に激しい乱高下が発生するため、夜間のポジション持ち越しは厳重に警戒してください。"
    )
    return create_flex_bubble("🚨 最重要イベント", "#8E44AD", title, desc)

def get_gmo_bubble(force_test=False):
    events = ["⏰ 21:30 | 米・新規失業保険申請件数", "⏰ 23:00 | 米・ISM非製造業景況指数"]
    if not force_test:
        try:
            res = requests.get("https://www.gaikaex.com/gaikaex/mark/calendar/", headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            pass
        except: return None
    
    if not events: return None
    if len(events) > 10: return None

    desc = (
        "本日発表予定の重要度★★★（最重要）指標です：\n\n" + 
        "\n".join(events) + 
        "\n\n💡 指標発表の前後数分間は、為替・先物市場でスプレッドが拡大し突発的な値動きが起きやすくなります。"
    )
    return create_flex_bubble("🇺🇸 米国★★★重要指標", "#F39C12", "本日発表の注目経済指標", desc, "ソース: GMO証券カレンダー")

def get_fgi_bubble(force_test=False):
    score, rating = 45, "Neutral" # テスト用ダミーデータ（45は中立）
    if not force_test:
        try:
            res = requests.get("https://production.dataviz.cnn.io/index/fearandgreed/graphdata", headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            if res.status_code == 200:
                score = int(round(res.json().get("fear_and_greed", {}).get("score", 0)))
                rating = res.json().get("fear_and_greed", {}).get("rating", "Neutral")
        except: return None
    
    if score is None: return None

    # ★ 7段階の判定とインデックス計算
    idx = 0
    if score <= 10: idx = 0
    elif score <= 24: idx = 1
    elif score <= 44: idx = 2
    elif score <= 55: idx = 3 # 中立
    elif score <= 75: idx = 4
    elif score <= 90: idx = 5
    else: idx = 6

    # 7段階のカラーパレット
    colors = ["#8B0000", "#E74C3C", "#D35400", "#F39C12", "#95A5A6", "#2ECC71", "#27AE60"]
    current_color = colors[idx] # ★ 現在地の判定色を取得

    if score <= 10: desc = "歴史的な大パニック！ここは絶対に買え！！身の毛もよだつ恐怖に打ち勝ち大金を手に入れろ！"
    elif score <= 24: desc = "市場は極度の恐怖！買い場で間違いなし！みんなが逃げ出している超バーゲンセールです。"
    elif score <= 44: desc = "市場は恐怖モードに突入中。弱気なムードが漂っています。"
    elif score <= 55: desc = "市場はきわめて冷静です。嵐の前の静けさか、方向感を探る展開が続いています。"
    elif score <= 75: desc = "市場は強気モード上昇中！買いの勢いがついています。"
    elif score <= 90: desc = "市場は超イケイケ状態！絶好調ですが高値掴みには注意！"
    else: desc = "市場はイケイケ絶頂・過熱感バツグン！暴落間近につき厳重警戒！"

    # ★ タイトル領域：「スコア」と「判定」を分離し、判定文字に指定色を適用
    title_structures = [
        {"type": "text", "text": f"スコア: 【 {score} / 100 】", "weight": "bold", "size": "xl", "color": "#111111"},
        {
            "type": "box", "layout": "horizontal", "margin": "xs",
            "contents": [
                {"type": "text", "text": "判定: ", "weight": "bold", "size": "xl", "color": "#111111", "flex": 0},
                {"type": "text", "text": f"{rating}", "weight": "bold", "size": "xl", "color": current_color, "flex": 1} # ★ メーターと同色を指定
            ]
        }
    ]

    legend_info = [
        ("濃赤:", " 0〜10 (ここは絶対に買え！！)"),
        ("赤:", " 11〜24 (買い場で間違いなし！)"),
        ("濃橙:", " 25〜44 (極度の恐怖入り)"),
        ("橙:", " 45〜55 (恐怖)"),
        ("灰:", " 56〜75 (中立・平穏)"),
        ("緑:", " 76〜90 (強気モード)"),
        ("濃緑:", " 91〜100 (超イケイケ)")
    ]

    marker_boxes = []
    bar_boxes = []

    for i in range(7):
        marker_text = "▼" if i == idx else " "
        marker_boxes.append({
            "type": "text", "text": marker_text, "size": "sm", "color": "#111111", "align": "center", "weight": "bold", "flex": 1
        })
        height = "16px" if i == idx else "6px"
        bar_boxes.append({
            "type": "box", "layout": "vertical", "backgroundColor": colors[i], "height": height, "flex": 1, "cornerRadius": "3px",
            "contents": []
        })

    legend_boxes = [{"type": "text", "text": "💡 【メーターの凡例】", "size": "sm", "color": "#555555", "weight": "bold", "margin": "sm"}]
    for i in range(7):
        color_label, text_body = legend_info[i]
        is_current = (i == idx)
        
        legend_boxes.append({
            "type": "box",
            "layout": "horizontal",
            "margin": "xs",
            "contents": [
                {
                    "type": "text",
                    "text": color_label,
                    "color": colors[i],
                    "size": "xs",
                    "weight": "bold",
                    "flex": 0
                },
                {
                    "type": "text",
                    "text": text_body,
                    "color": "#111111",
                    "size": "xs",
                    "weight": "bold" if is_current else "regular",
                    "flex": 1,
                    "wrap": True
                }
            ]
        })

    buffett_box = {
        "type": "text",
        "text": "※ウォーレン・ヴァフェットの名言\n「他人が貪欲なときに恐れ、他人が恐れているときに貪欲であれ」",
        "size": "xxs",
        "color": "#AAAAAA",
        "wrap": True,
        "margin": "lg"
    }

    extra_contents = [
        {"type": "separator", "margin": "md"},
        {"type": "box", "layout": "horizontal", "contents": marker_boxes, "spacing": "xs", "margin": "md"},
        {"type": "box", "layout": "horizontal", "contents": bar_boxes, "spacing": "xs", "alignItems": "center"},
        {"type": "box", "layout": "vertical", "contents": legend_boxes, "margin": "lg"},
        buffett_box
    ]

    # ★ カード最上部のヘッダー背景色も現在の判定色(current_color)へ連動
    return create_flex_bubble("🧭 Fear & Greed Index", current_color, title_structures, desc, "ソース: CNN Markets", extra_contents)

# ==========================================
# 5. カルーセル一括送信処理
# ==========================================
def send_carousel_message(bubbles):
    if not bubbles: return
    if not LINE_ACCESS_TOKEN:
        print("❌ LINE_ACCESS_TOKEN が設定されていません。")
        return

    payload = {
        "messages": [
            {
                "type": "flex",
                "altText": "相場アラート（複数通知があります）",
                "contents": {"type": "carousel", "contents": bubbles}
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
        print("🛠️ テスト用カルーセルを強制生成します...")
        bubbles.append(get_sq_bubble(now_jst, force_test=True))
        bubbles.append(get_margin_bubble(force_test=True))
        bubbles.append(get_anomaly_bubble(now_jst, force_test=True))
        bubbles.append(get_fomc_bubble(now_jst, force_test=True))
        bubbles.append(get_gmo_bubble(force_test=True))
        bubbles.append(get_fgi_bubble(force_test=True))
        
        bubbles = [b for b in bubbles if b is not None]
        send_carousel_message(bubbles)
        print("🏁 テスト処理完了。")
        return

    # --- 以下、本番運用時のロジック ---
    today_wd = now_jst.weekday()
    now_hour = now_jst.hour

    if today_wd == 5: return # 土曜スキップ

    if today_wd == 6:
        b_margin = get_margin_bubble()
        b_fgi = get_fgi_bubble()
        if b_margin: bubbles.append(b_margin)
        if b_fgi: bubbles.append(b_fgi)

    elif now_hour == 8:
        if not is_japanese_holiday(now_jst):
            b_sq = get_sq_bubble(now_jst)
            b_margin = get_margin_bubble()
            b_anomaly = get_anomaly_bubble(now_jst)
            if b_sq: bubbles.append(b_sq)
            if b_margin: bubbles.append(b_margin)
            if b_anomaly: bubbles.append(b_anomaly)

    else:
        if not is_us_holiday(now_jst):
            b_fomc = get_fomc_bubble(now_jst)
            b_gmo = get_gmo_bubble()
            b_fgi = get_fgi_bubble()
            if b_fomc: bubbles.append(b_fomc)
            if b_gmo: bubbles.append(b_gmo)
            if b_fgi: bubbles.append(b_fgi)

    if bubbles:
        send_carousel_message(bubbles)

if __name__ == "__main__":
    main()
