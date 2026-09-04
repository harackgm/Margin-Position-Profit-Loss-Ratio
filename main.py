import os
import re
import time
from datetime import datetime, date, timedelta, timezone
import requests
from bs4 import BeautifulSoup

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
# 3. SQ日判定ロジック (祝日・前倒し・月跨ぎ自動対応)
# ==========================================
def get_sq_date_for_month(year, month):
    """指定された年月における実際のSQ日（祝日・休日考慮済み）を返す"""
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
    """指定日がSQ日かどうか、およびメジャーSQかどうかを判定する"""
    today_date = dt_jst.date()
    year = dt_jst.year
    month = dt_jst.month

    current_sq_date = get_sq_date_for_month(year, month)

    if month == 12:
        next_sq_date = get_sq_date_for_month(year + 1, 1)
    else:
        next_sq_date = get_sq_date_for_month(year, month + 1)

    if today_date == current_sq_date:
        is_major = (month in [3, 6, 9, 12])
        return True, is_major
    elif today_date == next_sq_date:
        next_month = 1 if month == 12 else month + 1
        is_major = (next_month in [3, 6, 9, 12])
        return True, is_major

    return False, False

def check_and_send_sq_notice(dt_jst):
    """SQ日の場合にLINEで注意喚起を送信"""
    is_sq, is_major = get_sq_info(dt_jst)

    if not is_sq:
        print("🟢 本日はSQ日ではありません。")
        return

    today_str = dt_jst.strftime('%Y/%m/%d')

    if is_major:
        title = "🚨🔥 【本日『メジャーSQ』通過日！】 🔥🚨"
        meaning = (
            "【メジャーSQとは？】\n"
            "「日経225先物」と「オプション取引」の満期決済日が重なる特別に重要な日です（3・6・9・12月）。\n"
            "機関投資家の巨額なポジション調整が一斉に行われるため、売買高が跳ね上がります。"
        )
        warning = (
            "⚠️ 【価格変動・乱高下に厳重警戒！】\n"
            "特に朝9:00の寄り付き前後を中心に、思惑が交錯して株価が突発的に上下へ大きくブレる傾向があります。\n"
            "無理な飛び乗りや高値掴みには十分注意し、慎重な取引を心がけましょう！"
        )
    else:
        title = "⚠️📢 【本日『SQ（SQ算出日）』です】 📢⚠️"
        meaning = (
            "【SQ（SQ算出日）とは？】\n"
            "主に「日経225オプション取引」の満期決済日です（毎月第2金曜日周辺）。\n"
            "SQ値を算出するため、朝方に買い戻しや売り決済の注文が集中します。"
        )
        warning = (
            "⚠️ 【寄り付き前後の値動きに注意】\n"
            "朝9:00の相場開始時を中心に、一時的に価格変動が大きくなる場合があります。\n"
            "思わぬ板の急変に備えて、指値管理などを丁寧に行いましょう。"
        )

    msg = (
        f"{title}\n"
        f"📅 日付: {today_str}\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"{meaning}\n\n"
        f"{warning}"
    )

    print(f"🚀 SQ通知を配信します（メジャーSQ: {is_major}）")
    send_line_message(msg)

# ==========================================
# 4. FOMC（米連邦公開市場委員会）判定ロジック
# ==========================================
def check_and_send_fomc_notice(dt_jst):
    """FOMC政策金利発表直前となる『水曜日夜』にリマインド送信"""
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
        details = (
            "【FOMC（米連邦公開市場委員会）とは？】\n"
            "米国の金利方針を決定する最高意思決定会合です。\n"
            "日本時間の本日深夜（午前3:00〜4:00頃）に政策金利と声明文が発表され、パウエルFRB議長の記者会見が行われます。"
        )
        warning = (
            "⚠️ 【全世界の市場・為替が激変する警戒夜！】\n"
            "発表前後でドル円（為替）や米国株、日経先物が激しく乱高下する可能性が非常に高くなります。\n"
            "夜間のポジション持ち越しには十分ご注意ください！"
        )

        msg = (
            f"{title}\n"
            f"📅 発表予定: 日本時間 今夜深夜（明日 {tomorrow_date.strftime('%m/%d')} 未明）\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"{details}\n\n"
            f"{warning}"
        )
        print("🚀 FOMC事前リマインド通知を配信します。")
        send_line_message(msg)
    else:
        print("🟢 今夜はFOMC発表の前夜ではありません。")

