import os
import re
import time
import random
from datetime import datetime, date, timedelta, timezone
import requests
from bs4 import BeautifulSoup
import json

# ==========================================
# 1. 設定情報
# ==========================================
LINE_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN")
LINE_USER_ID = os.environ.get("LINE_USER_ID")

# ★ テスト送信モード（True: 自分のみに送信）
# ※機能の表示確認用です。
DEBUG_MODE = True 

THRES_DANGER = -10.0
THRES_RECOVERY = 0.0

# ★ 連投防止用の状態保存ファイル（記憶用DB）
STATE_FILE = "state.json"

# ==========================================
# 1.5 状態管理（連投防止ストッパー・全時間帯対応）
# ==========================================
def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return {}

def save_state(data):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"❌ 状態記録エラー: {e}")

def is_us_holiday_already_notified(dt_jst):
    return load_state().get("last_us_holiday_date") == dt_jst.strftime('%Y-%m-%d')

def mark_us_holiday_as_notified(dt_jst):
    today_str = dt_jst.strftime('%Y-%m-%d')
    data = load_state()
    data["last_us_holiday_date"] = today_str
    save_state(data)
    print(f"🔒 連投防止: 本日({today_str})の米国休場通知を記録しました。")

def is_morning_already_notified(dt_jst):
    return load_state().get("last_morning_date") == dt_jst.strftime('%Y-%m-%d')

def mark_morning_as_notified(dt_jst):
    today_str = dt_jst.strftime('%Y-%m-%d')
    data = load_state()
    data["last_morning_date"] = today_str
    save_state(data)
    print(f"🔒 連投防止: 本日({today_str})の朝の通知を記録しました。")

def is_night_already_notified(dt_jst):
    return load_state().get("last_night_date") == dt_jst.strftime('%Y-%m-%d')

def mark_night_as_notified(dt_jst):
    today_str = dt_jst.strftime('%Y-%m-%d')
    data = load_state()
    data["last_night_date"] = today_str
    save_state(data)
    print(f"🔒 連投防止: 本日({today_str})の夜の通知を記録しました。")

def is_sunday_already_notified(dt_jst):
    return load_state().get("last_sunday_date") == dt_jst.strftime('%Y-%m-%d')

def mark_sunday_as_notified(dt_jst):
    today_str = dt_jst.strftime('%Y-%m-%d')
    data = load_state()
    data["last_sunday_date"] = today_str
    save_state(data)
    print(f"🔒 連投防止: 本日({today_str})の日曜通知を記録しました。")

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

def get_us_holiday_name(dt_jst):
    today_date = dt_jst.date()
    month, day, weekday = today_date.month, today_date.day, today_date.weekday()
    
    if month == 1 and day == 1: return "元日 (New Year's Day)"
    if month == 6 and day == 19: return "ジューンティーンス (Juneteenth Independence Day)"
    if month == 7 and day == 4: return "独立記念日 (Independence Day)"
    if month == 12 and day == 25: return "クリスマス (Christmas Day)"
    
    if weekday == 0: # 月曜日
        if month == 1 and 15 <= day <= 21: return "キング牧師記念日 (Martin Luther King Jr. Day)"
        if month == 2 and 15 <= day <= 21: return "プレジデント・デー (Washington's Birthday)"
        if month == 5 and 25 <= day <= 31: return "メモリアル・デー (Memorial Day)"
        if month == 9 and 1 <= day <= 7: return "レイバー・デー (Labor Day)"
        
    if weekday == 3 and month == 11 and 22 <= day <= 28: return "感謝祭 (Thanksgiving Day)"
    
    return None

def is_us_holiday(dt_jst):
    return get_us_holiday_name(dt_jst) is not None

# ==========================================
# 3. Flex Message バブル生成用共通関数
# ==========================================
def create_flex_bubble(header_text, header_color, title, desc, footer_text=None, extra_contents=None, footer_url=None):
    body_contents = []
    
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
        footer_item = {
            "type": "text",
            "text": footer_text,
            "wrap": True,
            "size": "sm",
            "color": "#0275D8" if footer_url else "#999999"
        }
        if footer_url:
            footer_item["action"] = {
                "type": "uri",
                "label": "Link",
                "uri": footer_url
            }
            footer_item["decoration"] = "underline"

        bubble["footer"] = {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "10px",
            "contents": [footer_item]
        }
    return bubble

def get_us_holiday_bubble(dt_jst):
    if not DEBUG_MODE and is_us_holiday_already_notified(dt_jst):
        return None

    holiday_name = get_us_holiday_name(dt_jst)
    if not holiday_name:
        return None

    img_url = "https://raw.githubusercontent.com/harackgm/Margin-Position-Profit-Loss-Ratio/main/americaholiday.png?.png"

    bubble = {
        "type": "bubble",
        "size": "mega",
        "hero": {
            "type": "image",
            "url": img_url,
            "size": "full",
            "aspectRatio": "20:13",
            "aspectMode": "cover"
        },
        "body": {
            "type": "box", "layout": "vertical", "paddingAll": "15px",
            "contents": [
                {"type": "text", "text": "🇺🇸 米国市場 休場のお知らせ", "weight": "bold", "size": "lg", "color": "#111111"},
                {"type": "separator", "margin": "md"},
                {"type": "text", "text": f"本日は「{holiday_name}」のため、米国株式市場は休場となります。", "wrap": True, "size": "md", "color": "#333333", "margin": "md"},
                {"type": "text", "text": "※Fear & Greed Indexや米国経済指標の更新はお休みです。", "wrap": True, "size": "sm", "color": "#888888", "margin": "md"}
            ]
        }
    }
    return bubble

