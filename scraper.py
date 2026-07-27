"""
Scraper wyników Multi Multi z megalotto.pl
Zapisuje do data/draws.json (podzielone na roczniki)
"""
import requests
import json
import re
import time
import os
from datetime import datetime
from bs4 import BeautifulSoup

BASE_URL = "https://megalotto.pl/wyniki/multi-multi/losowania-z-roku-{year}"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; LottoScraper/1.0)"}
DATA_DIR = "data"
CURRENT_YEAR = datetime.now().year
START_YEAR = 1996


def parse_page(html):
    """Parsuje stronę roczną megalotto.pl — zwraca listę losowań."""
    soup = BeautifulSoup(html, "html.parser")
    results = []

    text = soup.get_text("\n")
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    i = 0
    while i < len(lines):
        m = re.match(r'^(\d+)\.$', lines[i])
        if m:
            draw_no = int(m.group(1))
            if i + 1 < len(lines):
                date_m = re.match(r'^(\d{2})-(\d{2})-(\d{4})$', lines[i+1])
                if date_m:
                    draw_date = f"{date_m.group(1)}.{date_m.group(2)}.{date_m.group(3)}"
                    nums = []
                    j = i + 2
                    while j < len(lines) and len(nums) < 20:
                        line = lines[j]
                        time_num = re.match(r'^\d{2}:\d{2}(\d+)$', line)
                        if time_num:
                            n = int(time_num.group(1))
                            if 1 <= n <= 80:
                                nums.append(n)
                        elif re.match(r'^\d{1,2}$', line):
                            n = int(line)
                            if 1 <= n <= 80:
                                nums.append(n)
                        elif line.startswith("Wygrane"):
                            break
                        j += 1

                    if len(nums) == 20:
                        results.append({
                            "no": draw_no,
                            "date": draw_date,
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
    """Zapisuje index.json z metadanymi wszystkich roczników."""
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

    # Zapisz też ostatnie 200 losowań jako osobny plik (szybkie ładowanie)
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

    print(f"Index: {total} losowań, {len(index)} roczników")
    print(f"Latest-200: {len(all_recent)} losowań")


def run_full():
    """Pierwsze uruchomienie — pobiera całe archiwum."""
    for year in range(START_YEAR, CURRENT_YEAR + 1):
        draws = scrape_year(year)
        if draws:
            save_year(year, draws)
        time.sleep(1)
    save_index()


def run_update():
    """Aktualizacja — tylko bieżący rok."""
    existing = load_year(CURRENT_YEAR)
    max_no = max((d["no"] for d in existing), default=0)

    fresh = scrape_year(CURRENT_YEAR)
    if not fresh:
        return

    # Połącz stare i nowe, deduplikuj po numerze
    merged = {d["no"]: d for d in existing}
    new_count = 0
    for d in fresh:
        if d["no"] not in merged:
            new_count += 1
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
