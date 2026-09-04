import os
import re
import time
from datetime import datetime, date, timedelta, timezone
import requests
from bs4 import BeautifulSoup
import json # ★Flex Message生成用に必須

# ==========================================
# 1. 設定情報
# ==========================================
LINE_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN")
LINE_USER_ID = os.environ.get("LINE_USER_ID")  # ★ 開発者の個別テスト用ID

# ★ テスト実行用安全スイッチ（Trueの時は開発者のみにPush通知する）
DEBUG_MODE = True 

THRES_DANGER = -10.0
THRES_RECOVERY = 0.0

# ==========================================
# 2. 祝日判定ロジック (日本 & アメリカ)
# ==========================================
def is_japanese_holiday(dt_jst):
    """日本の祝日および東証の年末年始休業日の判定"""
    today_date = dt_jst.date()
    year = today_date.year
    month = today_date.month
    day = today_date.day
    weekday = today_date.weekday() # 0=月曜日

    if (month == 12 and day == 31) or (month == 1 and day <= 3):
        return True

    fixed_holidays = [
        (1, 1), (2, 11), (2, 23), (4, 29), (5, 3),
        (5, 4), (5, 5), (8, 11), (11, 3), (11, 23),
    ]

    vernal_equinox = 20 if (year % 4 == 0 or year % 4 == 1) else 21
    fixed_holidays.append((3, vernal_equinox))

    autumnal_equinox = 22 if (year % 4 == 0 or year % 4 == 1) else 23
    fixed_holidays.append((9, autumnal_equinox))

    if (month, day) in fixed_holidays:
        return True

    if weekday == 0:
        if month == 1 and 8 <= day <= 14:
            return True
        if month == 7 and 15 <= day <= 21:
            return True
        if month == 9 and 15 <= day <= 21:
            return True
        if month == 10 and 8 <= day <= 14:
            return True

    if weekday == 0:
        yesterday = today_date - timedelta(days=1)
        if (yesterday.month, yesterday.day) in fixed_holidays:
            return True

    return False

def is_us_holiday(dt_jst):
    """米国株式市場の主要休場日判定"""
    today_date = dt_jst.date()
    month = today_date.month
    day = today_date.day
    weekday = today_date.weekday()

    if (month == 1 and day == 1) or (month == 6 and day == 19) or \
       (month == 7 and day == 4) or (month == 12 and day == 25):
        return True

    if weekday == 0:
        if month == 1 and 15 <= day <= 21:
            return True
        if month == 2 and 15 <= day <= 21:
            return True
        if month == 5 and 25 <= day <= 31:
            return True
        if month == 9 and 1 <= day <= 7:
            return True

    if weekday == 3 and month == 11 and 22 <= day <= 28:
        return True

    return False

# ==========================================
# 3. SQ日判定ロジック
# ==========================================
def get_sq_date_for_month(year, month):
    first_day = date(year, month, 1)
    days_to_first_friday = (4 - first_day.weekday()) % 7
    second_friday = first_day + timedelta(days=days_to_first_friday + 7)

    target_sq_date = second_friday
    while True:
        dt_check = datetime(target_sq_date.year, target_sq_date.month, target_sq_date.day, tzinfo=timezone(timedelta(hours=9)))
        if target_sq_date.weekday() in [5, 6] or is_japanese_holiday(dt_check):
            target_sq_date -= timedelta(days=1)
        else:
            break
    return target_sq_date

def get_sq_info(dt_jst):
    today_date = dt_jst.date()
    year = dt_jst.year
    month = dt_jst.month
    current_sq_date = get_sq_date_for_month(year, month)

    if month == 12:
        next_sq_date = get_sq_date_for_month(year + 1, 1)
    else:
        next_sq_date = get_sq_date_for_month(year, month + 1)

    if today_date == current_sq_date:
        return True, (month in [3, 6, 9, 12])
    elif today_date == next_sq_date:
        next_month = 1 if month == 12 else month + 1
        return True, (next_month in [3, 6, 9, 12])

    return False, False