# ==========================================
# 4. 各機能のバブル生成ロジック
# ==========================================
def get_sq_bubble(dt_jst):
    today_date = dt_jst.date()
    year, month = dt_jst.year, dt_jst.month

    first_day = date(year, month, 1)
    days_to_first_friday = (4 - first_day.weekday()) % 7
    sq_date = first_day + timedelta(days=days_to_first_friday + 7)
    while True:
        dt_check = datetime(sq_date.year, sq_date.month, sq_date.day, tzinfo=timezone(timedelta(hours=9)))
        if sq_date.weekday() in [5, 6] or is_japanese_holiday(dt_check):
            sq_date -= timedelta(days=1)
        else: break

    is_sq = (today_date == sq_date)
    is_major = (month in [3, 6, 9, 12])

    if not is_sq: return None

    header = "🚨 メジャーSQ日！" if is_major else "⚠️ 本日SQ算出日"
    color = "#C0392B"
    title = f"{'🔥 メジャーSQ通過日' if is_major else '📢 SQ算出日'}\n価格変動に厳重警戒！"
    desc = (
        "寄り付き(9:00)前後を中心に、機関投資家の巨額な決済注文が交錯し、株価が突発的に上下へブレやすくなります。\n\n"
        "💡 【豆知識】\n"
        "メジャーSQは3・6・9・12月の第2金曜日周辺に訪れ、先物とオプションの決済が重なる超重要日です。通過後は相場のトレンドがガラリと変わることも多いため、慎重な立ち回りが必要です。"
    )
    return create_flex_bubble(header, color, title, desc, "※SQ算出にかかわる板の急変にご注意ください。")

def get_margin_bubble():
    try:
        url = "https://www.traders.co.jp/margin_derivatives/margin_transition"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")
        latest_date, latest_value = "", None
        for row in soup.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) >= 11 and "/" in cells[0].get_text(strip=True):
                eval_str = cells[9].get_text(strip=True)
                if eval_str not in ["-", "－"]:
                    latest_value = float(eval_str)
                    latest_date = cells[0].get_text(strip=True)
                    break
    except Exception as e:
        print(f"❌ 信用評価損益率データ取得エラー: {e}")
        return None

    if latest_value is None: return None

    jst = timezone(timedelta(hours=9))
    is_sunday = (datetime.now(jst).weekday() == 6)
    is_danger = (latest_value <= THRES_DANGER)
    is_recovery = (latest_value >= THRES_RECOVERY)

    if not (is_sunday or is_danger or is_recovery): return None

    color = "#E74C3C" if is_danger else ("#27AE60" if is_recovery else "#2980B9")
    header = "📉 信用評価損益率 (危険水域)" if is_danger else "📊 信用評価損益率"
    title = f"現在値: 【 {latest_value}% 】\n({latest_date})"
    
    if is_danger:
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

    return create_flex_bubble(
        header, color, title, desc,
        footer_text="🔗 ソース: トレーダーズ・ウェブ",
        footer_url="https://www.traders.co.jp/margin_derivatives/margin_transition"
    )

