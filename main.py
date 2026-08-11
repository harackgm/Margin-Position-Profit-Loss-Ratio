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
    """日本の祝日判定"""
    today_date = dt_jst.date()
    
    # 主要な固定祝日リスト (月, 日)
    fixed_holidays = [
        (1, 1),   # 元日
        (2, 11),  # 建国記念の日
        (2, 23),  # 天皇誕生日
        (4, 29),  # 昭和の日
        (5, 3),   # 憲法記念日
        (5, 4),   # みどりの日
        (5, 5),   # こどもの日
        (8, 11),  # 山の日
        (11, 3),  # 文化の日
        (11, 23), # 勤労感謝の日
    ]
    if (today_date.month, today_date.day) in fixed_holidays:
        return True

    # ハッピーマンデー等（第N月曜日）
    month = today_date.month
    day = today_date.day
    weekday = today_date.weekday() # 0=月曜日

    if weekday == 0:
        if month == 1 and 8 <= day <= 14:   # 成人の日
            return True
        if month == 7 and 15 <= day <= 21:  # 海の日
            return True
        if month == 9 and 15 <= day <= 21:  # 敬老の日
            return True
        if month == 10 and 8 <= day <= 14:  # スポーツの日
            return True

    # 振替休日判定（固定祝日が日曜日の場合の翌月曜）
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
    weekday = today_date.weekday() # 0=月曜日

    # 固定祝日
    if (month == 1 and day == 1):   # New Year's Day
        return True
    if (month == 6 and day == 19):  # Juneteenth
        return True
    if (month == 7 and day == 4):   # Independence Day
        return True
    if (month == 12 and day == 25): # Christmas Day
        return True

    # 移動祝日
    if weekday == 0:
        if month == 1 and 15 <= day <= 21:  # Martin Luther King Jr. Day
            return True
        if month == 2 and 15 <= day <= 21:  # Presidents' Day
            return True
        if month == 5 and 25 <= day <= 31:  # Memorial Day
            return True
        if month == 9 and 1 <= day <= 7:    # Labor Day
            return True

    if weekday == 3 and month == 11 and 22 <= day <= 28: # Thanksgiving Day
        return True

    return False

# ==========================================
# 3. LINE Broadcast Message 送信関数（登録者全員配信）
# ==========================================
def broadcast_line_message(text):
    """友だち追加している全ユーザーへ一括送信する関数"""
    if not LINE_ACCESS_TOKEN:
        print("❌ LINE_ACCESS_TOKEN が設定されていません。")
        return

    url = "https://api.line.me/v2/bot/message/broadcast"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}",
    }
    payload = {"messages": [{"type": "text", "text": text}]}

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        if res.status_code == 200:
            print("🚀 LINE全員一括配信（ブロードキャスト）に成功しました！")
        else:
            print(f"❌ LINE配信失敗: {res.status_code} - {res.text}")
    except Exception as e:
        print(f"❌ LINE送信エラー: {e}")

# ==========================================
# 4. 恐怖と欲望指数 (Fear & Greed Index) データ取得＆演出処理
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

    # 万が一APIが拒否された場合のWebスクレイピング（予備）
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

    # 演出メッセージの作成
    if score <= 10:
        title = "💀🔥 【超絶バーゲンセール！ (Extreme Fear ≤ 10)】 🔥💀"
        expression = (
            "市場は歴史的な大パニック状態です！！\n"
            "😱 身の毛もよだつ最大の恐怖に打ち勝った者だけが、将来の大金を手に入れられる……！！\n"
            "千載一遇の超絶買い場到来か！？"
        )
    elif score <= 24:
        title = "😱🚨 【極度の恐怖 (Extreme Fear)】 🚨😱"
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
        f"  0〜10：超絶買い場（最大の恐怖）\n"
        f" 11〜24：極度の恐怖 (Extreme Fear)\n"
        f" 25〜44：恐怖 (Fear)\n"
        f" 45〜55：中立・平穏 (Neutral)\n"
        f" 56〜75：強気モード (Greed)\n"
        f" 76〜100：超イケイケ (Extreme Greed)"
    )

    broadcast_line_message(msg)

