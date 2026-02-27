
import requests, json, time

BASE = "https://ncaa-api.henrygd.me"

def get(path):
    url = BASE + path
    print(f"\nGET {url}")
    r = requests.get(url, timeout=15)
    print(f"  Status: {r.status_code}")
    time.sleep(0.3)
    if r.status_code == 200:
        return r.json()
    print(f"  Body: {r.text[:300]}")
    return None

# Test schedule for each month of 2024 season
for month in ["08", "09", "10", "11"]:
    data = get(f"/schedule/soccer-women/d1/2024/{month}")
    if data:
        dates = data.get("gameDates", [])
        active = [d for d in dates if d.get("games", 0) > 0]
        print(f"  gameDates total: {len(dates)}, with games: {len(active)}")
        if active:
            print(f"  First active date: {active[0]}")
    else:
        print("  No data returned")