# ==========================================
# 4.5 季節的アノマリー判定・通知機能
# ==========================================
def check_and_send_anomaly_notice(dt_jst):
    """特定の日付や営業日に季節的アノマリー（相場の経験則）を通知する"""
    today_date = dt_jst.date()
    month = today_date.month
    day = today_date.day

    msg_body = None

    # ---------------------------------------------
    # A. 月初（第1営業日）のアノマリー判定
    # ---------------------------------------------
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
            msg_body = "🎍 【アノマリー：1月効果 (January Effect)】\n昨年末の節税売りの反動や新規資金流入により、特に中小型株が上昇しやすい傾向があります！大発会以降の動きに注目です。"
        elif month == 4:
            msg_body = "💼 【アノマリー：新年度入り・ニューマネー】\n新年度を迎え、機関投資家からの新規資金が市場に入りやすい時期です。例年、4月はパフォーマンスが良い傾向があります。"
        elif month == 5:
            msg_body = "🎏 【アノマリー警戒：セル・イン・メイ (Sell in May)】\n「5月に株を売れ」の格言通り、例年5〜10月は株価が下落・停滞しやすい時期です。ポジション調整やリスク管理を意識しましょう。"
        elif month == 7:
            msg_body = "🏄 【アノマリー：サマーラリー】\n7月はボーナス資金の流入などで一時的に相場が上昇しやすく、強含みしやすい傾向があります。"
        elif month == 8:
            msg_body = "🌻 【アノマリー警戒：夏枯れ相場】\n8月はお盆や海外勢の夏休みで市場参加者が減り、商いが薄くなります。突発的な急落（ボラティリティ増大）に十分注意してください。"

    # ---------------------------------------------
    # B. 特殊日（変動祝日・イベント）のアノマリー判定
    # ---------------------------------------------
    if month == 9:
        # 9月の第1月曜日（レイバーデイ）の翌日（火曜日）
        first_day_of_sept = date(today_date.year, 9, 1)
        days_to_monday = (0 - first_day_of_sept.weekday()) % 7
        labor_day = first_day_of_sept + timedelta(days=days_to_monday)
        post_labor_day = labor_day + timedelta(days=1)
        
        if today_date == post_labor_day:
            msg_body = "🍂 【アノマリー警戒：9月効果 (September Effect)】\nレイバーデイ明けで機関投資家が市場に本格復帰します。秋に向けたポジション調整や決算前の節税売りが出やすく、年間で最も株価が下落しやすい警戒時期のスタートです。"

    elif month == 11:
        # 11月の第4木曜日（サンクスギビング）の前日（水曜日）
        first_day_of_nov = date(today_date.year, 11, 1)
        days_to_thursday = (3 - first_day_of_nov.weekday()) % 7
        thanksgiving = first_day_of_nov + timedelta(days=days_to_thursday + 21)
        thanksgiving_eve = thanksgiving - timedelta(days=1)
        
        if today_date == thanksgiving_eve:
            msg_body = "🦃 【アノマリー：サンクスギビング・ラリー】\n明日の米国感謝祭から週末の「ブラックフライデー」にかけて、年末商戦への期待感から米国株が上がりやすい期間に入ります！市場は祝日モードで商いが薄くなるため、突発的な動きにもご注意ください。"

    # ---------------------------------------------
    # C. 日付固定のアノマリー判定
    # ---------------------------------------------
    if month == 3 and day == 15:
        msg_body = "🌸 【アノマリー：期末の需給・お化粧買い】\n3月末に向けて、配当権利取りや機関投資家による決算対策の買いが入りやすく、底堅い展開になりやすい時期です。"
    elif month == 10 and day == 28:
        msg_body = "🎃 【アノマリー：ハロウィン効果】\n10月末に買い、翌春（4〜5月）に売るとリターンが高くなりやすいとされる時期です。秋は歴史的に底値になりやすい仕込み時です。"
    elif month == 12 and day == 15:
        msg_body = "❄️ 【アノマリー警戒：節税売りピーク】\n年末に向けて、税金対策のための「含み損株の売却（節税売り）」が出やすい時期です。需給悪化に注意しましょう。"
    elif month == 12 and day == 24:
        msg_body = "🎅 【アノマリー：サンタクロースラリー】\n年の最後の5営業日から新年最初の2営業日にかけて、株価が上昇しやすい期間に入ります！"

    if msg_body:
        full_msg = (
            f"🗓️ 【相場アノマリー（季節性）通知】\n\n"
            f"{msg_body}\n\n"
            f"━━━━━━━━━━━━━━━\n"
            f"※アノマリーは経験則であり、必ずしもその通りに動くとは限りません。一つの目安としてご活用ください。"
        )
        print("🚀 アノマリー通知を配信します。")
        send_line_message(full_msg)
    else:
        print("🟢 本日はアノマリー通知日ではありません。")