def check_and_send_sq_notice(dt_jst):
    is_sq, is_major = get_sq_info(dt_jst)
    if not is_sq:
        print("🟢 本日はSQ日ではありません。")
        return

    today_str = dt_jst.strftime('%Y/%m/%d')
    if is_major:
        title = "🚨🔥 【本日『メジャーSQ』通過日！】 🔥🚨"
        meaning = "【メジャーSQとは？】\n「日経225先物」と「オプション取引」の満期決済日が重なる特別に重要な日です（3・6・9・12月）。\n機関投資家の巨額なポジション調整が一斉に行われるため、売買高が跳ね上がります。"
        warning = "⚠️ 【価格変動・乱高下に厳重警戒！】\n特に朝9:00の寄り付き前後を中心に、思惑が交錯して株価が突発的に上下へ大きくブレる傾向があります。\n無理な飛び乗りや高値掴みには十分注意し、慎重な取引を心がけましょう！"
    else:
        title = "⚠️📢 【本日『SQ（SQ算出日）』です】 📢⚠️"
        meaning = "【SQ（SQ算出日）とは？】\n主に「日経225オプション取引」の満期決済日です（毎月第2金曜日周辺）。\nSQ値を算出するため、朝方に買い戻しや売り決済の注文が集中します。"
        warning = "⚠️ 【寄り付き前後の値動きに注意】\n朝9:00の相場開始時を中心に、一時的に価格変動が大きくなる場合があります。\n思わぬ板の急変に備えて、指値管理などを丁寧に行いましょう。"

    msg = f"{title}\n📅 日付: {today_str}\n━━━━━━━━━━━━━━━\n\n{meaning}\n\n{warning}"
    print(f"🚀 SQ通知を配信します（メジャーSQ: {is_major}）")
    send_line_message(msg)

# ==========================================
# 4. FOMC判定ロジック
# ==========================================
def check_and_send_fomc_notice(dt_jst):
    today_date = dt_jst.date()
    fomc_announcement_dates = [
        date(2026, 1, 29), date(2026, 3, 19), date(2026, 5, 7),
        date(2026, 6, 18), date(2026, 7, 30), date(2026, 9, 17),
        date(2026, 10, 29), date(2026, 12, 10),
        date(2027, 1, 28), date(2027, 3, 18), date(2027, 5, 6),
        date(2027, 6, 17), date(2027, 7, 29), date(2027, 9, 16),
        date(2027, 11, 4), date(2027, 12, 16),
    ]
    tomorrow_date = today_date + timedelta(days=1)

    if tomorrow_date in fomc_announcement_dates:
        title = "🏛️🇺🇸 【最重要イベント：今夜『FOMC政策金利発表』！】"
        details = "【FOMC（米連邦公開市場委員会）とは？】\n米国の金利方針を決定する最高意思決定会合です。\n日本時間の本日深夜（午前3:00〜4:00頃）に政策金利と声明文が発表され、パウエルFRB議長の記者会見が行われます。"
        warning = "⚠️ 【全世界の市場・為替が激変する警戒夜！】\n発表前後でドル円（為替）や米国株、日経先物が激しく乱高下する可能性が非常に高くなります。\n夜間のポジション持ち越しには十分ご注意ください！"
        msg = f"{title}\n📅 発表予定: 日本時間 今夜深夜（明日 {tomorrow_date.strftime('%m/%d')} 未明）\n━━━━━━━━━━━━━━━\n\n{details}\n\n{warning}"
        print("🚀 FOMC事前リマインド通知を配信します。")
        send_line_message(msg)
    else:
        print("🟢 今夜はFOMC発表の前夜ではありません。")

