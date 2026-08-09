import os
import re
from datetime import datetime, date, timedelta
import requests
from bs4 import BeautifulSoup

# ==========================================
# 1. 設定情報（GitHub Secretsから安全に読み込み）
# ==========================================
LINE_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN")
LINE_USER_ID = os.environ.get("LINE_USER_ID")

THRES_DANGER = -10.0
THRES_RECOVERY = 0.0

# ==========================================
# 2. LINE Push Message 送信関数
# ==========================================
def send_line_message(text):
    if not LINE_ACCESS_TOKEN or not LINE_USER_ID:
        print("❌ LINEのトークンまたはユーザーIDが設定されていません。")
        return

    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}",
    }
    payload = {"to": LINE_USER_ID, "messages": [{"type": "text", "text": text}]}

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        if res.status_code == 200:
            print("🚀 LINEへの通知送信に成功しました！")
        else:
            print(f"❌ LINE通知失敗: {res.status_code} - {res.text}")
    except Exception as e:
        print(f"❌ LINE送信エラー: {e}")

# ==========================================
# 3. トレーダーズ・ウェブ（信用評価損益率）処理
# ==========================================
def check_margin_evaluation():
    try:
        url = "https://www.traders.co.jp/margin_derivatives/margin_transition"
        print("🌐 トレーダーズ・ウェブにアクセスしています...")

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BeautifulSoup/537.36"
                " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }
        res = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")

        print("🔍 信用評価損益率データを探索中...")
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
            print("✅ 信用評価損益率 取得成功！")
            print(f"最新日付: {latest_date}")
            print(f"信用評価損益率: {latest_value}%")

            today_wd = date.today().weekday()
            is_sunday = (today_wd == 6)  # 日曜日判定 (6)

            # 警戒・回復アラート判定
            is_danger = latest_value <= THRES_DANGER
            is_recovery = latest_value >= THRES_RECOVERY

            if is_sunday:
                # 日曜日は定期通知日（夜20:00の実行時に送信）
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
                    f"📊 過去の推移データはこちら:\nhttps://www.traders.co.jp/margin_derivatives/margin_transition"
                )
                send_line_message(msg)

            elif is_danger or is_recovery:
                # 平日のアラート通知
                if is_danger:
                    msg = (
                        f"⚠️ 【警戒警報：信用評価損益率】\n日付: {latest_date}\n"
                        f"評価損益率が {latest_value}% に低下しました！\n（設定閾値: {THRES_DANGER}% 以下）\n\n"
                        f"📊 過去の推移データはこちら:\nhttps://www.traders.co.jp/margin_derivatives/margin_transition"
                    )
                else:
                    msg = (
                        f"🎉 【プラス圏浮上：信用評価損益率】\n日付: {latest_date}\n"
                        f"評価損益率が {latest_value}% に回復しました！\n\n"
                        f"📊 過去の推移データはこちら:\nhttps://www.traders.co.jp/margin_derivatives/margin_transition"
                    )
                send_line_message(msg)

            else:
                print("🟢 平日かつ正常範囲内のため、LINE通知はスキップします。")
        else:
            print("❌ 信用評価損益率の取得に失敗しました。")
        print("-" * 30)

    except Exception as e:
        print(f"❌ トレーダーズ・ウェブ処理中にエラーが発生しました: {e}")

# ==========================================
# 4. 外貨ex by GMO（米国・重要度★★★指標）処理
# ==========================================
def check_gaikaex_economy_index():
    print("🌐 外貨ex by GMO 経済指標カレンダーにアクセスしています...")
    gaikaex_url = "https://www.gaikaex.com/gaikaex/mark/calendar/"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BeautifulSoup/537.36"
            " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }

    try:
        res = requests.get(gaikaex_url, headers=headers, timeout=15)
        res.encoding = res.apparent_encoding or "utf-8"
        res.raise_for_status()

        soup = BeautifulSoup(res.text, "html.parser")
        today = date.today()

        m_str, d_str = str(today.month), str(today.day)
        m_z, d_z = f"{today.month:02d}", f"{today.day:02d}"

        print(f"🔍 本日（{today.year}/{m_z}/{d_z}）の米国★★★指標を検索中...")

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
        print(f"❌ 外貨ex by GMO処理中にエラーが発生しました: {e}")

# ==========================================
# 5. メイン処理
# ==========================================
def main():
    today_wd = date.today().weekday()
    now_hour = datetime.now().hour
    print(f"🤖 自動チェック処理を開始します... (実行曜日(0=月,6=日): {today_wd}, 実行時刻(JST): 約{now_hour}時)")

    # 日曜日の場合 ＝ 信用評価損益率（週末定期報告）を実行
    if today_wd == 6:
        print("📅 【日曜日】信用評価損益率の週末定期報告を行います。")
        check_margin_evaluation()
    # 平日（月〜金）の朝（12時前） ＝ 信用評価損益率のアラートチェック
    elif now_hour < 12:
        print("☀️ 【平日朝の部】信用評価損益率のアラートチェックを行います。")
        check_margin_evaluation()
    # 平日（月〜金）の夜（12時以降） ＝ 米国重要指標チェック
    else:
        print("🌙 【平日夜の部】米国重要指標（GMO★★★）のチェックを行います。")
        check_gaikaex_economy_index()

    print("🏁 すべての処理が完了しました。")

if __name__ == "__main__":
    main()