def get_updown_ratio_bubble(check_threshold=False):
    latest_date = ""
    latest_value = None
    time.sleep(random.randint(1, 3))

    try:
        data_url = "https://nikkei225jp.com/_data/_nfsDATA/DAY/daily2year.json"
        headers_nikkei = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": "https://nikkei225jp.com/data/touraku.php"
        }
        res = requests.get(data_url, headers=headers_nikkei, timeout=15)
        if res.status_code == 200:
            matches = re.findall(r'\[\s*(\d{12,13})\s*,([^\]]+)\]', res.text)
            valid_rows = []
            for ts_str, rest in matches:
                parts = [p.strip() for p in rest.split(',')]
                if len(parts) >= 6:
                    try:
                        ts = int(ts_str) / 1000.0
                        up = float(parts[4])
                        down = float(parts[5])
                        valid_rows.append((ts, up, down))
                    except ValueError:
                        continue
            
            if len(valid_rows) >= 25:
                valid_rows.sort(key=lambda x: x[0])
                recent_25 = valid_rows[-25:]
                up_sum = sum(item[1] for item in recent_25)
                down_sum = sum(item[2] for item in recent_25)
                if down_sum > 0:
                    latest_value = round((up_sum / down_sum) * 100.0, 2)
                    last_ts = recent_25[-1][0]
                    dt = datetime.fromtimestamp(last_ts, tz=timezone(timedelta(hours=9)))
                    latest_date = dt.strftime('%Y-%m-%d')
    except Exception as e:
        print(f"⚠️ 騰落レシオ解析例外: {e}")

    if latest_value is None:
        return None

    is_overbought = (latest_value >= 120.0)
    is_oversold = (latest_value <= 80.0)

    if check_threshold and not (is_overbought or is_oversold):
        return None

    idx = 0
    if latest_value < 70.0: idx = 0
    elif latest_value < 80.0: idx = 1
    elif latest_value < 90.0: idx = 2
    elif latest_value < 110.0: idx = 3
    elif latest_value < 120.0: idx = 4
    elif latest_value < 140.0: idx = 5
    else: idx = 6

    colors = ["#8B0000", "#E74C3C", "#F39C12", "#95A5A6", "#2ECC71", "#27AE60", "#1E8449"]
    current_color = colors[idx]

    custom_ratings = [
        "EX FEAR（超底値圏）",
        "FEAR（底値圏）",
        "FEAR（やや売られ過ぎ）",
        "NEUTRAL（中立・平穏）",
        "GREED（やや買われ過ぎ）",
        "GREED（買われ過ぎ・天井圏）",
        "EX GREED（超過熱）"
    ]
    current_rating_text = custom_ratings[idx]

    if idx == 0: status_desc = "相場は総悲観の底値圏です。絶好の買い場（仕込み時）が到来しています。"
    elif idx == 1: status_desc = "売られ過ぎのサインが出ています。押し目買いを検討する好機です。"
    elif idx == 2: status_desc = "やや売られ過ぎの傾向があります。自律反発に向けた準備期間です。"
    elif idx == 3: status_desc = "売り買いの勢力が拮抗しており、相場はニュートラル（中立）な状態です。"
    elif idx == 4: status_desc = "相場がやや強気です。新規の買いは少し慎重に行う時期です。"
    elif idx == 5: status_desc = "相場は買われ過ぎ（天井圏）に達しています。利益確定売りを検討してください。"
    else: status_desc = "歴史的な超過熱状態です。いつ急落してもおかしくないため厳重警戒が必要です。"

    desc = f"{status_desc}\n\n💡 【豆知識：騰落レシオとは？】\n市場の「買われすぎ」「売られすぎ」を測る温度計のような指標です。100%が中立（売り買い互角）で、120%を超えると過熱による下落警戒、80%を割ると底値圏で反発のチャンスとされています。"

    title_structures = [
        {"type": "text", "text": f"現在値: 【 {latest_value}% 】", "weight": "bold", "size": "xl", "color": "#111111"},
        {"type": "text", "text": f"({latest_date})", "size": "md", "color": "#555555", "margin": "xs"},
        {
            "type": "box", "layout": "horizontal", "margin": "md",
            "contents": [
                {"type": "text", "text": "判定: ", "weight": "bold", "size": "lg", "color": "#111111", "flex": 0},
                {"type": "text", "text": f"{current_rating_text}", "weight": "bold", "size": "md", "color": current_color, "flex": 1, "wrap": True, "align": "center"}
            ]
        }
    ]

    legend_info = [
        ("濃赤:", " 70%未満 (絶好の買い場)"),
        ("赤:", " 70〜79% (底値圏)"),
        ("橙:", " 80〜89% (やや売られ過ぎ)"),
        ("灰:", " 90〜109% (中立・平穏)"),
        ("薄緑:", " 110〜119% (やや買われ過ぎ)"),
        ("緑:", " 120〜139% (天井圏・過熱)"),
        ("濃緑:", " 140%以上 (暴落警戒)")
    ]

    marker_boxes = []
    bar_boxes = []
    icon_boxes = []

    for i in range(7):
        marker_text = "▼" if i == idx else " "
        marker_boxes.append({"type": "text", "text": marker_text, "size": "sm", "color": "#111111", "align": "center", "weight": "bold", "flex": 1})
        height = "16px" if i == idx else "6px"
        bar_boxes.append({"type": "box", "layout": "vertical", "backgroundColor": colors[i], "height": height, "flex": 1, "cornerRadius": "3px", "contents": []})
        
        icon_text = " "
        if i == 0:
            icon_text = "😱"
        elif i == 3:
            icon_text = "😐"
        elif i == 6:
            icon_text = "😇"
        icon_boxes.append({"type": "text", "text": icon_text, "size": "xl", "align": "center", "flex": 1})

    legend_boxes = [{"type": "text", "text": "💡 【メーターの凡例】", "size": "sm", "color": "#555555", "weight": "bold", "margin": "sm"}]
    for i in range(7):
        color_label, text_body = legend_info[i]
        is_current = (i == idx)
        legend_boxes.append({
            "type": "box", "layout": "horizontal", "margin": "xs",
            "contents": [
                {"type": "text", "text": color_label, "color": colors[i], "size": "sm", "weight": "bold", "flex": 0},
                {"type": "text", "text": text_body, "color": "#111111", "size": "sm", "weight": "bold" if is_current else "regular", "flex": 1, "wrap": True}
            ]
        })

    extra_contents = [
        {"type": "separator", "margin": "md"},
        {"type": "box", "layout": "horizontal", "contents": marker_boxes, "spacing": "xs", "margin": "md"},
        {"type": "box", "layout": "horizontal", "contents": bar_boxes, "spacing": "xs", "alignItems": "center"},
        {"type": "box", "layout": "horizontal", "contents": icon_boxes, "spacing": "xs", "margin": "sm"},
        {"type": "box", "layout": "vertical", "contents": legend_boxes, "margin": "lg"}
    ]

    return create_flex_bubble(
        "🇯🇵 騰落レシオ25日 📊", current_color, title_structures, desc,
        footer_text="🔗 ソース: 日経平均 株価 AI予想",
        extra_contents=extra_contents,
        footer_url="https://nikkei225jp.com/data/touraku.php"
    )