# ==========================================
# 4.5 季節的アノマリー判定・通知機能 (★Flex Message対応)
# ==========================================
def check_and_send_anomaly_notice(dt_jst):
    today_date = dt_jst.date()
    month = today_date.month
    day = today_date.day

    anomaly_icon = ""
    anomaly_title = ""
    anomaly_desc = ""

    # A. 月初（第1営業日）の判定
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
            anomaly_icon, anomaly_title = "🎍", "1月効果 (January Effect)"
            anomaly_desc = "昨年末の節税売りの反動や新規資金流入により、特に中小型株が上昇しやすい傾向があります！大発会以降の動きに注目です。"
        elif month == 4:
            anomaly_icon, anomaly_title = "💼", "新年度入り・ニューマネー"
            anomaly_desc = "新年度を迎え、機関投資家からの新規資金が市場に入りやすい時期です。例年、4月はパフォーマンスが良い傾向があります。"
        elif month == 5:
            anomaly_icon, anomaly_title = "🎏", "警戒：セル・イン・メイ"
            anomaly_desc = "「5月に株を売れ」の有名な格言です。\n例年5〜10月は株価が下落・停滞しやすい時期のため、ポジション調整やリスク管理を意識しましょう。"
        elif month == 7:
            anomaly_icon, anomaly_title = "🏄", "サマーラリー"
            anomaly_desc = "7月はボーナス資金の流入などで一時的に相場が上昇しやすく、強含みしやすい傾向があります。"
        elif month == 8:
            anomaly_icon, anomaly_title = "🌻", "警戒：夏枯れ相場"
            anomaly_desc = "8月はお盆や海外勢の夏休みで市場参加者が減り、商いが薄くなります。少しの売りで突発的な急落（ボラティリティ増大）が起きやすいため十分注意してください。"

    # B. 特殊日（変動祝日・イベント）
    if month == 9:
        first_day_of_sept = date(today_date.year, 9, 1)
        days_to_monday = (0 - first_day_of_sept.weekday()) % 7
        labor_day = first_day_of_sept + timedelta(days=days_to_monday)
        post_labor_day = labor_day + timedelta(days=1)
        if today_date == post_labor_day:
            anomaly_icon, anomaly_title = "🍂", "警戒：9月効果 (September Effect)"
            anomaly_desc = "レイバーデイ明けで機関投資家が市場に本格復帰します。\n秋に向けたポジション調整や決算前の節税売りが出やすく、年間で最も株価が下落しやすい警戒時期のスタートです。"

    elif month == 11:
        first_day_of_nov = date(today_date.year, 11, 1)
        days_to_thursday = (3 - first_day_of_nov.weekday()) % 7
        thanksgiving = first_day_of_nov + timedelta(days=days_to_thursday + 21)
        thanksgiving_eve = thanksgiving - timedelta(days=1)
        if today_date == thanksgiving_eve:
            anomaly_icon, anomaly_title = "🦃", "サンクスギビング・ラリー"
            anomaly_desc = "明日の米国感謝祭から週末の「ブラックフライデー」にかけて、年末商戦への期待感から米国株が上がりやすい期間に入ります！\n市場は祝日モードで商いが薄くなるため、突発的な動きにもご注意ください。"

    # C. 日付固定
    if month == 3 and day == 15:
        anomaly_icon, anomaly_title = "🌸", "期末の需給・お化粧買い"
        anomaly_desc = "3月末に向けて、配当権利取りや機関投資家による決算対策の買いが入りやすく、底堅い展開になりやすい時期です。"
    elif month == 10 and day == 28:
        anomaly_icon, anomaly_title = "🎃", "ハロウィン効果"
        anomaly_desc = "10月末に買い、翌春（4〜5月）に売るとリターンが高くなりやすいとされる時期です。秋は歴史的に底値になりやすい仕込み時です。"
    elif month == 12 and day == 15:
        anomaly_icon, anomaly_title = "❄️", "警戒：節税売りピーク"
        anomaly_desc = "年末に向けて、税金対策のための「含み損株の売却（節税売り）」が出やすい時期です。需給悪化に注意しましょう。"
    elif month == 12 and day == 24:
        anomaly_icon, anomaly_title = "🎅", "サンタクロースラリー"
        anomaly_desc = "年の最後の5営業日から新年最初の2営業日にかけて、株価が上昇しやすい期間に入ります！"

    if anomaly_title:
        print(f"🚀 アノマリー通知（Flex Message）を配信します: {anomaly_title}")
        send_flex_anomaly_message(anomaly_icon, anomaly_title, anomaly_desc)
    else:
        print("🟢 本日はアノマリー通知日ではありません。")


