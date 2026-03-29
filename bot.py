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
    """Пробуем разные endpoints для live матчей"""
    endpoints = [
        ("/football-get-all-live-matches", {}),
        ("/football-get-matches-by-date", {"date": datetime.now().strftime("%Y-%m-%d")}),
        ("/football-get-livescores", {}),
        ("/livescores", {}),
    ]

    for path, params in endpoints:
        try:
            r = requests.get(f"{API_BASE}{path}",
                             headers=HEADERS,
                             params=params,
                             timeout=15)
            print(f"  Endpoint {path}: status={r.status_code}")
            if r.status_code != 200:
                continue

            data = r.json()
            print(f"  Ключи ответа: {list(data.keys()) if isinstance(data, dict) else type(data)}")

            # Ищем список матчей в любом месте ответа
            matches = find_matches(data)
            if matches:
                print(f"  Найдено матчей: {len(matches)} через {path}")
                return matches
        except Exception as e:
            print(f"  Ошибка {path}: {e}")

    return []


def find_matches(data):
    """Рекурсивно ищем список матчей в ответе API"""
    if isinstance(data, list) and len(data) > 0:
        if isinstance(data[0], dict):
            return data

    if isinstance(data, dict):
        # Прямые ключи где могут быть матчи
        for key in ["response", "matches", "data", "match", "fixtures",
                    "livescores", "events", "results", "games"]:
            if key in data:
                val = data[key]
                if isinstance(val, list) and len(val) > 0:
                    return val
                if isinstance(val, dict):
                    result = find_matches(val)
                    if result:
                        return result

    return []


def get_match_events(match_id):
    """Получить события матча"""
    endpoints = [
        f"/football-get-match-events",
        f"/football-get-events",
    ]
    params_variants = [
        {"matchId": match_id},
        {"fixtureId": match_id},
        {"id": match_id},
    ]

    for path in endpoints:
        for params in params_variants:
            try:
                r = requests.get(f"{API_BASE}{path}",
                                 headers=HEADERS,
                                 params=params,
                                 timeout=15)
                if r.status_code != 200:
                    continue
                data = r.json()
                events = find_events(data)
                if events:
                    return events
            except:
                pass
    return []


def find_events(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ["response", "events", "data", "event", "incidents"]:
            if key in data:
                val = data[key]
                if isinstance(val, list):
                    return val
    return []


def extract_match_info(match):
    """Извлечь инфо о матче из любой структуры"""
    def get_val(obj, *keys):
        for k in keys:
            if isinstance(obj, dict) and k in obj:
                v = obj[k]
                if v is not None:
                    return v
        return None

    fixture_id = get_val(match, "id", "matchId", "fixtureId", "fixture_id")
    if isinstance(fixture_id, dict):
        fixture_id = fixture_id.get("id")

    # Команды
    home_obj = get_val(match, "homeTeam", "home_team", "home")
    away_obj = get_val(match, "awayTeam", "away_team", "away")
    teams = match.get("teams", {})

    if isinstance(home_obj, dict):
        home = home_obj.get("name", "Хозяева")
    elif isinstance(home_obj, str):
        home = home_obj
    elif teams:
        home = teams.get("home", {}).get("name", "Хозяева")
    else:
        home = "Хозяева"

    if isinstance(away_obj, dict):
        away = away_obj.get("name", "Гости")
    elif isinstance(away_obj, str):
        away = away_obj
    elif teams:
        away = teams.get("away", {}).get("name", "Гости")
    else:
        away = "Гости"

    # Лига
    league_obj = get_val(match, "league", "competition", "tournament")
    if isinstance(league_obj, dict):
        league = league_obj.get("name", "Лига")
        country = league_obj.get("country", "")
    else:
        league = str(league_obj) if league_obj else get_val(match, "leagueName", "competitionName") or "Лига"
        country = ""

    # Счёт
    score_obj = get_val(match, "score", "goals", "result")
    if isinstance(score_obj, dict):
        home_score = score_obj.get("home", score_obj.get("homeTeam", 0)) or 0
        away_score = score_obj.get("away", score_obj.get("awayTeam", 0)) or 0
    else:
        home_score = get_val(match, "homeScore", "home_score") or 0
        away_score = get_val(match, "awayScore", "away_score") or 0

    # Минута
    status_obj = get_val(match, "status", "fixture")
    if isinstance(status_obj, dict):
        minute = status_obj.get("elapsed", status_obj.get("minute", 0)) or 0
    else:
        minute = get_val(match, "minute", "elapsed", "time") or 0
    if isinstance(minute, dict):
        minute = minute.get("elapsed", 0) or 0

    return fixture_id, home, away, league, country, home_score, away_score, int(minute or 0)


def check_goal_burst(events, team_name):
    goal_minutes = []
    for event in events:
        # Тип события
        event_type = ""
        for k in ["type", "eventType", "incident_type", "kind"]:
            if k in event:
                event_type = str(event[k]).lower()
                break

        if "goal" not in event_type:
            continue

        # Детали (пропускаем пенальти и автоголы)
        detail = ""
        for k in ["detail", "eventDetail", "description"]:
            if k in event:
                detail = str(event[k]).lower()
                break
        if "missed" in detail or "own" in detail:
            continue

        # Команда
        team = ""
        team_obj = event.get("team", event.get("teamName", event.get("team_name", "")))
        if isinstance(team_obj, dict):
            team = team_obj.get("name", "")
        else:
            team = str(team_obj)

        if not team or (team_name.lower() not in team.lower() and team.lower() not in team_name.lower()):
            continue

        # Минута
        minute = 0
        time_obj = event.get("time", event.get("minute", event.get("elapsed", 0)))
        if isinstance(time_obj, dict):
            minute = time_obj.get("elapsed", 0) or 0
        else:
            minute = int(time_obj or 0)

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
    print("🤖 Бот запущен!")
    print(f"📋 Алгоритм: {GOALS_THRESHOLD} гола за {MINUTES_WINDOW} мин в 1-м тайме")
    print("=" * 50)

    send_telegram(
        "✅ <b>Бот перезапущен (v2)!</b>\n\n"
        f"Алгоритм: {GOALS_THRESHOLD} гола за {MINUTES_WINDOW} мин в первом тайме\n"
        "Слежу за всеми лигами 👀"
    )

    while True:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Проверяю матчи...")
        matches = get_live_matches()
        print(f"  Итого матчей: {len(matches)}")

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
