"""
Выгружает источники трафика по каждому видео канала.
Показывает, ОТКУДА приходят зрители: рекомендации (Browse/Suggested),
поиск (Search), внешние ссылки и т.д.

Это ключевая метрика: если SUBSCRIBER+RELATED_VIDEO < 50% — алгоритм не продвигает видео.

Использует тот же token_video.json, что и fetch_video_report.py.
Запуск: python fetch_traffic_sources.py
"""

import os
import sys
import datetime
import time
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

VIDEO_IDS = [
    ("vyEer_SFc3M", "Чернобыль звери"),
    ("qRE5nQ15p0E", "Маяк/Карачай"),
    ("AGdOUblOl1s", "Ракетные шахты"),
    ("IHjROJiFo3c", "Аральское море"),
    ("xqZcaako6_o", "Колыма"),
    ("ZkOJ8vKrZzA", "Семипалатинск"),
    ("mcHyhcorjII", "Рыжий лес"),
    ("nVrYVJZOBlo", "Новая Земля"),
    ("4uwnkorhxXc", "Припять дом"),
    ("RObXEmfDVV0", "Фукусима"),
    ("olR8WVAr5TY", "ЗФИ"),
    ("uvtYW2vgPXQ", "Рыбы Припяти"),
]


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


def fetch_traffic_for_video(yta, video_id, start, end):
    """Источники трафика для ОДНОГО видео (через фильтр, не dimension)."""
    resp = yta.reports().query(
        ids="channel==MINE",
        startDate=start,
        endDate=end,
        metrics="views,estimatedMinutesWatched",
        dimensions="insightTrafficSourceType",
        filters=f"video=={video_id}",
        sort="-views",
    ).execute()
    cols = [h["name"] for h in resp["columnHeaders"]]
    return pd.DataFrame(resp.get("rows", []), columns=cols)


def main():
    creds = get_credentials()
    yta = build("youtubeAnalytics", "v2", credentials=creds)
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
        algo = df_ch.loc[
            df_ch["insightTrafficSourceType"].isin(
                ["SUBSCRIBER", "RELATED_VIDEO", "YT_SEARCH"]
            ),
            "share_pct",
        ].sum()
        print(f"\nАлгоритмический трафик (подписчики + рекомендации + поиск): {algo:.1f}%")

    # 2. Трафик по каждому видео отдельно
    print("\n=== Источники трафика по видео ===")
    all_rows = []
    for vid, name in VIDEO_IDS:
        print(f"  {name}...", end=" ", flush=True)
        try:
            df_v = fetch_traffic_for_video(yta, vid, START_DATE, end)
            if not df_v.empty:
                df_v["video_id"] = vid
                df_v["video_name"] = name
                all_rows.append(df_v)
                total_v = df_v["views"].sum()
                sub = df_v.loc[
                    df_v["insightTrafficSourceType"] == "SUBSCRIBER", "views"
                ].sum()
                rel = df_v.loc[
                    df_v["insightTrafficSourceType"] == "RELATED_VIDEO", "views"
                ].sum()
                algo_pct = (sub + rel) / total_v * 100 if total_v > 0 else 0
                print(
                    f"{total_v:>10,} просм. | "
                    f"подписчики {sub / total_v * 100:4.1f}% | "
                    f"рекоменд. {rel / total_v * 100:4.1f}% | "
                    f"алго {algo_pct:4.1f}%"
                )
            else:
                print("нет данных")
            time.sleep(0.3)
        except Exception as e:
            print(f"ошибка: {e}")

    if all_rows:
        df_all = pd.concat(all_rows, ignore_index=True)
        path_all = os.path.join(OUTPUT_DIR, "traffic_per_video.csv")
        df_all.to_csv(path_all, index=False)
        print(f"\nСохранено: {path_all}")

        # Сводная таблица
        pivot = df_all.pivot_table(
            index=["video_id", "video_name"],
            columns="insightTrafficSourceType",
            values="views",
            aggfunc="sum",
            fill_value=0,
        )
        pivot["TOTAL"] = pivot.sum(axis=1)
        if "SUBSCRIBER" in pivot.columns and "RELATED_VIDEO" in pivot.columns:
            pivot["ALGO_PCT"] = (
                (pivot["SUBSCRIBER"] + pivot["RELATED_VIDEO"]) / pivot["TOTAL"] * 100
            ).round(1)
        pivot = pivot.sort_values("TOTAL", ascending=False)

        path_pivot = os.path.join(OUTPUT_DIR, "traffic_pivot.csv")
        pivot.to_csv(path_pivot)
        print(f"Сводная таблица: {path_pivot}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n!!! ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
    input("\nНажмите Enter, чтобы закрыть окно...")