# ==========================================
# 5. LINE 送信関数
# ==========================================
def send_line_message(text):
    """従来のテキスト送信用モジュール"""
    if not LINE_ACCESS_TOKEN:
        print("❌ LINE_ACCESS_TOKEN が設定されていません。")
        return

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}",
    }

    if DEBUG_MODE:
        if not LINE_USER_ID: return
        url = "https://api.line.me/v2/bot/message/push"
        payload = {"to": LINE_USER_ID, "messages": [{"type": "text", "text": f"🛠️【テスト送信】\n\n{text}"}]}
    else:
        url = "https://api.line.me/v2/bot/message/broadcast"
        payload = {"messages": [{"type": "text", "text": text}]}

    try:
        requests.post(url, headers=headers, json=payload, timeout=10)
        print("🚀 LINEテキスト送信成功！")
    except Exception as e:
        print(f"❌ LINE送信エラー: {e}")


def send_flex_anomaly_message(icon, title, desc):
    """アノマリー専用のリッチなカード型（Flex Message）送信用モジュール"""
    if not LINE_ACCESS_TOKEN:
        return

    # ★ 空間を有効活用し、折り返し（wrap: true）を設定したFlex MessageのJSON設計
    flex_contents = {
        "type": "bubble",
        "styles": {
            "header": {"backgroundColor": "#2C3E50"} # 紺色のヘッダー帯
        },
        "header": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "12px",
            "contents": [
                {
                    "type": "text",
                    "text": "🗓️ 相場カレンダー（季節性）",
                    "color": "#FFFFFF",
                    "weight": "bold",
                    "size": "xs"
                }
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "md",
            "paddingAll": "20px",
            "contents": [
                {
                    "type": "text",
                    "text": f"{icon} {title}",
                    "weight": "bold",
                    "size": "md",
                    "wrap": True,
                    "color": "#e74c3c" if "警戒" in title else "#111111"
                },
                {
                    "type": "separator",
                    "margin": "md"
                },
                {
                    "type": "text",
                    "text": desc,
                    "wrap": True,
                    "size": "sm",
                    "color": "#333333",
                    "margin": "md"
                }
            ]
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "15px",
            "contents": [
                {
                    "type": "text",
                    "text": "※アノマリーは経験則であり、必ずしもその通りに動くとは限りません。一つの目安としてご活用ください。",
                    "wrap": True,
                    "size": "xxs",
                    "color": "#999999"
                }
            ]
        }
    }

    message_payload = {
        "type": "flex",
        "altText": f"相場アノマリー通知: {title}",
        "contents": flex_contents
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}",
    }

    if DEBUG_MODE:
        if not LINE_USER_ID: return
        url = "https://api.line.me/v2/bot/message/push"
        payload = {"to": LINE_USER_ID, "messages": [message_payload]}
    else:
        url = "https://api.line.me/v2/bot/message/broadcast"
        payload = {"messages": [message_payload]}

    try:
        requests.post(url, headers=headers, json=payload, timeout=10)
        print("🚀 LINE Flex Message送信成功！")
    except Exception as e:
        print(f"❌ LINE Flex送信エラー: {e}")

# ==========================================
# 6. 恐怖と欲望指数 / 7. 信用評価損益率 / 8. 米国重要指標
# ==========================================
# (※文字数削減と既存ロジック保護のため、処理内容は変更せずそのまま配置しています)

