import os
import re
import time
from datetime import datetime, date, timedelta, timezone
import requests
from bs4 import BeautifulSoup

# ==========================================
# 1. 設定情報（LINE アクセストークン）
# ==========================================
LINE_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN")

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
# 3. アノマリー＆イベント判定ロジック (SQ / 彼岸底 / FOMC)
# ==========================================

# --- SQ日判定 ---
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

# --- 彼岸底判定 ---
def get_higan_zoko_date(year, month):
    """3月15日・9月15日以降の最初の営業日を取得する"""
    target_date = date(year, month, 15)
    while True:
        dt_check = datetime(target_date.year, target_date.month, target_date.day, tzinfo=timezone(timedelta(hours=9)))
        if target_date.weekday() in [5, 6] or is_japanese_holiday(dt_check):
            target_date += timedelta(days=1)
        else:
            break
    return target_date

def check_and_send_higan_zoko_notice(dt_jst):
    """彼岸底アノマリーの事前リマインドを送信"""
    today_date = dt_jst.date()
    year = dt_jst.year
    month = dt_jst.month

    if month not in [3, 9]:
        return

    higan_date = get_higan_zoko_date(year, month)

    if today_date == higan_date:
        season = "春" if month == 3 else "秋"
        icon = "🌸" if month == 3 else "🌾"
        title = f"{icon} 【アノマリー警戒：{season}の彼岸底シーズン到来】 {icon}"
        
        details = (
            f"【{season}の彼岸底（ひがんぞこ）とは？】\n"
            f"日本の株式市場で古くから知られる季節アノマリーです。\n"
            f"月末の決算に向けた機関投資家の「換金売り（ポジション調整）」がピークを迎え、一時的な底値（押し目）を作りやすい時期とされています。"
        )
        
        warning = (
            "⚠️ 【今後の立ち回り】\n"
            "売り圧力が強まりやすいタイミングのため、買い急ぎには注意が必要です。\n"
            "下落が一巡して反転する「絶好の買い場」を慎重に探っていきましょう！"
        )

        msg = (
            f"{title}\n"
            f"📅 日付: {today_date.strftime('%Y/%m/%d')}\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"{details}\n\n"
            f"{warning}"
        )

        print(f"🚀 {season}の彼岸底アノマリー事前リマインドを配信します。")
        send_line_message(msg)

# --- FOMC判定 ---
def check_and_send_fomc_notice(dt_jst):
    """FOMC事前リマインド送信（水曜日夜想定）"""
    today_date = dt_jst.date()

    fomc_announcement_dates = [
        # 2026年スケジュール
        date(2026, 1, 29), date(2026, 3, 19), date(2026, 5, 7),
        date(2026, 6, 18), date(2026, 7, 30), date(2026, 9, 17),
        date(2026, 10, 29), date(2026, 12, 10),
        # 2027年スケジュール（先行登録）
        date(2027, 1, 28), date(2027, 3, 18), date(2027, 5, 6),
        date(2027, 6, 17), date(2027, 7, 29), date(2027, 9, 16),
        date(2027, 11, 4), date(2027, 12, 16),
    ]

    tomorrow_date = today_date + timedelta(days=1)

    if tomorrow_date in fomc_announcement_dates:
        title = "🏛️🇺🇸 【最重要イベント：今夜『FOMC政策金利発表』！】"
        details = (
            "【FOMC（米連邦公開市場委員会）とは？】\n"
            "米国の金利方針（利上げ・利下げ・維持）を決定する最高意思決定会合です。\n"
            "日本時間の本日深夜（午前3:00〜4:00頃）に政策金利と声明文が発表され、パウエルFRB議長の記者会見が行われます。"
        )
        warning = (
            "⚠️ 【全世界の市場・為替が激変する警戒夜！】\n"
            "発表前後でドル円（為替）や米国株、日経平均先物が激しく乱高下する可能性が非常に高くなります。\n"
            "夜間のポジション持ち越しやレバレッジ取引には十分ご注意ください！"
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

# ==========================================
# 4. LINE 送信関数
# ==========================================
def send_line_message(text):
    """登録者全員へブロードキャスト一括送信"""
    if not LINE_ACCESS_TOKEN:
        print("❌ LINE_ACCESS_TOKEN が設定されていません。")
        return

    url = "https://api.line.me/v2/bot/message/broadcast"
    payload = {"messages": [{"type": "text", "text": text}]}
    target_name = "全員一括（ブロードキャスト送信）"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}",
    }

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        if res.status_code == 200:
            print(f"🚀 LINE送信成功！（対象: {target_name}）")
        else:
            print(f"❌ LINE配信失敗: {res.status_code} - {res.text}")
    except Exception as e:
        print(f"❌ LINE送信エラー: {e}")