def get_anomaly_bubble(dt_jst):
    today_date = dt_jst.date()
    month, day = today_date.month, today_date.day
    title, desc = "", ""

    is_first_business_day = True
    if dt_jst.weekday() >= 5 or is_japanese_holiday(dt_jst):
        is_first_business_day = False
    else:
        for d in range(1, day):
            check_date = dt_jst.replace(day=d)
            if check_date.weekday() < 5 and not is_japanese_holiday(check_date):
                is_first_business_day = False
                break

    if is_first_business_day:
        if month == 1:
            title = "🎍 大発会・ご祝儀相場 (新春ラリー)"
            desc = "新年の取引初日（大発会）は、新春の買い気配や「ご祝儀買い」が入りやすく、株価が上昇しやすいアノマリーがあります！\n\n💡 【立ち回り】\nご祝儀買いによる一時的な上昇に期待がかかる一方、買い一巡後の高値掴みには注意し、冷静にトレンドを見極めましょう。"
        elif month == 4:
            title, desc = "💼 新年度入り・ニューマネー", "新年度を迎え、機関投資家からの新規資金が市場に入りやすい時期です。例年、4月はパフォーマンスが良い傾向があります。"
        elif month == 5:
            title, desc = "🎏 警戒：セル・イン・メイ", "「5月に株を売れ」の有名な格言です。例年5〜10月は株価が下落・停滞しやすい時期のため、ポジション調整やリスク管理を意識しましょう。"
        elif month == 7:
            title, desc = "🏄 サマーラリー", "7月はボーナス資金の流入などで一時的に相場が上昇しやすく、強含みしやすい傾向があります。"
        elif month == 8:
            title, desc = "🌻 警戒：夏枯れ相場", "8月はお盆や海外勢の夏休みで市場参加者が減り、商いが薄くなります。少しの売りで突発的な急落（ボラティリティ増大）が起きやすいため十分注意してください。"

    if month == 9:
        first_day_of_sept = date(today_date.year, 9, 1)
        labor_day = first_day_of_sept + timedelta(days=(0 - first_day_of_sept.weekday()) % 7)
        post_labor_day = labor_day + timedelta(days=1)
        if today_date == post_labor_day:
            title = "🍂 9月効果 (September Effect)"
            desc = "レイバーデイ明けで機関投資家が市場に本格復帰します。秋に向けたポジション調整や決算前の節税売りが出やすく、年間で最も株価が下落しやすい警戒時期のスタートです。\n\n💡 【注意点】\n無理な買い増しは避け、キャッシュ比率を高めて押し目を待つのが定石とされています。"

    elif month == 11:
        first_day_of_nov = date(today_date.year, 11, 1)
        thanksgiving = first_day_of_nov + timedelta(days=(3 - first_day_of_nov.weekday()) % 7 + 21)
        thanksgiving_eve = thanksgiving - timedelta(days=1)
        if today_date == thanksgiving_eve:
            title = "🦃 サンクスギビングラリー"
            desc = "明日の米国感謝祭から週末の「ブラックフライデー」にかけて、年末商戦への期待感から米国株が上昇しやすいアノマリー期間に入ります！\n\n💡 【注目ポイント】\n機関投資家が休暇に入るため市場の商い（取引量）は薄くなります。少しの注文で株価が大きく動く可能性があるため注意してください。"

    if month == 2 and day == 3:
        title = "👹 節分天井 (せつぶんてんじょう)"
        desc = "「節分天井・彼岸底」の格言通り、新春からの買い勢いが一巡し、2月上旬に相場が一時的な高値（天井）をつけやすい時期です！\n\n💡 【立ち回り】\nここから3月のお彼岸（彼岸底）に向けて調整・下落しやすくなるため、高値掴みを避け、利益確定やリスク管理を意識しましょう。"
    elif month == 3 and day == 17:
        title = "🌸 春の彼岸底 (ひがんぞこ)"
        desc = "「節分天井・彼岸底」の格言通り、3月決算前の換金売り（現金化）により、お彼岸にかけて株価が調整・下落しやすい時期に入ります！\n\n💡 【立ち回り】\n短期的な下落に警戒しつつ、売りの波が一巡した後の「底打ち（絶好の押し目買い場）」を冷静に見極める準備をしましょう。"
    elif month == 9 and day == 20:
        title = "🍂 秋の彼岸底 (ひがんぞこ)"
        desc = "年間で最も株価が下落・停滞しやすい9月相場が調整の最終盤を迎え、底値を探る展開になりやすい時期です！\n\n💡 【立ち回り】\n突発的な売りへの警戒を怠らず、底打ち確認後は年末高（ハロウィン効果等）に向けた絶好の仕込み好機となります。"
    elif month == 3 and day == 15:
        title, desc = "🌸 期末の需給・お化粧買い", "3月末に向けて、配当権利取りや機関投資家による決算対策の買いが入りやすく、底堅い展開になりやすい時期です。"
    elif month == 10 and day == 28:
        title, desc = "🎃 ハロウィン効果", "10月末に買い、翌春（4〜5月）に売るとリターンが高くなりやすいとされる時期です。秋は歴史的に底値になりやすい仕込み時です。"
    elif month == 12 and day == 15:
        title, desc = "❄️ 警戒：節税売りピーク", "年末に向けて、税金対策のための「含み損株の売却（節税売り）」が出やすい時期です。需給悪化に注意しましょう。"
    elif month == 12 and day == 24:
        title, desc = "🎅 サンタクロースラリー", "年の最後の5営業日から新年最初の2営業日にかけて、株価が上昇しやすい期間に入ります！"

    if not title: return None
    return create_flex_bubble("🗓️ 相場カレンダー", "#2C3E50", title, desc, "※アノマリーは経験則であり、確定事項ではありません。")

