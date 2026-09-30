"""
Выгружает демографию аудитории канала через YouTube Analytics API:
- Пол и возраст зрителей
- География (страны)
- Демография по каждому видео отдельно

Использует тот же token.json, что и fetch_analytics.py.
Запуск: python fetch_demographics.py
"""

import os
import datetime
import pandas as pd
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/yt-analytics.readonly"]
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"
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


def fetch_age_gender(yta, start, end):
    """Пол + возраст по всему каналу."""
    resp = yta.reports().query(
        ids="channel==MINE",
        startDate=start,
        endDate=end,
        metrics="viewerPercentage",
        dimensions="ageGroup,gender",
        sort="ageGroup",
    ).execute()
    cols = [h["name"] for h in resp["columnHeaders"]]
    return pd.DataFrame(resp.get("rows", []), columns=cols)


def fetch_countries(yta, start, end):
    """Топ стран по просмотрам."""
    resp = yta.reports().query(
        ids="channel==MINE",
        startDate=start,
        endDate=end,
        metrics="views,estimatedMinutesWatched",
        dimensions="country",
        sort="-views",
        maxResults=25,
    ).execute()
    cols = [h["name"] for h in resp["columnHeaders"]]
    return pd.DataFrame(resp.get("rows", []), columns=cols)


def fetch_age_gender_per_video(yta, start, end):
    """Пол + возраст в разрезе видео."""
    resp = yta.reports().query(
        ids="channel==MINE",
        startDate=start,
        endDate=end,
        metrics="viewerPercentage",
        dimensions="video,ageGroup,gender",
        sort="-viewerPercentage",
        maxResults=500,
    ).execute()
    cols = [h["name"] for h in resp["columnHeaders"]]
    return pd.DataFrame(resp.get("rows", []), columns=cols)


def main():
    creds = get_credentials()
    yta = build("youtubeAnalytics", "v2", credentials=creds)
    end = datetime.date.today().isoformat()
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=== Пол и возраст (весь канал) ===")
    df_ag = fetch_age_gender(yta, START_DATE, end)
    path_ag = os.path.join(OUTPUT_DIR, "demographics_age_gender.csv")
    df_ag.to_csv(path_ag, index=False)
    print(f"Сохранено: {path_ag}")
    if not df_ag.empty:
        print(df_ag.to_string(index=False))

    print("\n=== Топ стран ===")
    df_c = fetch_countries(yta, START_DATE, end)
    path_c = os.path.join(OUTPUT_DIR, "demographics_countries.csv")
    df_c.to_csv(path_c, index=False)
    print(f"Сохранено: {path_c}")
    if not df_c.empty:
        print(df_c.to_string(index=False))

    print("\n=== Пол и возраст по видео ===")
    try:
        df_v = fetch_age_gender_per_video(yta, START_DATE, end)
        path_v = os.path.join(OUTPUT_DIR, "demographics_per_video.csv")
        df_v.to_csv(path_v, index=False)
        print(f"Сохранено: {path_v}")
        if not df_v.empty:
            print(f"Строк: {len(df_v)}")
            print(df_v.head(20).to_string(index=False))
    except Exception as e:
        print(f"API не поддерживает этот запрос (это нормально): {e}")


if __name__ == "__main__":
    main()