def check_and_send_fear_greed():
    print("🌐 CNN Fear & Greed IndexのデータAPIへアクセスします...")
    api_url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    headers = {"User-Agent": "Mozilla/5.0"}
    score = None
    rating = ""
    try:
        res = requests.get(api_url, headers=headers, timeout=15)
        if res.status_code == 200:
            data = res.json()
            score = int(round(data.get("fear_and_greed", {}).get("score", 0)))
            rating = data.get("fear_and_greed", {}).get("rating", "Neutral")
    except:
        pass
    if score is None:
        try:
            web_url = "https://edition.cnn.com/markets/fear-and-greed"
            res = requests.get(web_url, headers=headers, timeout=15)
            match = re.search(r'"score":\s*([\d\.]+)', res.text)
            if match:
                score = int(round(float(match.group(1))))
                rating = "Neutral"
        except: return
    if score is None: return

    if score <= 10:
        title, expression = "💀🔥 【超絶大バーゲンセール！ (Extreme Fear ≤ 10)】 🔥💀", "市場は歴史的な大パニック状態です！！\n😱 身の毛もよだつ最大の恐怖に打ち勝った者だけが、将来の大金を手に入れられる……！！\n千載一遇の超絶買い場到来か！？"
    elif score <= 24:
        title, expression = "😱🚨 【キャー！極度の恐怖 (Extreme Fear)】 🚨😱", "市場は極限のパニック状態です！！\nみんなが恐怖で逃げ出しています💦 バーゲンセールか、底なし沼か……！？"
    elif score <= 44:
        title, expression = "😨⚠️ 【恐怖モード (Fear)】 ⚠️😨", "市場には弱気なムードが漂っています。\n慎重な立ち回りが求められる警戒エリアです！"
    elif score <= 55:
        title, expression = "😐⚖️ 【中立・平穏 (Neutral)】 ⚖️😐", "市場はきわめて冷静です。\n嵐の前の静けさか、方向感を探る展開が続いています。"
    elif score <= 75:
        title, expression = "😃🚀 【強気モード！ (Greed)】 🚀😃", "市場は強気ムード上昇中！！\n買いの勢いがついています。この波に乗っていきましょう！"
    else:
        title, expression = "🤩🔥 【超イケイケ激熱発狂モード！！ (Extreme Greed)】 🔥🤩", "市場は熱狂の渦！絶好調のイケイケ状態です！！\n過熱感バツグン！高値掴みには注意しつつノリノリで行きましょう！"
    
    m0 = "[★]" if score <= 10 else "[  ]"
    m1 = "[★]" if 11 <= score <= 24 else "[  ]"
    m2 = "[★]" if 25 <= score <= 44 else "[  ]"
    m3 = "[★]" if 45 <= score <= 55 else "[  ]"
    m4 = "[★]" if 56 <= score <= 75 else "[  ]"
    m5 = "[★]" if score >= 76 else "[  ]"

    msg = f"🧭 Fear & Greed Index（恐怖と欲望指数）\n\n{title}\n━━━━━━━━━━━━━━━\n📊 現在のスコア: 【 {score} / 100 】\n📝 判定: {rating.upper()}\n━━━━━━━━━━━━━━━\n\n{expression}\n\n🔗 詳細:\nhttps://edition.cnn.com/markets/fear-and-greed\n\n💡 【スコアの目安】\n{m0} 0〜10：超絶買い場\n{m1} 11〜24：極度の恐怖\n{m2} 25〜44：恐怖\n{m3} 45〜55：中立・平穏\n{m4} 56〜75：強気モード\n{m5} 76〜100：超イケイケ"
    send_line_message(msg)

def check_margin_evaluation():
    try:
        url = "https://www.traders.co.jp/margin_derivatives/margin_transition"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")
        latest_date, latest_value = "", None
        for row in soup.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) >= 11:
                date_str = cells[0].get_text(strip=True)
                if "/" in date_str and len(date_str) == 10:
                    eval_str = cells[9].get_text(strip=True)
                    if eval_str not in ["-", "－"]:
                        try:
                            latest_value = float(eval_str)
                            latest_date = date_str
                            break
                        except: continue
        if latest_value is not None:
            jst = timezone(timedelta(hours=9))
            now_test = datetime.now(jst)
            is_sunday = (now_test.weekday() == 6)
            is_danger, is_recovery = latest_value <= THRES_DANGER, latest_value >= THRES_RECOVERY
            if is_sunday or is_danger or is_recovery:
                if is_danger: title, status_text = "⚠️🚨 【信用評価損益率：危険水域到達】 🚨⚠️", "追証発生や投げ売り（追い込まれた個人の投げ）の危険が高まっています。"
                elif is_recovery: title, status_text = "🎉📈 【信用評価損益率：プラス圏浮上】 📈🎉", "個人投資家の損益がプラスに転じました！"
                else: title, status_text = "📊 【日曜日：信用評価損益率 定期報告】", "現在、正常範囲内（平穏）です。"
                msg = f"{title}\n━━━━━━━━━━━━━━━\n📅 日付: {latest_date}\n📉 評価損益率: 【 {latest_value}% 】\n━━━━━━━━━━━━━━━\n\n{status_text}\n\n🔗 推移データ:\nhttps://www.traders.co.jp/margin_derivatives/margin_transition"
                send_line_message(msg)
    except: pass

