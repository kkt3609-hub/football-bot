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
        data = r.json()
        matches = data.get("response", {}).get("live", [])
        print(f"  Матчей в эфире: {len(matches)}")
        return matches
    except Exception as e:
        print(f"[API] Ошибка: {e}")
        return []


def get_match_events(match_id):
    try:
        r = requests.get(f"{API_BASE}/football-get-match-events",
                         headers=HEADERS,
                         params={"matchId": match_id},
                         timeout=15)
        data = r.json()
        print(f"  Events для {match_id}: {str(data)[:300]}")
        response = data.get("response", {})
        if isinstance(response, list):
            return response
        if isinstance(response, dict):
            for key in ["events", "incidents", "data"]:
                if key in response and isinstance(response[key], list):
                    return response[key]
        return []
    except Exception as e:
        print(f"[API] Ошибка событий {match_id}: {e}")
        return []


def check_goal_burst(events, team_id, team_name):
    goal_minutes = []
    for e in events:
        etype = str(e.get("type", "")).lower()
        if "goal" not in etype:
            continue
        detail = str(e.get("detail", e.get("subtype", ""))).lower()
        if "own" in detail or "miss" in detail:
            continue

        e_team_id = str(e.get("teamId", e.get("team_id", "")))
        team_obj = e.get("team", {})
        e_team_name = team_obj.get("name", "") if isinstance(team_obj, dict) else str(team_obj)

        team_match = (e_team_id == str(team_id)) or \
                     (team_name.lower() in e_team_name.lower()) or \
                     (e_team_name.lower() in team_name.lower())
        if not team_match:
            continue

        minute = int(e.get("minute", e.get("time", 0)) or 0)
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
    match_id = match.get("id")
    if not match_id:
        return

    home = match.get("home", {})
    away = match.get("away", {})
    home_name = home.get("name", "Хозяева")
    away_name = away.get("name", "Гости")
    home_id = home.get("id")
    away_id = away.get("id")
    home_score = home.get("score", 0) or 0
    away_score = away.get("score", 0) or 0

    minute = match.get("minute") or match.get("elapsed") or 0
    try:
        minute = int(str(minute).replace("'", "").strip())
    except:
        minute = 0

    if FIRST_HALF_ONLY and minute > 45:
        return

    events = get_match_events(match_id)
    time.sleep(0.5)

    for team_name, team_id in [(home_name, home_id), (away_name, away_id)]:
        key = f"{match_id}_{team_id}"
        if key in notified:
            continue
        triggered, trigger_minute = check_goal_burst(events, team_id, team_name)
        if triggered:
            notified[key] = True
            message = (
                f"🔥 <b>АЛЕРТ: БЫСТРЫЕ ГОЛЫ!</b>\n\n"
                f"⚽ <b>{home_name} {home_score}–{away_score} {away_name}</b>\n\n"
                f"📊 <b>{team_name}</b> забила {GOALS_THRESHOLD} гола "
                f"за {MINUTES_WINDOW} минут в первом тайме!\n"
                f"⏱ Минута: {trigger_minute}'\n\n"
                f"🕐 {datetime.now().strftime('%H:%M:%S')}"
            )
            print(f"[АЛЕРТ] {team_name} | {home_name} vs {away_name}")
            send_telegram(message)


def main():
    print("=" * 50)
    print("🤖 Бот запущен! v5")
    print(f"📋 {GOALS_THRESHOLD} гола за {MINUTES_WINDOW} мин в 1-м тайме")
    print("=" * 50)

    send_telegram("✅ <b>Бот v5 запущен!</b>\nСлежу за всеми лигами 👀")

    while True:
        try:
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Проверяю матчи...")
            matches = get_live_matches()
            for match in matches:
                try:
                    process_match(match)
                except Exception as e:
                    print(f"  Ошибка матча: {e}")
            if len(notified) > 1000:
                notified.clear()
        except Exception as e:
            print(f"[ГЛАВНАЯ ОШИБКА] {e}")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
