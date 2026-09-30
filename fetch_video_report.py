"""
Выгружает статистику по КАЖДОМУ видео канала (не по дням, а по роликам)
и сохраняет в CSV: название, дата публикации, просмотры, удержание, лайки и т.д.

Перед первым запуском:
1. credentials.json уже должен лежать в этой папке (тот же, что для fetch_analytics.py).
2. Установите зависимости: pip install -r requirements.txt
3. Запустите: python fetch_video_report.py
   Откроется браузер — войдите в тот же Google-аккаунт и разрешите доступ.
   Этому скрипту нужно на одно разрешение больше (доступ к названиям видео),
   поэтому он использует отдельный token_video.json и попросит авторизацию заново,
   даже если fetch_analytics.py уже был авторизован.

По умолчанию берётся весь период с 2015-01-01 по сегодня — этого достаточно
для любого канала. При желании поменяйте START_DATE ниже.
"""

import os
import datetime
import pandas as pd
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/youtube.readonly",
]
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token_video.json"
OUTPUT_DIR = "data"
START_DATE = "2015-01-01"


def get_credentials():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            print("Открываю браузер для входа в Google-аккаунт...")
            creds = flow.run_local_server(port=8080, open_browser=True)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return creds


def fetch_video_stats(youtube_analytics, start_date, end_date):
    request = youtube_analytics.reports().query(
        ids="channel==MINE",
        startDate=start_date,
        endDate=end_date,
        metrics="views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,"
        "subscribersGained,likes,comments,shares",
        dimensions="video",
        sort="-views",
        maxResults=200,
    )
    return request.execute()


def fetch_video_titles(youtube_data, video_ids):
    """videos.list принимает максимум 50 ID за раз, поэтому бьём на пачки."""
    all_items = []
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i : i + 50]
        response = youtube_data.videos().list(
            part="snippet,contentDetails", id=",".join(chunk)
        ).execute()
        all_items.extend(response.get("items", []))
    return {
        item["id"]: {
            "title": item["snippet"]["title"],
            "publishedAt": item["snippet"]["publishedAt"][:10],
            "duration": item["contentDetails"]["duration"],
        }
        for item in all_items
    }


def main():
    creds = get_credentials()
    youtube_analytics = build("youtubeAnalytics", "v2", credentials=creds)
    youtube_data = build("youtube", "v3", credentials=creds)

    end_date = datetime.date.today().isoformat()
    report = fetch_video_stats(youtube_analytics, START_DATE, end_date)

    columns = [h["name"] for h in report["columnHeaders"]]
    df = pd.DataFrame(report.get("rows", []), columns=columns)

    if df.empty:
        print("Нет данных за указанный период.")
        return

    titles = fetch_video_titles(youtube_data, df["video"].tolist())
    df["title"] = df["video"].map(lambda v: titles.get(v, {}).get("title", ""))
    df["publishedAt"] = df["video"].map(lambda v: titles.get(v, {}).get("publishedAt", ""))
    df["duration"] = df["video"].map(lambda v: titles.get(v, {}).get("duration", ""))

    # Красивый порядок колонок
    ordered = [
        "title", "publishedAt", "video", "views", "estimatedMinutesWatched",
        "averageViewDuration", "averageViewPercentage",
        "subscribersGained", "likes", "comments", "shares", "duration",
    ]
    df = df[[c for c in ordered if c in df.columns]]

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, "video_report.csv")
    df.to_csv(out_path, index=False)
    print(f"Сохранено: {out_path}")
    print(df.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