def get_fomc_bubble(dt_jst):
    today_date = dt_jst.date()
    fomc_announcement_dates = [
        date(2026, 1, 29), date(2026, 3, 19), date(2026, 5, 7),
        date(2026, 6, 18), date(2026, 7, 30), date(2026, 9, 17),
        date(2026, 10, 29), date(2026, 12, 10),
        date(2027, 1, 28), date(2027, 3, 18), date(2027, 5, 6),
        date(2027, 6, 17), date(2027, 7, 29), date(2027, 9, 16),
        date(2027, 11, 4), date(2027, 12, 16),
    ]
    if (today_date + timedelta(days=1)) not in fomc_announcement_dates: return None

    title = "🏛️🇺🇸 FOMC政策金利発表"
    desc = (
        "日本時間の今夜深夜(3:00〜4:00頃)に米国の政策金利と声明文が発表され、パウエルFRB議長の記者会見が行われます。\n\n"
        "💡 【影響と注意点】\n"
        "全世界の株価・ドル円（為替）のトレンドを左右する最重要イベントです。発表直後は上下に激しい乱高下が発生するため、夜間のポジション持ち越しは厳重に警戒してください。"
    )
    return create_flex_bubble("🚨 最重要イベント", "#8E44AD", title, desc)

def get_gmo_bubble():
    try:
        gaikaex_url = "https://www.gaikaex.com/gaikaex/mark/calendar/"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(gaikaex_url, headers=headers, timeout=15)
        res.encoding = res.apparent_encoding or "utf-8"
        soup = BeautifulSoup(res.text, "html.parser")
        
        jst = timezone(timedelta(hours=9))
        today = datetime.now(jst).date()
        m_str, d_str = str(today.month), str(today.day)
        m_z, d_z = f"{today.month:02d}", f"{today.day:02d}"

        target_events, current_is_today = [], False

        for row in soup.find_all("tr"):
            row_text, row_html = row.get_text(" ", strip=True), str(row)

            if any(p in row_text for p in [f"{m_str}/{d_str}", f"{m_z}/{d_z}", f"{m_str}月{d_str}日", f"{m_z}月{d_z}日"]):
                current_is_today = True
            elif any(re.search(r"\d{1,2}/\d{1,2}|\d{1,2}月\d{1,2}日", row_text) for _ in [1]):
                if current_is_today and not any(p in row_text for p in [f"{m_str}/{d_str}", f"{m_z}/{d_z}"]):
                    current_is_today = False

            if not current_is_today: continue

            is_us = "アメリカ" in row_text or "米国" in row_text
            if not is_us:
                for img in row.find_all("img"):
                    alt = (img.get("alt", "") + img.get("title", "") + img.get("src", "")).lower()
                    if "アメリカ" in alt or "米国" in alt or "us" in alt:
                        is_us = True; break
            if not is_us: continue

            is_star3 = ("★★★" in row_text or "★3" in row_text or 
                        re.search(r"star[_-]?3|rank[_-]?3|level[_-]?3", row_html, re.I) or row_html.count("star") >= 3)

            if is_star3:
                time_match = re.search(r"\d{2}:\d{2}", row_text)
                time_str = time_match.group(0) if time_match else "時間未定"
                name_str = ""
                link_elem = row.find("a")
                if link_elem and len(link_elem.get_text(strip=True)) > 2:
                    name_str = link_elem.get_text(strip=True)
                else:
                    for td in row.find_all("td"):
                        txt = td.get_text(strip=True)
                        if len(txt) > 3 and not txt.endswith("%") and ":" not in txt and "アメリカ" not in txt:
                            name_str = txt; break
                if name_str:
                    evt = f"⏰ {time_str} | {name_str}"
                    if evt not in target_events: target_events.append(evt)
    except Exception as e:
        print(f"❌ GMO指標取得エラー: {e}")
        return None

    if not target_events: return None

    if len(target_events) > 10:
        print(f"⚠️ 大量通知ストッパー作動: 指標が {len(target_events)} 件のため送信を一時停止します。")
        return None

    desc = (
        "本日発表予定の重要度★★★（最重要）指標です：\n\n" + 
        "\n".join(target_events) + 
        "\n\n💡 指標発表の前後数分間は、為替・先物市場でスプレッドが拡大し突発的な値動きが起きやすくなります。"
    )
    return create_flex_bubble(
        "🇺🇸 米国★★★重要指標", "#F39C12", "本日発表の注目経済指標", desc,
        footer_text="🔗 ソース: GMO外貨 カレンダー",
        footer_url="https://www.gaikaex.com/gaikaex/mark/calendar/"
    )