# ==========================================
# 5. トレーダーズ・ウェブ（信用評価損益率）処理
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
            today_wd = datetime.now(jst).weekday()
            is_sunday = (today_wd == 6)

            is_danger = latest_value <= THRES_DANGER
            is_recovery = latest_value >= THRES_RECOVERY

            if is_sunday:
                if is_danger:
                    status_text = f"⚠️ 警戒ライン到達中（{THRES_DANGER}%以下）"
                elif is_recovery:
                    status_text = f"🎉 プラス圏（{THRES_RECOVERY}%以上）"
                else:
                    status_text = "🟢 正常範囲内"

                msg = (
                    f"📅 【週末定期報告：信用評価損益率】\n"
                    f"日付: {latest_date}\n"
                    f"評価損益率: {latest_value}%\n"
                    f"状態: {status_text}\n\n"
                    f"📊 過去の推移データ:\nhttps://www.traders.co.jp/margin_derivatives/margin_transition"
                )
                broadcast_line_message(msg)

            elif is_danger or is_recovery:
                if is_danger:
                    msg = (
                        f"⚠️ 【警戒警報：信用評価損益率】\n日付: {latest_date}\n"
                        f"評価損益率が {latest_value}% に低下しました！\n（設定閾値: {THRES_DANGER}% 以下）\n\n"
                        f"📊 推移データ:\nhttps://www.traders.co.jp/margin_derivatives/margin_transition"
                    )
                else:
                    msg = (
                        f"🎉 【プラス圏浮上：信用評価損益率】\n日付: {latest_date}\n"
                        f"評価損益率が {latest_value}% に回復しました！\n\n"
                        f"📊 推移データ:\nhttps://www.traders.co.jp/margin_derivatives/margin_transition"
                    )
                broadcast_line_message(msg)

            else:
                print("🟢 平日かつ正常範囲内のため、LINE通知はスキップします。")
        else:
            print("❌ 信用評価損益率の取得に失敗しました。")
        print("-" * 30)

    except Exception as e:
        print(f"❌ トレーダーズ・ウェブ処理中にエラーが発生しました: {e}")

# ==========================================
# 6. 外貨ex by GMO（米国・重要度★★★指標）処理
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
            broadcast_line_message(msg)
        else:
            print("🟢 本日発表の米国★★★指標はありませんでした。")
        print("-" * 30)

    except Exception as e:
        print(f"❌ 外貨ex by GMO処理中にエラーが発生しました: {e}")

# ==========================================
# 7. メイン処理（時間帯ガード付き）
# ==========================================
def main():
    jst = timezone(timedelta(hours=9))
    now_jst = datetime.now(jst)
    
    today_wd = now_jst.weekday()  # 0=月 ... 5=土, 6=日
    now_hour = now_jst.hour       # 時刻（0〜23）

    print(f"🤖 チェック開始... (曜日(0=月,6=日): {today_wd}, 日本時刻: 約{now_hour}時)")

    # 1. 土曜日の場合 ＝ 完全スキップ
    if today_wd == 5:
        print("☕ 【土曜日】日米ともに市場休場日のため処理をスキップします。")
        return

    # 2. 日曜日の場合 ＝ 20時台のみ実行（週末定期報告）
    if today_wd == 6:
        if 19 <= now_hour <= 22:
            print("📅 【日曜日 20:00】週末定期報告を行います。")
            check_margin_evaluation()
            print("---")
            check_and_send_fear_greed()
        else:
            print(f"⏸️ 日曜日ですが、定期配信時間（20:00）外（現在{now_hour}時）のためスキップします。")

    # 3. 平日（月〜金）朝の部 ＝ 8時台（日本株チェック）
    elif 7 <= now_hour <= 10:
        if is_japanese_holiday(now_jst):
            print("🇯🇵【日本の祝日】のため、朝の日本株チェックをスキップします。")
        else:
            print("☀️ 【平日朝 08:30】信用評価損益率アラートチェックを行います。")
            check_margin_evaluation()

    # 4. 平日（月〜金）夜の部 ＝ 21時以降（米国指標 ＆ Fear & Greed）
    elif 20 <= now_hour <= 23:
        if is_us_holiday(now_jst):
            print("🇺🇸【アメリカの祝日】のため、夜の米国指標 ＆ Fear & Greed チェックをスキップします。")
        else:
            print("🌙 【平日夜 21:30】米国重要指標 ＆ Fear & Greed チェックを行います。")
            check_gaikaex_economy_index()
            print("---")
            check_and_send_fear_greed()

    # 5. 上記以外の時間帯 ＝ スキップ
    else:
        print(f"⏸️ 現在の時間帯（{now_hour}時）はスケジュール対象外のため、処理を実行せず終了します。")

    print("🏁 処理が完了しました。")

if __name__ == "__main__":
    main()