# ==========================================
# 5. LINE 送信関数 (★ テスト用にPush通知機能を追加)
# ==========================================
def send_line_message(text):
    """通知送信モジュール"""
    if not LINE_ACCESS_TOKEN:
        print("❌ LINE_ACCESS_TOKEN が設定されていません。")
        return

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}",
    }

    if DEBUG_MODE:
        # デバッグモード時は開発者のみへ個別送信（Push API）
        if not LINE_USER_ID:
            print("\n⚠️ 【DEBUG_MODE: ON】 しかし LINE_USER_ID が未設定のため送信できません。ログに出力します。")
            print("▼▼ 送信予定メッセージ ▼▼\n")
            print(text)
            print("\n▲▲▲▲▲▲▲▲▲▲▲▲▲▲\n")
            return
        
        url = "https://api.line.me/v2/bot/message/push"
        payload = {
            "to": LINE_USER_ID,
            "messages": [{"type": "text", "text": f"🛠️【テスト送信】\n\n{text}"}]
        }
        target_name = "開発者のみ（Push一斉送信回避）"
    else:
        # 本番モード（Broadcast API）
        url = "https://api.line.me/v2/bot/message/broadcast"
        payload = {"messages": [{"type": "text", "text": text}]}
        target_name = "全員一括（ブロードキャスト送信）"

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        if res.status_code == 200:
            print(f"🚀 LINE送信成功！（対象: {target_name}）")
        else:
            print(f"❌ LINE配信失敗: {res.status_code} - {res.text}")
    except Exception as e:
        print(f"❌ LINE送信エラー: {e}")