# ★ 新機能：週間（来週）の米国★★★指標を取得する関数
def get_weekly_gmo_bubble(dt_jst):
    try:
        gaikaex_url = "https://www.gaikaex.com/gaikaex/mark/calendar/"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(gaikaex_url, headers=headers, timeout=15)
        res.encoding = res.apparent_encoding or "utf-8"
        soup = BeautifulSoup(res.text, "html.parser")

        # 直近1週間（明日から7日間）の日付パターンを作成
        target_dates = []
        date_map = {}
        for i in range(0, 8):
            d = dt_jst + timedelta(days=i)
            m_str, d_str = str(d.month), str(d.day)
            m_z, d_z = f"{d.month:02d}", f"{d.day:02d}"
            patterns = [f"{m_str}/{d_str}", f"{m_z}/{d_z}", f"{m_str}月{d_str}日", f"{m_z}月{d_z}日"]
            target_dates.extend(patterns)
            date_key = f"{d.month}/{d.day} ({'月火水木金土日'[d.weekday()]})"
            for p in patterns:
                date_map[p] = date_key

        weekly_events = {}
        current_date_key = None

        for row in soup.find_all("tr"):
            row_text = row.get_text(" ", strip=True)
            row_html = str(row)

            # 行のテキストから日付を検知
            found_date = False
            for pat in date_map.keys():
                if pat in row_text:
                    current_date_key = date_map[pat]
                    found_date = True
                    break

            # 日付行だがターゲット期間外の場合はスキップフラグを立てる
            if not found_date and any(re.search(r"\d{1,2}/\d{1,2}|\d{1,2}月\d{1,2}日", row_text) for _ in [1]):
                current_date_key = None

            if not current_date_key:
                continue

            # 米国指標かチェック
            is_us = "アメリカ" in row_text or "米国" in row_text
            if not is_us:
                for img in row.find_all("img"):
                    alt = (img.get("alt", "") + img.get("title", "") + img.get("src", "")).lower()
                    if "アメリカ" in alt or "米国" in alt or "us" in alt:
                        is_us = True; break
            if not is_us: continue

            # 重要度★★★かチェック
            is_star3 = ("★★★" in row_text or "★3" in row_text or 
                        re.search(r"star[_-]?3|rank[_-]?3|level[_-]?3", row_html, re.I) or row_html.count("star") >= 3)

            if is_star3:
                time_match = re.search(r"\d{2}:\d{2}", row_text)
                time_str = time_match.group(0) if time_match else "時間未定"
                name_str = ""
                link_elem = row.find("a")
                if link_elem and len(link_elem.get_text(strip=True)) > 2:
                    name_str = link_elem.get_text(strip=True)
                else:
                    for td in row.find_all("td"):
                        txt = td.get_text(strip=True)
                        if len(txt) > 3 and not txt.endswith("%") and ":" not in txt and "アメリカ" not in txt:
                            name_str = txt; break
                if name_str:
                    evt = f"⏰ {time_str} | {name_str}"
                    if current_date_key not in weekly_events:
                        weekly_events[current_date_key] = []
                    if evt not in weekly_events[current_date_key]:
                        weekly_events[current_date_key].append(evt)

    except Exception as e:
        print(f"❌ 週間GMO指標取得エラー: {e}")
        return None

    if not weekly_events: return None

    desc_lines = ["来週発表予定の重要度★★★（最重要）指標です：\n"]
    total_events = 0
    for date_key, evts in weekly_events.items():
        desc_lines.append(f"📅 【{date_key}】")
        for e in evts:
            desc_lines.append(f" {e}")
            total_events += 1
        desc_lines.append("")

    if total_events > 20:
        print(f"⚠️ 週間指標が {total_events} 件のため多すぎます。省略等は未実装のためそのまま進行します。")

    desc = "\n".join(desc_lines).strip()
    desc += "\n\n💡 指標発表の前後数分間は、為替・先物市場でスプレッドが拡大し突発的な値動きが起きやすくなります。"

    return create_flex_bubble(
        "🇺🇸 来週の★★★重要指標", "#D35400", "来週の注目経済指標", desc,
        footer_text="🔗 ソース: GMO外貨 カレンダー",
        footer_url="https://www.gaikaex.com/gaikaex/mark/calendar/"
    )

