"""
Выгружает статистику YouTube-канала через YouTube Analytics API и сохраняет в CSV.

Перед первым запуском:
1. Положите файл credentials.json (скачан из Google Cloud Console) в эту же папку.
2. Установите зависимости: pip install -r requirements.txt
3. Запустите: python fetch_analytics.py
   При первом запуске откроется браузер — войдите в тот Google-аккаунт,
   на который зарегистрирован канал, и разрешите доступ.
   После этого появится token.json — он хранит доступ, чтобы не логиниться каждый раз.

credentials.json и token.json никогда не должны попадать в git — они уже в .gitignore.
"""

import os
import datetime
import pandas as pd
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/yt-analytics.readonly"]
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"
OUTPUT_DIR = "data"


def get_credentials():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return creds


def fetch_report(youtube_analytics, start_date, end_date):
    request = youtube_analytics.reports().query(
        ids="channel==MINE",
        startDate=start_date,
        endDate=end_date,
        metrics="views,estimatedMinutesWatched,averageViewDuration,subscribersGained,subscribersLost,likes,comments,shares",
        dimensions="day",
        sort="day",
    )
    return request.execute()


def main():
    creds = get_credentials()
    youtube_analytics = build("youtubeAnalytics", "v2", credentials=creds)

    end_date = datetime.date.today().isoformat()
    start_date = (datetime.date.today() - datetime.timedelta(days=28)).isoformat()

    report = fetch_report(youtube_analytics, start_date, end_date)

    columns = [h["name"] for h in report["columnHeaders"]]
    df = pd.DataFrame(report.get("rows", []), columns=columns)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, f"analytics_{start_date}_to_{end_date}.csv")
    df.to_csv(out_path, index=False)
    print(f"Сохранено: {out_path}")
    print(df.tail())


if __name__ == "__main__":
    main()