# ==========================================
# 6. 恐怖と欲望指数 (Fear & Greed Index) データ取得＆演出処理
# ==========================================
def check_and_send_fear_greed():
    print("🌐 CNN Fear & Greed IndexのデータAPIへアクセスします...")
    
    api_url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    score = None
    rating = ""

    try:
        res = requests.get(api_url, headers=headers, timeout=15)
        if res.status_code == 200:
            data = res.json()
            fng_data = data.get("fear_and_greed", {})
            score = int(round(fng_data.get("score", 0)))
            rating = fng_data.get("rating", "Neutral")
            print(f"✅ API取得成功！ スコア = {score}, 状態 = {rating}")
    except Exception as e:
        print(f"❌ API通信エラー: {e}")

    if score is None:
        print("🔄 予備手段：Webページから数値を探索します...")
        try:
            web_url = "https://edition.cnn.com/markets/fear-and-greed"
            res = requests.get(web_url, headers=headers, timeout=15)
            match = re.search(r'"score":\s*([\d\.]+)', res.text)
            if match:
                score = int(round(float(match.group(1))))
                rating = "Neutral"
                print(f"✅ 予備取得成功！ スコア = {score}")
        except Exception as e:
            print(f"❌ 予備取得も失敗: {e}")
            return

    if score is None:
        return

    if score <= 10:
        title = "💀🔥 【超絶大バーゲンセール！ (Extreme Fear ≤ 10)】 🔥💀"
        expression = "市場は歴史的な大パニック状態です！！\n😱 身の毛もよだつ最大の恐怖に打ち勝った者だけが、将来の大金を手に入れられる……！！\n千載一遇の超絶買い場到来か！？"
    elif score <= 24:
        title = "😱🚨 【キャー！極度の恐怖 (Extreme Fear)】 🚨😱"
        expression = "市場は極限のパニック状態です！！\nみんなが恐怖で逃げ出しています💦 バーゲンセールか、底なし沼か……！？"
    elif score <= 44:
        title = "😨⚠️ 【恐怖モード (Fear)】 ⚠️😨"
        expression = "市場には弱気なムードが漂っています。\n慎重な立ち回りが求められる警戒エリアです！"
    elif score <= 55:
        title = "😐⚖️ 【中立・平穏 (Neutral)】 ⚖️😐"
        expression = "市場はきわめて冷静です。\n嵐の前の静けさか、方向感を探る展開が続いています。"
    elif score <= 75:
        title = "😃🚀 【強気モード！ (Greed)】 🚀😃"
        expression = "市場は強気ムード上昇中！！\n買いの勢いがついています。この波に乗っていきましょう！"
    else:
        title = "🤩🔥 【超イケイケ激熱発狂モード！！ (Extreme Greed)】 🔥🤩"
        expression = "市場は熱狂の渦！絶好調のイケイケ状態です！！\n過熱感バツグン！高値掴みには注意しつつノリノリで行きましょう！"

    m0 = "[★]" if score <= 10 else "[  ]"
    m1 = "[★]" if 11 <= score <= 24 else "[  ]"
    m2 = "[★]" if 25 <= score <= 44 else "[  ]"
    m3 = "[★]" if 45 <= score <= 55 else "[  ]"
    m4 = "[★]" if 56 <= score <= 75 else "[  ]"
    m5 = "[★]" if score >= 76 else "[  ]"

    msg = (
        f"🧭 Fear & Greed Index（恐怖と欲望指数）\n\n"
        f"{title}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📊 現在のスコア: 【 {score} / 100 】\n"
        f"📝 判定: {rating.upper()}\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"{expression}\n\n"
        f"🔗 詳細:\nhttps://edition.cnn.com/markets/fear-and-greed\n\n"
        f"💡 【スコアの目安】\n"
        f"{m0} 0〜10：超絶買い場\n"
        f"{m1} 11〜24：極度の恐怖\n"
        f"{m2} 25〜44：恐怖\n"
        f"{m3} 45〜55：中立・平穏\n"
        f"{m4} 56〜75：強気モード\n"
        f"{m5} 76〜100：超イケイケ"
    )

    send_line_message(msg)

