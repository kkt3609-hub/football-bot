import requests
import time
from datetime import datetime

# ============================================================
TELEGRAM_TOKEN = "8031024083:AAE8gFsy6RhRHIXa6gcRk96bSk3cG8Ifhjg"
TELEGRAM_CHAT_ID = "168902166"
FOOTBALL_API_KEY = "de56d8553amsh4f25358ccb4626ep15bca0jsn22d4391773a3"

GOALS_THRESHOLD = 2
MINUTES_WINDOW = 20
FIRST_HALF_ONLY = True
CHECK_INTERVAL = 60
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
        r = requests.get(f"{API_BASE}/football-current-live",
                         headers=HEADERS, timeout=15)
        print(f"  Live endpoint status: {r.status_code}")
        data = r.json()
        print(f"  Ключи: {list(data.keys()) if isinstance(data, dict) else type(data)}")

        # Ищем матчи
        for key in ["response", "matches", "data", "match", "livescores", "events", "results"]:
            if isinstance(data, dict) and key in data:
                val = data[key]
                if isinstance(val, list) and len(val) > 0:
                    print(f"  Найдено {len(val)} матчей в ключе '{key}'")
                    print(f"  Пример матча: {str(val[0])[:200]}")
                    return val

        print(f"  Полный ответ: {str(data)[:300]}")
        return []
    except Exception as e:
        print(f"[API] Ошибка: {e}")
        return []


def get_match_events(match_id):
    # Смотрим Events/Matches раздел
    for path, param_name in [
        ("/football-get-match-events", "matchId"),
        ("/football-event-match", "matchId"),
        ("/football-get-events", "matchId"),
    ]:
        try:
            r = requests.get(f"{API_BASE}{path}",
                             headers=HEADERS,
                             params={param_name: match_id},
                             timeout=15)
            if r.status_code != 200:
                continue
            data = r.json()
            for key in ["response", "events", "data", "event", "incidents"]:
                if isinstance(data, dict) and key in data:
                    val = data[key]
                    if isinstance(val, list):
                        return val
        except:
            pass
    return []


def extract_match_info(match):
    def g(obj, *keys):
        for k in keys:
            if isinstance(obj, dict) and k in obj and obj[k] is not None:
                return obj[k]
        return None

    fixture_id = g(match, "id", "matchId", "fixtureId")
    if isinstance(fixture_id, dict):
        fixture_id = fixture_id.get("id")

    teams = match.get("teams", {})
    home_obj = g(match, "homeTeam", "home_team") or teams.get("home", {})
    away_obj = g(match, "awayTeam", "away_team") or teams.get("away", {})
    home = home_obj.get("name", "Хозяева") if isinstance(home_obj, dict) else str(home_obj)
    away = away_obj.get("name", "Гости") if isinstance(away_obj, dict) else str(away_obj)

    league_obj = g(match, "league", "competition", "tournament")
    league = league_obj.get("name", "Лига") if isinstance(league_obj, dict) else str(league_obj or "Лига")
    country = league_obj.get("country", "") if isinstance(league_obj, dict) else ""

    score = g(match, "score", "goals", "result") or {}
    home_score = (score.get("home") or score.get("homeTeam") or g(match, "homeScore") or 0)
    away_score = (score.get("away") or score.get("awayTeam") or g(match, "awayScore") or 0)

    status = g(match, "status", "fixture") or {}
    minute = status.get("elapsed") or status.get("minute") or g(match, "minute", "elapsed") or 0
    if isinstance(minute, dict):
        minute = minute.get("elapsed", 0) or 0

    return fixture_id, home, away, league, country, int(home_score or 0), int(away_score or 0), int(minute or 0)


def check_goal_burst(events, team_name):
    goal_minutes = []
    for event in events:
        etype = str(event.get("type", event.get("eventType", event.get("kind", "")))).lower()
        if "goal" not in etype:
            continue

        detail = str(event.get("detail", event.get("description", ""))).lower()
        if "missed" in detail or "own" in detail:
            continue

        team_obj = event.get("team", event.get("teamName", ""))
        team = team_obj.get("name", "") if isinstance(team_obj, dict) else str(team_obj)
        if not team or (team_name.lower() not in team.lower() and team.lower() not in team_name.lower()):
            continue

        time_obj = event.get("time", event.get("minute", event.get("elapsed", 0)))
        minute = time_obj.get("elapsed", 0) if isinstance(time_obj, dict) else int(time_obj or 0)

        if FIRST_HALF_ONLY and minute > 45:
            continue
        goal_minutes.append(minute)

    goal_minutes.sort()
    for i in range(len(goal_minutes)):
        for j in range(i + 1, len(goal_minutes)):
            if goal_minutes[j] - goal_minutes[i] <= MINUTES_WINDOW:
                if (j - i + 1) >= GOALS_THRESHOLD:
                    return True, goal_minutes[j]
    return False, None


def process_match(match):
    fixture_id, home, away, league, country, home_score, away_score, minute = extract_match_info(match)
    if not fixture_id:
        return
    if FIRST_HALF_ONLY and minute > 45:
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
    print("🤖 Бот запущен! v3")
    print(f"📋 {GOALS_THRESHOLD} гола за {MINUTES_WINDOW} мин в 1-м тайме")
    print("=" * 50)

    send_telegram("✅ <b>Бот v3 запущен!</b>\nСлежу за всеми лигами 👀")

    while True:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Проверяю матчи...")
        matches = get_live_matches()
        print(f"  Итого: {len(matches)}")
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