def get_fgi_bubble():
    score = None
    api_url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    try:
        res = requests.get(api_url, headers=headers, timeout=15)
        if res.status_code == 200:
            data = res.json()
            score = int(round(data.get("fear_and_greed", {}).get("score", 0)))
    except Exception as e:
        print(f"❌ Fear & Greed API取得エラー: {e}")

    if score is None:
        try:
            web_url = "https://edition.cnn.com/markets/fear-and-greed"
            res = requests.get(web_url, headers=headers, timeout=15)
            if res.status_code == 200:
                match = re.search(r'"score":\s*([\d\.]+)', res.text)
                if match:
                    score = int(round(float(match.group(1))))
        except Exception as e:
            print(f"❌ Fear & Greed Web取得エラー: {e}")

    if score is None:
        return None

    idx = 0
    if score <= 10: idx = 0
    elif score <= 24: idx = 1
    elif score <= 44: idx = 2
    elif score <= 55: idx = 3
    elif score <= 75: idx = 4
    elif score <= 90: idx = 5
    else: idx = 6

    colors = ["#8B0000", "#E74C3C", "#F39C12", "#95A5A6", "#2ECC71", "#27AE60", "#1E8449"]
    current_color = colors[idx]

    custom_ratings = [
        "EX FEAR（超恐怖・超買い場）",
        "FEAR（恐怖）",
        "FEAR（ビビリ）",
        "NEUTRAL（中立）",
        "GREED（貪欲）",
        "GREED（強欲）",
        "EX GREED（超強欲）"
    ]
    current_rating_text = custom_ratings[idx]

    if score <= 10: desc = "歴史的な大パニック！ここは絶対に買え！！身の毛もよだつ恐怖に打ち勝ち大金を手に入れろ！"
    elif score <= 24: desc = "市場は極度の恐怖！買い場で間違いなし！みんなが逃げ出している超バーゲンセールです。"
    elif score <= 44: desc = "市場は恐怖モードに突入中。弱気なムードが漂っています。"
    elif score <= 55: desc = "市場はきわめて冷静です。嵐の前の静けさか、方向感を探る展開が続いています。"
    elif score <= 75: desc = "市場は強気モード上昇中！買いの勢いがついています。"
    elif score <= 90: desc = "市場は超イケイケ状態！絶好調ですが高値掴みには注意！"
    else: desc = "市場はイケイケ絶頂・過熱感バツグン！暴落間近につき厳重警戒！"

    title_structures = [
        {"type": "text", "text": f"スコア: 【 {score} / 100 】", "weight": "bold", "size": "xl", "color": "#111111"},
        {
            "type": "box", "layout": "horizontal", "margin": "xs",
            "contents": [
                {"type": "text", "text": "判定: ", "weight": "bold", "size": "lg", "color": "#111111", "flex": 0},
                {"type": "text", "text": f"{current_rating_text}", "weight": "bold", "size": "lg", "color": current_color, "flex": 1, "wrap": True}
            ]
        }
    ]

    legend_info = [
        ("濃赤:", " 0〜10 (ここは絶対に買え！！)"),
        ("赤:", " 11〜24 (極度の恐怖)"),
        ("橙:", " 25〜44 (恐怖)"),
        ("灰:", " 45〜55 (中立・平穏)"),
        ("薄緑:", " 56〜75 (強気モード)"),
        ("緑:", " 76〜90 (超イケイケ！)"),
        ("濃緑:", " 91〜100 (暴落間近)")
    ]

    marker_boxes = []
    bar_boxes = []
    icon_boxes = []

    for i in range(7):
        marker_text = "▼" if i == idx else " "
        marker_boxes.append({"type": "text", "text": marker_text, "size": "sm", "color": "#111111", "align": "center", "weight": "bold", "flex": 1})
        height = "16px" if i == idx else "6px"
        bar_boxes.append({"type": "box", "layout": "vertical", "backgroundColor": colors[i], "height": height, "flex": 1, "cornerRadius": "3px", "contents": []})
        
        icon_text = " "
        if i == 0:
            icon_text = "😱"
        elif i == 3:
            icon_text = "😐"
        elif i == 6:
            icon_text = "😇"
        icon_boxes.append({"type": "text", "text": icon_text, "size": "xl", "align": "center", "flex": 1})

    legend_boxes = [{"type": "text", "text": "💡 【メーターの凡例】", "size": "sm", "color": "#555555", "weight": "bold", "margin": "sm"}]
    for i in range(7):
        color_label, text_body = legend_info[i]
        is_current = (i == idx)
        legend_boxes.append({
            "type": "box", "layout": "horizontal", "margin": "xs",
            "contents": [
                {"type": "text", "text": color_label, "color": colors[i], "size": "sm", "weight": "bold", "flex": 0},
                {"type": "text", "text": text_body, "color": "#111111", "size": "sm", "weight": "bold" if is_current else "regular", "flex": 1, "wrap": True}
            ]
        })

    buffett_box = {
        "type": "text", "text": "※ウォーレン・ヴァフェットの名言\n「他人が貪欲なときに恐れ、他人が恐れているときに貪欲であれ」",
        "size": "xxs", "color": "#AAAAAA", "wrap": True, "margin": "lg"
    }

    extra_contents = [
        {"type": "separator", "margin": "md"},
        {"type": "box", "layout": "horizontal", "contents": marker_boxes, "spacing": "xs", "margin": "md"},
        {"type": "box", "layout": "horizontal", "contents": bar_boxes, "spacing": "xs", "alignItems": "center"},
        {"type": "box", "layout": "horizontal", "contents": icon_boxes, "spacing": "xs", "margin": "sm"},
        {"type": "box", "layout": "vertical", "contents": legend_boxes, "margin": "lg"},
        buffett_box
    ]

    return create_flex_bubble(
        "🇺🇸 Fear & Greed Index 🧭", current_color, title_structures, desc,
        footer_text="🔗 ソース: CNN Markets",
        extra_contents=extra_contents,
        footer_url="https://edition.cnn.com/markets/fear-and-greed"
    )

