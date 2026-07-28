"""
Scraper wyników Multi Multi z megalotto.pl
Zapisuje do data/ jako pliki JSON per rok
Data i godzina w formacie UTC ISO 8601
"""
import requests
import json
import re
import time
import os
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo

BASE_URL = "https://megalotto.pl/wyniki/multi-multi/losowania-z-roku-{year}"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; LottoScraper/1.0)"}
DATA_DIR = "data"
CURRENT_YEAR = datetime.now().year
START_YEAR = 1996
TZ_PL = ZoneInfo("Europe/Warsaw")


def to_utc(date_str, time_str):
    """
    Konwertuje datę DD.MM.YYYY i godzinę HH:MM (czas warszawski) na UTC ISO 8601.
    Przykład: "27.07.2026", "22:00" → "2026-07-27T20:00:00Z"
    """
    try:
        dd, mm, yyyy = date_str.split(".")
        hh, mi = time_str.split(":")
        local_dt = datetime(int(yyyy), int(mm), int(dd), int(hh), int(mi),
                            tzinfo=TZ_PL)
        utc_dt = local_dt.astimezone(timezone.utc)
        return utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None


def parse_page(html):
    """Parsuje stronę roczną megalotto.pl przez tagi HTML."""
    soup = BeautifulSoup(html, "html.parser")
    results = []
    all_li = soup.find_all("li")

    i = 0
    while i < len(all_li):
        text = all_li[i].get_text(strip=True)
        m = re.match(r'^(\d+)\.$', text)
        if m:
            draw_no = int(m.group(1))
            if i + 1 < len(all_li):
                date_text = all_li[i+1].get_text(strip=True)
                date_m = re.match(r'^(\d{2})-(\d{2})-(\d{4})$', date_text)
                if date_m:
                    draw_date = f"{date_m.group(1)}.{date_m.group(2)}.{date_m.group(3)}"
                    draw_time = None
                    nums = []
                    j = i + 2

                    while j < len(all_li) and len(nums) < 20:
                        li_text = all_li[j].get_text(strip=True)

                        # Godzina z linku do wygranych (pewna metoda)
                        link = all_li[j].find("a", href=True)
                        if link:
                            href = link.get("href", "")
                            t = re.search(r'wygrane-z-dnia-(\d{2}:\d{2})-', href)
                            if t:
                                draw_time = t.group(1)
                            break

                        # Liczba: "22:0019" lub samo "14"
                        time_num = re.match(r'^(\d{2}:\d{2})(\d{1,2})$', li_text)
                        if time_num:
                            if draw_time is None:
                                draw_time = time_num.group(1)
                            n = int(time_num.group(2))
                            if 1 <= n <= 80:
                                nums.append(n)
                        elif re.match(r'^\d{1,2}$', li_text):
                            n = int(li_text)
                            if 1 <= n <= 80:
                                nums.append(n)
                        j += 1

                    if len(nums) == 20:
                        draw_time = draw_time or "22:00"  # fallback
                        utc_dt = to_utc(draw_date, draw_time)
                        results.append({
                            "no": draw_no,
                            "date": draw_date,
                            "time": draw_time,
                            "utc": utc_dt,
                            "numbers": sorted(nums)
                        })
                    i = j
                    continue
        i += 1

    return results


def scrape_year(year):
    url = BASE_URL.format(year=year)
    print(f"Scrapuję {year}...", end=" ", flush=True)
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        draws = parse_page(r.text)
        print(f"{len(draws)} losowań")
        return draws
    except Exception as e:
        print(f"BŁĄD: {e}")
        return []


def load_year(year):
    path = os.path.join(DATA_DIR, f"draws-{year}.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return []


def save_year(year, draws):
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, f"draws-{year}.json")
    with open(path, "w") as f:
        json.dump(draws, f, ensure_ascii=False)


def save_index():
    index = []
    for year in range(START_YEAR, CURRENT_YEAR + 1):
        path = os.path.join(DATA_DIR, f"draws-{year}.json")
        if os.path.exists(path):
            with open(path) as f:
                draws = json.load(f)
            if draws:
                index.append({
                    "year": year,
                    "count": len(draws),
                    "first": draws[-1]["date"],
                    "last": draws[0]["date"]
                })

    all_recent = []
    for entry in reversed(index):
        year_draws = load_year(entry["year"])
        all_recent = year_draws + all_recent
        if len(all_recent) >= 200:
            break
    all_recent = all_recent[:200]
    total = sum(e["count"] for e in index)

    with open(os.path.join(DATA_DIR, "index.json"), "w") as f:
        json.dump({"years": index, "total": total}, f, ensure_ascii=False)

    with open(os.path.join(DATA_DIR, "latest-200.json"), "w") as f:
        json.dump(all_recent, f, ensure_ascii=False)

    print(f"Index: {total} losowań | Latest-200: {len(all_recent)}")


def run_full():
    for year in range(START_YEAR, CURRENT_YEAR + 1):
        draws = scrape_year(year)
        if draws:
            save_year(year, draws)
        time.sleep(1)
    save_index()


def run_update():
    existing = load_year(CURRENT_YEAR)
    fresh = scrape_year(CURRENT_YEAR)
    if not fresh:
        return
    merged = {d["no"]: d for d in existing}
    new_count = sum(1 for d in fresh if d["no"] not in merged)
    for d in fresh:
        merged[d["no"]] = d
    result = sorted(merged.values(), key=lambda x: x["no"], reverse=True)
    save_year(CURRENT_YEAR, result)
    save_index()
    print(f"Nowych losowań: {new_count}")


if __name__ == "__main__":
    import sys
    if "--full" in sys.argv:
        run_full()
    else:
        run_update()
