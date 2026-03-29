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


def get_match_detail(match_id):
    try:
        r = requests.get(f"{API_BASE}/football-get-match-detail",
                         headers=HEADERS,
                         params={"eventid": match_id},
                         timeout=15)
        data = r.json()
        print(f"  Detail для {match_id}: {str(data)[:400]}")
        return data.get("response", {})
    except Exception as e:
        print(f"[API] Ошибка detail {match_id}: {e}")
        return {}


def find_goals_in_detail(detail, team_id, team_name):
    """
    Ищем голы в любом месте структуры detail.
    Возвращаем список минут голов команды.
    """
    goal_minutes = []

    def search(obj, depth=0):
        if depth > 6:
            return
        if isinstance(obj, list):
            for item in obj:
                search(item, depth + 1)
        elif isinstance(obj, dict):
            # Проверяем — это событие гола?
            obj_str = str(obj).lower()
            is_goal = ("goal" in obj_str and
                       "missed" not in obj_str and
                       "owngoal" not in obj_str.replace("own goal", "X"))

            if is_goal:
                # Ищем минуту
                minute = None
                for k in ["minute", "time", "elapsed", "min"]:
                    if k in obj and obj[k] is not None:
                        try:
                            minute = int(str(obj[k]).replace("'", "").strip())
                            break
                        except:
                            pass

                # Ищем команду
                team_match = False
                for k in ["teamId", "team_id", "teamID"]:
                    if k in obj and str(obj[k]) == str(team_id):
                        team_match = True
                        break
                if not team_match:
                    for k in ["teamName", "team_name", "team"]:
                        if k in obj:
                            val = obj[k]
                            name = val.get("name", "") if isinstance(val, dict) else str(val)
                            if team_name.lower() in name.lower() or name.lower() in team_name.lower():
                                team_match = True
                                break

                if team_match and minute is not None:
                    if not (FIRST_HALF_ONLY and minute > 45):
                        goal_minutes.append(minute)
                        return  # не углубляемся дальше в этот объект

            for v in obj.values():
                search(v, depth + 1)

    search(detail)
    return goal_minutes


def check_goal_burst(goal_minutes):
    goal_minutes = sorted(goal_minutes)
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

    # Пропускаем если у обеих команд уже есть уведомление
    key_home = f"{match_id}_{home_id}"
    key_away = f"{match_id}_{away_id}"
    if key_home in notified and key_away in notified:
        return

    detail = get_match_detail(match_id)
    time.sleep(0.5)

    for team_name, team_id, key in [
        (home_name, home_id, key_home),
        (away_name, away_id, key_away)
    ]:
        if key in notified:
            continue

        goal_minutes = find_goals_in_detail(detail, team_id, team_name)
        triggered, trigger_minute = check_goal_burst(goal_minutes)

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
    print("🤖 Бот запущен! v6")
    print(f"📋 {GOALS_THRESHOLD} гола за {MINUTES_WINDOW} мин в 1-м тайме")
    print("=" * 50)

    send_telegram("✅ <b>Бот v6 запущен!</b>\nСлежу за всеми лигами 👀")

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