# ==========================================
# 5. カルーセル一括送信処理
# ==========================================
def send_carousel_message(bubbles):
    if not bubbles: return False
    if not LINE_ACCESS_TOKEN:
        print("❌ LINE_ACCESS_TOKEN が設定されていません。")
        return False

    if len(bubbles) > 10:
        print(f"⚠️ 大量通知ストッパー作動: バブル数が {len(bubbles)} 件のため送信を一時停止します。")
        return False

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
    
    if DEBUG_MODE:
        if not LINE_USER_ID: return False
        url = "https://api.line.me/v2/bot/message/push"
        payload["to"] = LINE_USER_ID
        target_name = "開発者のみ（Push送信）"
    else:
        url = "https://api.line.me/v2/bot/message/broadcast"
        target_name = "全員一括（ブロードキャスト送信）"

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        if res.status_code == 200:
            print(f"🚀 LINE カルーセル送信成功！（対象: {target_name} / バブル数: {len(bubbles)}）")
            return True
        else:
            print(f"❌ LINE配信失敗: {res.status_code} - {res.text}")
            return False
    except Exception as e:
        print(f"❌ LINE送信エラー: {e}")
        return False

# ==========================================
# 6. メイン処理
# ==========================================
def main():
    jst = timezone(timedelta(hours=9))
    now_jst = datetime.now(jst)
    bubbles = []

    print(f"🤖 チェック開始... (JST: {now_jst.strftime('%Y/%m/%d %H:%M')} / DEBUG_MODE={DEBUG_MODE})")

    # ==========================================
    # ★ テスト専用：週間指標を強制テスト表示
    # ==========================================
    if DEBUG_MODE:
        print("🛠️ テストモード稼働中：週間指標追加の表示確認を行います。")
        b_weekly = get_weekly_gmo_bubble(now_jst)
        if b_weekly: bubbles.append(b_weekly)
        
        if bubbles:
            send_carousel_message(bubbles)
        else:
            print("エラー: 週間指標データが見つかりません。")
        return

    today_wd = now_jst.weekday()
    now_hour = now_jst.hour

    if today_wd == 5:
        print("☕ 土曜日のためチェックをスキップします。")
    elif today_wd == 6:
        if not is_sunday_already_notified(now_jst):
            b_margin = get_margin_bubble()
            if b_margin: bubbles.append(b_margin)
            
            # ★ 新機能: 日曜日に来週分の指標を追加
            b_weekly = get_weekly_gmo_bubble(now_jst)
            if b_weekly: bubbles.append(b_weekly)
        else:
            print("🟢 日曜通知：本日すでに通知済みのためスキップします。")
    elif now_hour == 8:
        if not is_morning_already_notified(now_jst):
            if is_japanese_holiday(now_jst):
                print("🇯🇵 日本祝日のため朝の通知をスキップします。")
            else:
                b_sq = get_sq_bubble(now_jst)
                b_margin = get_margin_bubble()
                b_anomaly = get_anomaly_bubble(now_jst)
                b_touraku = get_updown_ratio_bubble(check_threshold=True)
                if b_sq: bubbles.append(b_sq)
                if b_margin: bubbles.append(b_margin)
                if b_anomaly: bubbles.append(b_anomaly)
                if b_touraku: bubbles.append(b_touraku)
        else:
            print("🟢 朝の通知：本日すでに通知済みのためスキップします。")
    elif 16 <= now_hour <= 19:
        if is_us_holiday(now_jst):
            b_us_holiday = get_us_holiday_bubble(now_jst)
            if b_us_holiday: bubbles.append(b_us_holiday)
    elif now_hour >= 20:
        if not is_night_already_notified(now_jst):
            
            if not is_japanese_holiday(now_jst):
                b_touraku = get_updown_ratio_bubble(check_threshold=False)
                if b_touraku: bubbles.append(b_touraku)

            if not is_us_holiday(now_jst):
                b_fomc = get_fomc_bubble(now_jst)
                b_gmo = get_gmo_bubble()
                b_fgi = get_fgi_bubble()
                if b_fomc: bubbles.append(b_fomc)
                if b_gmo: bubbles.append(b_gmo)
                if b_fgi: bubbles.append(b_fgi)
        else:
            print("🟢 夜の通知：本日すでに通知済みのためスキップします。")

    if bubbles:
        success = send_carousel_message(bubbles)
        if success:
            if today_wd == 6:
                mark_sunday_as_notified(now_jst)
            elif now_hour == 8:
                mark_morning_as_notified(now_jst)
            elif 16 <= now_hour <= 19:
                if any("米国市場 休場のお知らせ" in str(b) for b in bubbles):
                    mark_us_holiday_as_notified(now_jst)
            elif now_hour >= 20:
                mark_night_as_notified(now_jst)
    else:
        print("🟢 本日は通知対象のイベント・更新はありませんでした。")

if __name__ == "__main__":
    main()