def check_gaikaex_economy_index():
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
            if any(p in row_text for p in [f"{m_str}/{d_str}", f"{m_z}/{d_z}", f"{m_str}月{d_str}日", f"{m_z}月{d_z}日"]): current_is_today = True
            elif any(re.search(r"\d{1,2}/\d{1,2}|\d{1,2}月\d{1,2}日", row_text) for _ in [1]):
                if current_is_today and not any(p in row_text for p in [f"{m_str}/{d_str}", f"{m_z}/{d_z}"]): current_is_today = False
            if not current_is_today: continue
            is_us = "アメリカ" in row_text or "米国" in row_text
            if not is_us:
                for img in row.find_all("img"):
                    alt = (img.get("alt", "") + img.get("title", "") + img.get("src", "")).lower()
                    if "アメリカ" in alt or "米国" in alt or "us" in alt: is_us = True; break
            if not is_us: continue
            if ("★★★" in row_text or "★3" in row_text or re.search(r"star[_-]?3|rank[_-]?3|level[_-]?3", row_html, re.I) or row_html.count("star") >= 3):
                time_match = re.search(r"\d{2}:\d{2}", row_text)
                time_str = time_match.group(0) if time_match else "時間未定"
                name_str = ""
                link_elem = row.find("a")
                if link_elem and len(link_elem.get_text(strip=True)) > 2: name_str = link_elem.get_text(strip=True)
                else:
                    for td in row.find_all("td"):
                        txt = td.get_text(strip=True)
                        if len(txt) > 3 and not txt.endswith("%") and ":" not in txt and "アメリカ" not in txt: name_str = txt; break
                if name_str:
                    evt = f"⏰ {time_str} | {name_str}"
                    if evt not in target_events: target_events.append(evt)
        if target_events:
            if len(target_events) > 10: return
            msg = f"🇺🇸 【GMO証券：本日発表の米国★★★ 注目指標】\n📅 {today.strftime('%Y/%m/%d')}\n\n" + "\n".join(target_events) + f"\n\n📊 経済指標カレンダー:\n{gaikaex_url}"
            send_line_message(msg)
    except: pass

# ==========================================
# 9. メイン処理
# ==========================================
def main():
    jst = timezone(timedelta(hours=9))
    
    # ★ テスト用: 実行時刻を「2026年11月25日（水）朝8:00 (サンクスギビング前日)」に偽装
    now_jst = datetime(2026, 11, 25, 8, 0, tzinfo=jst)
    
    # ----------------------------------------------------------------------
    # ⚠️ 【重要: 本番運用への戻し方】
    # テストが完了したら、必ず以下の手順で通常のスケジュール動作に戻してください。
    # 
    # 1. 14行目の `DEBUG_MODE = True` を `DEBUG_MODE = False` に変更する。
    # 2. 上記のテスト用 `now_jst = ...` の行を消す（または # をつけてコメントアウト）。
    # 3. 以下の # を外して、現在時刻を取得するコードを有効にする。
    # ----------------------------------------------------------------------
    # now_jst = datetime.now(jst)
    
    today_wd = now_jst.weekday()
    now_hour = now_jst.hour

    print(f"🤖 チェック開始... (テスト実行: 偽装日時 {now_jst.strftime('%Y/%m/%d %H:%M')} 扱いで実行)")

    if today_wd == 5:
        return

    if today_wd == 6:
        check_margin_evaluation()
        check_and_send_fear_greed()
    elif now_hour == 8:
        if not is_japanese_holiday(now_jst):
            check_and_send_sq_notice(now_jst)
            check_margin_evaluation()
            check_and_send_anomaly_notice(now_jst) # Flex Messageで送信されます
    else:
        if not is_us_holiday(now_jst):
            check_and_send_fomc_notice(now_jst)
            check_gaikaex_economy_index()
            check_and_send_fear_greed()

if __name__ == "__main__":
    main()