# ==========================================
# 5. 恐怖と欲望指数 (Fear & Greed Index) データ取得
# ==========================================
def check_and_send_fear_greed():
    print("🌐 CNN Fear & Greed IndexのデータAPIへ直接アクセスします...")
    
    api_url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
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
        else:
            print(f"⚠️ APIレスポンスエラー: ステータスコード {res.status_code}")
    except Exception as e:
        print(f"❌ API通信中にエラーが発生しました: {e}")

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
            print(f"❌ 予備取得も失敗しました: {e}")

    if score is None:
        print("❌ スコアを取得できませんでした。")
        return

    if score <= 10:
        title = "💀🔥 【超絶大バーゲンセール！ (Extreme Fear ≤ 10)】 🔥💀"
        expression = (
            "市場は歴史的な大パニック状態です！！\n"
            "😱 身の毛もよだつ最大の恐怖に打ち勝った者だけが、将来の大金を手に入れられる……！！\n"
            "千載一遇の超絶買い場到来か！？ここで買える者こそが勝者！目をつむって買いまくれ！"
        )
    elif score <= 24:
        title = "😱🚨 【キャー！極度の恐怖 (Extreme Fear)】 🚨😱"
        expression = (
            "市場は極限のパニック状態です！！\n"
            "みんなが恐怖で逃げ出しています💦 バーゲンセールか、それとも底なし沼か……！？"
        )
    elif score <= 44:
        title = "😨⚠️ 【恐怖モード (Fear)】 ⚠️😨"
        expression = (
            "市場には弱気なムードが漂っています。\n"
            "慎重な立ち回りが求められる警戒エリアです！"
        )
    elif score <= 55:
        title = "😐⚖️ 【中立・平穏 (Neutral)】 ⚖️😐"
        expression = (
            "市場はきわめて冷静です。\n"
            "嵐の前の静けさか、方向感を探る展開が続いています。"
        )
    elif score <= 75:
        title = "😃🚀 【強気モード！ (Greed)】 🚀😃"
        expression = (
            "市場は強気ムード上昇中！！\n"
            "買いの勢いがついています。この波に乗っていきましょう！"
        )
    else:
        title = "🤩🔥 【超イケイケ激熱発狂モード！！ (Extreme Greed)】 🔥🤩"
        expression = (
            "市場は熱狂の渦！絶好調のイケイケ状態です！！\n"
            "過熱感バツグン！高値掴みには注意しつつノリノリで行きましょう！"
        )

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
        f"🔗 詳細チャート:\nhttps://edition.cnn.com/markets/fear-and-greed\n\n"
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
# 6. トレーダーズ・ウェブ（信用評価損益率）処理
# ==========================================
def check_margin_evaluation():
    try:
        url = "https://www.traders.co.jp/margin_derivatives/margin_transition"
        print("🌐 トレーダーズ・ウェブにアクセスしています...")

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }
        res = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")

        rows = soup.find_all("tr")
        latest_date = ""
        latest_value = None

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
            now_jst = datetime.now(jst)
            is_sunday = (now_jst.weekday() == 6)

            is_danger = latest_value <= THRES_DANGER
            is_recovery = latest_value >= THRES_RECOVERY

            if is_sunday or is_danger or is_recovery:
                if is_danger:
                    title = "⚠️🚨 【信用評価損益率：危険水域到達】 🚨⚠️"
                    status_text = "追証発生や投げ売り（追い込まれた個人の投げ）の危険が高まっています。"
                elif is_recovery:
                    title = "🎉📈 【信用評価損益率：プラス圏浮上】 📈🎉"
                    status_text = "個人投資家の損益がプラスに転じました！"
                else:
                    title = "📊 【日曜日：信用評価損益率 定期報告】"
                    status_text = "現在、正常範囲内（平穏）です。"

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
# 7. 外貨ex by GMO（米国・重要度★★★指標）処理
# ==========================================
def check_gaikaex_economy_index():
    print("🌐 外貨ex by GMO 経済指標カレンダーにアクセスしています...")
    gaikaex_url = "https://www.gaikaex.com/gaikaex/mark/calendar/"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
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

        target_events = []
        rows = soup.find_all("tr")
        current_is_today = False

        for row in rows:
            row_text = row.get_text(" ", strip=True)
            row_html = str(row)

            if any(p in row_text for p in [f"{m_str}/{d_str}", f"{m_z}/{d_z}", f"{m_str}月{d_str}日", f"{m_z}月{d_z}日"]):
                current_is_today = True
            elif any(re.search(r"\d{1,2}/\d{1,2}|\d{1,2}月\d{1,2}日", row_text) for _ in [1]):
                if current_is_today and not any(p in row_text for p in [f"{m_str}/{d_str}", f"{m_z}/{d_z}"]):
                    current_is_today = False

            if not current_is_today:
                continue

            is_us = "アメリカ" in row_text or "米国" in row_text
            if not is_us:
                for img in row.find_all("img"):
                    alt_title = (img.get("alt", "") + img.get("title", "") + img.get("src", "")).lower()
                    if "アメリカ" in alt_title or "米国" in alt_title or "us" in alt_title:
                        is_us = True
                        break

            if not is_us:
                continue

            is_star3 = ("★★★" in row_text or "★3" in row_text or 
                        re.search(r"star[_-]?3|rank[_-]?3|level[_-]?3", row_html, re.I) or 
                        row_html.count("star") >= 3)

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
# 8. メイン処理
# ==========================================
def main():
    jst = timezone(timedelta(hours=9))
    now_jst = datetime.now(jst)
    
    today_wd = now_jst.weekday()
    now_hour = now_jst.hour

    print(f"🤖 チェック開始... (曜日: {today_wd}, 時刻: {now_hour}時)")

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
            print("☀️ 朝のチェック (SQ / 彼岸底 / 信用評価損益率)")
            check_and_send_sq_notice(now_jst)
            check_and_send_higan_zoko_notice(now_jst)
            print("---")
            check_margin_evaluation()

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
