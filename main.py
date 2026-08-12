import os
import re
import datetime
import requests
from bs4 import BeautifulSoup

# -------------------------------------------------------------------
# 設定・定数定義
# -------------------------------------------------------------------
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# -------------------------------------------------------------------
# LINE Messaging API / LINE Notify 送信処理
# -------------------------------------------------------------------
def send_line_message(message_text):
    """LINEへメッセージを送信する関数"""
    token = os.environ.get("LINE_ACCESS_TOKEN")
    if not token:
        print("[ERROR] LINE_ACCESS_TOKEN が設定されていません。")
        return False

    # LINE Notify エンドポイント
    url = "https://notify-api.line.me/api/notify"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"message": f"\n{message_text}"}

    try:
        response = requests.post(url, headers=headers, data=payload, timeout=15)
        if response.status_code == 200:
            print("[INFO] LINE通知の送信に成功しました。")
            return True
        else:
            print(f"[ERROR] LINE送信失敗: Status {response.status_code}, Res: {response.text}")
            return False
    except Exception as e:
        print(f"[ERROR] LINE送信中に例外が発生しました: {e}")
        return False

# -------------------------------------------------------------------
# データ取得スクレイピング処理
# -------------------------------------------------------------------
def get_margin_ratio():
    """信用評価損益率を取得（日本株）"""
    try:
        url = "https://minkabu.jp/market/margin_ratio" # Minkabu等から取得例
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            # 対象要素の検索（構造に合わせて調整）
            element = soup.find(class_="margin-ratio-val")
            if element:
                val_str = element.text.strip().replace("%", "").replace("+", "")
                return float(val_str)
    except Exception as e:
        print(f"[WARN] 信用評価損益率の取得に失敗しました: {e}")
    return None

def get_fear_and_greed():
    """Fear & Greed Index を取得"""
    try:
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            data = res.json()
            score = round(data["fear_and_greed"]["score"])
            rating = data["fear_and_greed"]["rating"]
            return score, rating
    except Exception as e:
        print(f"[WARN] Fear & Greed Index の取得に失敗しました: {e}")
    return None, None

def get_gmo_indicators():
    """GMOクリック証券から本日の★3米国経済指標を取得"""
    indicators = []
    try:
        url = "https://www.click-sec.com/corp/guide/kabu/calendar/"
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            # ★3の指標を抽出する処理
            rows = soup.select("table.calendar-table tr")
            for row in rows:
                text = row.text
                if "米国" in text and ("★★★" in text or "星3" in text or "重要" in text):
                    # 指標名を簡易整形
                    title = text.split()[0] if text.split() else "米国重要指標"
                    indicators.append(title)
    except Exception as e:
        print(f"[WARN] 経済指標の取得に失敗しました: {e}")
    return indicators

# -------------------------------------------------------------------
# メイン配信ロジック
# -------------------------------------------------------------------
def main():
    print("[INFO] === Daily Market Alert 処理開始 ===")
    
    # 現在の日本時間を計算（UTC+9）
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    now_jst = now_utc + datetime.timedelta(hours=9)
    hour = now_jst.hour
    day_of_week = now_jst.weekday() # 0:月 ~ 6:日

    print(f"[INFO] 実行日時 (JST): {now_jst.strftime('%Y-%m-%d %H:%M:%S')} (曜日: {day_of_week})")

    # ---------------------------------------------------------------
    # 1. 平日朝 (08:23頃実行): 信用評価損益率アラート
    # ---------------------------------------------------------------
    if 7 <= hour <= 9 and day_of_week in [0, 1, 2, 3, 4]:
        print("[INFO] 【平日朝】判定ロジックを実行します。")
        ratio = get_margin_ratio()
        
        if ratio is not None:
            # 閾値判定: -10.0%以下 または 0.0%以上
            if ratio <= -10.0 or ratio >= 0.0:
                msg = f"【信用評価損益率アラート】\n最新値: {ratio:.1f}%\n※閾値条件を満たしたため通知します。"
                send_line_message(msg)
            else:
                print(f"[INFO] 評価損益率は {ratio:.1f}% のため、通知対象外（閾値範囲内）です。")
        else:
            print("[WARN] 評価損益率の取得ができなかったため送信をスキップしました。")

    # ---------------------------------------------------------------
    # 2. 平日夜 (19:51頃実行): 本日の米国重要指標 & Fear & Greed
    # ---------------------------------------------------------------
    elif 18 <= hour <= 21 and day_of_week in [0, 1, 2, 3, 4]:
        print("[INFO] 【平日夜】判定ロジックを実行します。")
        score, rating = get_fear_and_greed()
        indicators = get_gmo_indicators()
        
        fg_str = f"{score} ({rating})" if score is not None else "取得不可"
        ind_str = "、".join(indicators) if indicators else "本日なし"
        
        # 1行崩れを防ぐ整形レイアウト
        msg = f"【本日夜の市場情報】\n☑ Fear&Greed: {fg_str}\n☑ 米国★3指標: {ind_str}"
        send_line_message(msg)

    # ---------------------------------------------------------------
    # 3. 日曜夜 (19:52頃実行): 週末定期報告
    # ---------------------------------------------------------------
    elif 18 <= hour <= 21 and day_of_week == 6:
        print("[INFO] 【日曜夜】判定ロジックを実行します。")
        ratio = get_margin_ratio()
        score, rating = get_fear_and_greed()
        
        ratio_str = f"{ratio:.1f}%" if ratio is not None else "取得不可"
        fg_str = f"{score} ({rating})" if score is not None else "取得不可"
        
        msg = f"【週末定期報告】\n☑ 信用評価損益率: {ratio_str}\n☑ Fear&Greed: {fg_str}"
        send_line_message(msg)

    else:
        print("[INFO] 該当する実行時間帯ではありません。処理を終了します。")

    print("[INFO] === Daily Market Alert 処理終了 ===")

if __name__ == "__main__":
    main()
