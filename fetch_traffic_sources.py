"""
Выгружает источники трафика по каждому видео канала.
Показывает, ОТКУДА приходят зрители: рекомендации (Browse/Suggested),
поиск (Search), внешние ссылки и т.д.

Это ключевая метрика: если Browse+Suggested < 50% — алгоритм не продвигает видео.

Использует тот же token_video.json, что и fetch_video_report.py.
Запуск: python fetch_traffic_sources.py
"""

import os
import datetime
import pandas as pd
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
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
            flow.redirect_uri = "http://localhost"
            auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
            print("\n1. Откройте эту ссылку в браузере и разрешите доступ:\n")
            print(auth_url)
            print(
                "\n2. Браузер покажет ошибку/пустую страницу — это нормально."
                "\n   В адресной строке найдите часть 'code=...' — скопируйте всё после"
                "\n   'code=' и до следующего '&'."
            )
            code = input("\n3. Вставьте code сюда: ").strip()
            flow.fetch_token(code=code)
            creds = flow.credentials
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return creds


def fetch_channel_traffic(yta, start, end):
    """Источники трафика по всему каналу."""
    resp = yta.reports().query(
        ids="channel==MINE",
        startDate=start,
        endDate=end,
        metrics="views,estimatedMinutesWatched",
        dimensions="insightTrafficSourceType",
        sort="-views",
    ).execute()
    cols = [h["name"] for h in resp["columnHeaders"]]
    return pd.DataFrame(resp.get("rows", []), columns=cols)


def fetch_video_list(youtube_data):
    """Получает список видео канала для маппинга ID → название."""
    videos = {}
    request = youtube_data.search().list(
        part="snippet",
        forMine=True,
        type="video",
        maxResults=50,
        order="date",
    )
    while request:
        response = request.execute()
        for item in response.get("items", []):
            vid = item["id"]["videoId"]
            videos[vid] = item["snippet"]["title"]
        request = youtube_data.search().list_next(request, response)
    return videos


def fetch_traffic_per_video(yta, start, end):
    """Источники трафика в разрезе видео."""
    resp = yta.reports().query(
        ids="channel==MINE",
        startDate=start,
        endDate=end,
        metrics="views,estimatedMinutesWatched",
        dimensions="video,insightTrafficSourceType",
        sort="-views",
        maxResults=500,
    ).execute()
    cols = [h["name"] for h in resp["columnHeaders"]]
    return pd.DataFrame(resp.get("rows", []), columns=cols)


def main():
    creds = get_credentials()
    yta = build("youtubeAnalytics", "v2", credentials=creds)
    youtube_data = build("youtube", "v3", credentials=creds)
    end = datetime.date.today().isoformat()
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 1. Трафик по всему каналу
    print("=== Источники трафика (весь канал) ===")
    df_ch = fetch_channel_traffic(yta, START_DATE, end)
    path_ch = os.path.join(OUTPUT_DIR, "traffic_channel.csv")
    df_ch.to_csv(path_ch, index=False)
    print(f"Сохранено: {path_ch}")
    if not df_ch.empty:
        total = df_ch["views"].sum()
        df_ch["share_pct"] = (df_ch["views"] / total * 100).round(1)
        print(df_ch.to_string(index=False))
        browse = df_ch.loc[
            df_ch["insightTrafficSourceType"].isin(["SUBSCRIBER", "SUGGESTED", "YT_SEARCH"]),
            "share_pct",
        ].sum()
        print(f"\nAlgorithmic (Browse+Suggested+Search): {browse:.1f}%")

    # 2. Трафик в разрезе видео
    print("\n=== Источники трафика по видео ===")
    try:
        df_v = fetch_traffic_per_video(yta, START_DATE, end)
        path_v = os.path.join(OUTPUT_DIR, "traffic_per_video.csv")
        df_v.to_csv(path_v, index=False)
        print(f"Сохранено: {path_v}")

        if not df_v.empty:
            # Маппинг ID → название
            titles = fetch_video_list(youtube_data)

            # Сводная таблица: видео × источник → просмотры
            pivot = df_v.pivot_table(
                index="video",
                columns="insightTrafficSourceType",
                values="views",
                aggfunc="sum",
                fill_value=0,
            )
            pivot["total"] = pivot.sum(axis=1)
            pivot = pivot.sort_values("total", ascending=False)
            pivot["title"] = pivot.index.map(lambda v: titles.get(v, v[:12]))

            path_pivot = os.path.join(OUTPUT_DIR, "traffic_pivot.csv")
            pivot.to_csv(path_pivot)
            print(f"Сводная таблица: {path_pivot}")
            print(pivot.head(15).to_string())
    except Exception as e:
        print(f"Ошибка при запросе по видео: {e}")
        print("Канальные данные выше всё равно сохранены.")


if __name__ == "__main__":
    main()
