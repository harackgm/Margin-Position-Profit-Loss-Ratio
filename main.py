import os
import re
import time
import base64
from datetime import datetime, date, timedelta
import requests
from bs4 import BeautifulSoup

# Selenium関連のインポート（画像キャプチャ用）
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

# ==========================================
# 1. 設定情報（GitHub Secretsから安全に読み込み）
# ==========================================
LINE_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN")
LINE_USER_ID = os.environ.get("LINE_USER_ID")
IMGBB_API_KEY = os.environ.get("IMGBB_API_KEY")

THRES_DANGER = -10.0
THRES_RECOVERY = 0.0

# ==========================================
# 2. LINE Push Message 送信関数（テキスト用＆画像用）
# ==========================================
def send_line_message(text):
    """テキストメッセージを送信する関数"""
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
            print("🚀 LINEへのテキスト通知送信に成功しました！")
        else:
            print(f"❌ LINE通知失敗: {res.status_code} - {res.text}")
    except Exception as e:
        print(f"❌ LINE送信エラー: {e}")


def send_line_image(image_url):
    """画像メッセージを送信する関数"""
    if not LINE_ACCESS_TOKEN or not LINE_USER_ID:
        return

    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}",
    }
    payload = {
        "to": LINE_USER_ID,
        "messages": [
            {
                "type": "image",
                "originalContentUrl": image_url,
                "previewImageUrl": image_url
            }
        ]
    }

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        if res.status_code == 200:
            print(f"📸 LINEへの画像送信成功: {image_url}")
        else:
            print(f"❌ LINE画像通知失敗: {res.status_code} - {res.text}")
    except Exception as e:
        print(f"❌ LINE画像送信エラー: {e}")

# ==========================================
# 3. 恐怖と貪欲指数 (Fear & Greed Index) 画像処理
# ==========================================
def capture_and_send_fear_greed():
    """CNNのサイトからメーターを撮影し、ImgBB経由でLINEへ送る関数"""
    if not IMGBB_API_KEY:
        print("❌ IMGBB_API_KEYが設定されていないため、画像処理をスキップします。")
        return

    print("🌐 CNN Fear & Greed Indexにアクセスし、画像をキャプチャします...")
    
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1200,800')
    
    driver = None
    image_path = "fgi_meter.png"

    try:
        driver = webdriver.Chrome(options=options)
        driver.get("https://edition.cnn.com/markets/fear-and-greed")
        
        time.sleep(5) 

        try:
            gauge_element = driver.find_element(By.CSS_SELECTOR, ".market-fng-gauge")
            gauge_element.screenshot(image_path)
            print("📸 メーター部分の切り取り撮影に成功しました。")
        except:
            driver.save_screenshot(image_path)
            print("📸 画面全体の撮影に成功しました。")
            
    except Exception as e:
        print(f"❌ 画像キャプチャ中にエラーが発生しました: {e}")
        return
    finally:
        if driver:
            driver.quit()

    # --- ImgBBへ画像をアップロードして完全な画像直リンク化 ---
    print("☁️ 取得した画像をImgBBへアップロードしています...")
    try:
        with open(image_path, "rb") as file:
            img_base64 = base64.b64encode(file.read())

        imgbb_url = "https://api.imgbb.com/1/upload"
        payload = {
            "key": IMGBB_API_KEY,
            "image": img_base64,
        }
        res = requests.post(imgbb_url, data=payload, timeout=15)
        res_json = res.json()

        if res.status_code == 200 and res_json.get("success"):
            data_field = res_json.get("data", {})
            
            # LINEが確実に表示できる画像ファイルの直リンク（display_url / image.url）を特定
            image_url = data_field.get("display_url") or data_field.get("image", {}).get("url")
            
            print(f"✅ 画像直リンクの取得成功: {image_url}")
            
            send_line_message("🧭 【動作テスト：恐怖と貪欲指数 (Fear & Greed Index)】\nメーター画像の表示テストです！")
            send_line_image(image_url)
        else:
            print(f"❌ ImgBBへのアップロード失敗: {res_json}")
            
    except Exception as e:
        print(f"❌ ImgBBアップロード処理中にエラーが発生しました: {e}")

# ==========================================
# 4. トレーダーズ・ウェブ（信用評価損益率）処理
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
                send_line_message(msg)

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
                send_line_message(msg)

            else:
                print("🟢 平日かつ正常範囲内のため、LINE通知はスキップします。")
        else:
            print("❌ 信用評価損益率の取得に失敗しました。")
        print("-" * 30)

    except Exception as e:
        print(f"❌ トレーダーズ・ウェブ処理中にエラーが発生しました: {e}")

# ==========================================
# 5. 外貨ex by GMO（米国・重要度★★★指標）処理
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
# 6. メイン処理（★テスト強制実行モード★）
# ==========================================
def main():
    print("🧪 【テスト実行】時間判定を無視して、恐怖と貪欲指数を撮影＆送信します！")
    capture_and_send_fear_greed()

if __name__ == "__main__":
    main()
