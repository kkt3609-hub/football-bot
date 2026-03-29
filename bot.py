import requests
import time
from datetime import datetime

# ============================================================
#  НАСТРОЙКИ
# ============================================================
TELEGRAM_TOKEN = "8031024083:AAE8gFsy6RhRHIXa6gcRk96bSk3cG8Ifhjg"
TELEGRAM_CHAT_ID = "168902166"
FOOTBALL_API_KEY = "de56d8553amsh4f25358ccb4626ep15bca0jsn22d4391773a3"

# Алгоритм
GOALS_THRESHOLD = 2    # голов
MINUTES_WINDOW = 20    # за сколько минут
FIRST_HALF_ONLY = True # только первый тайм

CHECK_INTERVAL = 60    # проверка каждые 60 секунд
# ============================================================

API_BASE = "https://free-api-live-football-data.p.rapidapi.com"
HEADERS = {
    "x-rapidapi-key": FOOTBALL_API_KEY,
    "x-rapidapi-host": "free-api-live-football-data.p.rapidapi.com"
}

notified = {}


def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }, timeout=10)
        print(f"[TG] {r.status_code}")
    except Exception as e:
        print(f"[TG] Ошибка: {e}")


def get_live_matches():
    try:
        r = requests.get(f"{API_BASE}/football-get-all-live-matches",
                         headers=HEADERS, timeout=15)
        data = r.json()
        matches = data.get("response", data.get("matches", data.get("data", [])))
        if isinstance(matches, dict):
            matches = matches.get("match", [])
        return matches if isinstance(matches, list) else []
    except Exception as e:
        print(f"[API] Ошибка live матчей: {e}")
        return []


def get_match_events(fixture_id):
    try:
        r = requests.get(f"{API_BASE}/football-get-match-events",
                         headers=HEADERS,
                         params={"matchId": fixture_id},
                         timeout=15)
        data = r.json()
        events = data.get("response", data.get("events", data.get("data", [])))
        if isinstance(events, dict):
            events = events.get("event", [])
        return events if isinstance(events, list) else []
    except Exception as e:
        print(f"[API] Ошибка событий {fixture_id}: {e}")
        return []


def extract_match_info(match):
    fixture_id = (match.get("id") or match.get("matchId") or
                  match.get("fixture", {}).get("id") or str(match))
    home = (match.get("homeTeam", {}).get("name") or
            match.get("home_team") or
            match.get("teams", {}).get("home", {}).get("name") or "Хозяева")
    away = (match.get("awayTeam", {}).get("name") or
            match.get("away_team") or
            match.get("teams", {}).get("away", {}).get("name") or "Гости")
    league = (match.get("league", {}).get("name") or
              match.get("competition", {}).get("name") or
              match.get("leagueName") or "Лига")
    country = (match.get("league", {}).get("country") or
               match.get("competition", {}).get("country") or "")
    home_score = (match.get("homeScore") or match.get("score", {}).get("home") or
                  match.get("goals", {}).get("home") or 0)
    away_score = (match.get("awayScore") or match.get("score", {}).get("away") or
                  match.get("goals", {}).get("away") or 0)
    minute = (match.get("minute") or match.get("elapsed") or
              match.get("fixture", {}).get("status", {}).get("elapsed") or 0)
    return fixture_id, home, away, league, country, home_score, away_score, minute


def extract_event_info(event):
    event_type = (event.get("type") or event.get("eventType") or "").lower()
    team = (event.get("team", {}).get("name") or
            event.get("teamName") or
            event.get("team") or "")
    minute = (event.get("time", {}).get("elapsed") or
              event.get("minute") or
              event.get("elapsed") or 0)
    detail = (event.get("detail") or event.get("eventDetail") or "")
    return event_type, team, minute, detail


def check_goal_burst(events, team_name):
    goal_minutes = []
    for event in events:
        event_type, team, minute, detail = extract_event_info(event)
        if "goal" not in event_type:
            continue
        if "missed" in detail.lower() or "own" in detail.lower():
            continue
        if team_name.lower() not in team.lower() and team.lower() not in team_name.lower():
            continue
        if FIRST_HALF_ONLY and int(minute or 0) > 45:
            continue
        goal_minutes.append(int(minute or 0))

    goal_minutes.sort()
    for i in range(len(goal_minutes)):
        for j in range(i + 1, len(goal_minutes)):
            if goal_minutes[j] - goal_minutes[i] <= MINUTES_WINDOW:
                if (j - i + 1) >= GOALS_THRESHOLD:
                    return True, goal_minutes[j]
    return False, None


def process_match(match):
    fixture_id, home, away, league, country, home_score, away_score, minute = extract_match_info(match)
    if FIRST_HALF_ONLY and int(minute or 0) > 45:
        return
    events = get_match_events(fixture_id)
    time.sleep(0.5)
    for team_name in [home, away]:
        key = f"{fixture_id}_{team_name}"
        if key in notified:
            continue
        triggered, trigger_minute = check_goal_burst(events, team_name)
        if triggered:
            notified[key] = True
            message = (
                f"🔥 <b>АЛЕРТ: БЫСТРЫЕ ГОЛЫ!</b>\n\n"
                f"🏆 {league}" + (f" ({country})" if country else "") + "\n"
                f"⚽ <b>{home} {home_score}–{away_score} {away}</b>\n\n"
                f"📊 <b>{team_name}</b> забила {GOALS_THRESHOLD} гола "
                f"за {MINUTES_WINDOW} минут в первом тайме!\n"
                f"⏱ Минута: {trigger_minute}'\n\n"
                f"🕐 {datetime.now().strftime('%H:%M:%S')}"
            )
            print(f"[АЛЕРТ] {team_name} | {home} vs {away}")
            send_telegram(message)


def main():
    print("=" * 50)
    print("🤖 Бот запущен!")
    print(f"📋 Алгоритм: {GOALS_THRESHOLD} гола за {MINUTES_WINDOW} мин в 1-м тайме")
    print(f"⏱ Проверка каждые {CHECK_INTERVAL} секунд")
    print("=" * 50)

    send_telegram(
        "✅ <b>Бот запущен!</b>\n\n"
        f"Алгоритм: {GOALS_THRESHOLD} гола за {MINUTES_WINDOW} мин в первом тайме\n"
        "Слежу за всеми лигами 👀"
    )

    while True:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Проверяю матчи...")
        matches = get_live_matches()
        print(f"  Матчей в эфире: {len(matches)}")
        for match in matches:
            try:
                process_match(match)
            except Exception as e:
                print(f"  Ошибка: {e}")
        if len(notified) > 1000:
            notified.clear()
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