# ==========================================
# 7. トレーダーズ・ウェブ（信用評価損益率）処理
# ==========================================
def check_margin_evaluation():
    try:
        url = "https://www.traders.co.jp/margin_derivatives/margin_transition"
        print("🌐 トレーダーズ・ウェブにアクセスしています...")

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        res = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")

        rows = soup.find_all("tr")
        latest_date, latest_value = "", None

        for row in rows:
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
                        except ValueError:
                            continue

        print("-" * 30)
        if latest_value is not None:
            print(f"✅ 信用評価損益率 取得成功！ 最新日付: {latest_date}, 値: {latest_value}%")

            jst = timezone(timedelta(hours=9))
            now_test = datetime.now(jst)
            is_sunday = (now_test.weekday() == 6)
            is_danger = latest_value <= THRES_DANGER
            is_recovery = latest_value >= THRES_RECOVERY

            if is_sunday or is_danger or is_recovery:
                if is_danger:
                    title, status_text = "⚠️🚨 【信用評価損益率：危険水域到達】 🚨⚠️", "追証発生や投げ売り（追い込まれた個人の投げ）の危険が高まっています。"
                elif is_recovery:
                    title, status_text = "🎉📈 【信用評価損益率：プラス圏浮上】 📈🎉", "個人投資家の損益がプラスに転じました！"
                else:
                    title, status_text = "📊 【日曜日：信用評価損益率 定期報告】", "現在、正常範囲内（平穏）です。"

                msg = (
                    f"{title}\n"
                    f"━━━━━━━━━━━━━━━\n"
                    f"📅 日付: {latest_date}\n"
                    f"📉 評価損益率: 【 {latest_value}% 】\n"
                    f"━━━━━━━━━━━━━━━\n\n"
                    f"{status_text}\n\n"
                    f"🔗 推移データ:\nhttps://www.traders.co.jp/margin_derivatives/margin_transition"
                )
                send_line_message(msg)
            else:
                print("🟢 平日かつ正常値のため、LINE通知をスキップしました。")
        else:
            print("❌ 信用評価損益率の取得失敗。")
        print("-" * 30)

    except Exception as e:
        print(f"❌ 処理エラー: {e}")

# ==========================================
# 8. 外貨ex by GMO（米国・重要度★★★指標）処理
# ==========================================
def check_gaikaex_economy_index():
    print("🌐 外貨ex by GMO 経済指標カレンダーにアクセスしています...")
    gaikaex_url = "https://www.gaikaex.com/gaikaex/mark/calendar/"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        res = requests.get(gaikaex_url, headers=headers, timeout=15)
        res.encoding = res.apparent_encoding or "utf-8"
        res.raise_for_status()

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
                    alt_title = (img.get("alt", "") + img.get("title", "") + img.get("src", "")).lower()
                    if "アメリカ" in alt_title or "米国" in alt_title or "us" in alt_title:
                        is_us = True
                        break

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
                            name_str = txt
                            break

                if name_str:
                    event_info = f"⏰ {time_str} | {name_str}"
                    if event_info not in target_events:
                        target_events.append(event_info)

        print("-" * 30)
        if target_events:
            if len(target_events) > 10:
                print(f"⚠️ 検知異常: 本日の★★★指標が {len(target_events)} 件と異常値です。誤配信を防ぐため通知をスキップします。")
                return

            print(f"✅ 本日発表の米国★★★指標を {len(target_events)} 件発見しました！")
            title = f"🇺🇸 【GMO証券：本日発表の米国★★★ 注目指標】\n📅 {today.strftime('%Y/%m/%d')}"
            msg = f"{title}\n\n" + "\n".join(target_events) + f"\n\n📊 経済指標カレンダー:\n{gaikaex_url}"
            send_line_message(msg)
        else:
            print("🟢 本日発表の米国★★★指標はありませんでした。")
        print("-" * 30)

    except Exception as e:
        print(f"❌ GMO指標処理エラー: {e}")

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
        print("☕ 土曜日のためスキップ")
        return

    if today_wd == 6:
        print("📅 日曜報告実行")
        check_margin_evaluation()
        print("---")
        check_and_send_fear_greed()

    elif now_hour == 8:
        if is_japanese_holiday(now_jst):
            print("🇯🇵 祝日のため朝スキップ")
        else:
            print("☀️ 朝のチェック (SQ / 信用評価 / アノマリー)")
            check_and_send_sq_notice(now_jst)
            print("---")
            check_margin_evaluation()
            print("---")
            check_and_send_anomaly_notice(now_jst)

    else:
        if is_us_holiday(now_jst):
            print("🇺🇸 米国祝日のため夜スキップ")
        else:
            print("🌙 夜の通知チェック (FOMC / 米国指標 / Fear & Greed)")
            check_and_send_fomc_notice(now_jst)
            print("---")
            check_gaikaex_economy_index()
            print("---")
            check_and_send_fear_greed()

    print("🏁 処理完了。")

if __name__ == "__main__":
    main()
