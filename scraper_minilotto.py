"""
Scraper wyników Mini Lotto z megalotto.pl
Zapisuje wszystko do data/minilotto.json (jeden plik)
Aktualizuje się przez GitHub Actions 1x dziennie (losowanie ~22:00)
"""
import requests
import json
import re
import time
import os
from datetime import datetime
from bs4 import BeautifulSoup

BASE_URL = "https://megalotto.pl/wyniki/mini-lotto/losowania-z-roku-{year}"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; LottoScraper/1.0)"}
DATA_DIR = "data"
OUTPUT_FILE = os.path.join(DATA_DIR, "minilotto.json")
CURRENT_YEAR = datetime.now().year
START_YEAR = 1981


def parse_page(html):
    """Parsuje stronę roczną mini lotto — zwraca listę losowań."""
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
                    while j < len(lines) and len(nums) < 5:
                        line = lines[j]
                        if re.match(r'^\d{1,2}$', line):
                            n = int(line)
                            if 1 <= n <= 42:
                                nums.append(n)
                        elif line.startswith("Wygrane"):
                            break
                        j += 1

                    if len(nums) == 5:
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
    print(f"Scrapuję Mini Lotto {year}...", end=" ", flush=True)
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        draws = parse_page(r.text)
        print(f"{len(draws)} losowań")
        return draws
    except Exception as e:
        print(f"BŁĄD: {e}")
        return []


def load_all():
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE) as f:
            return json.load(f)
    return []


def save_all(draws):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(draws, f, ensure_ascii=False)
    print(f"Zapisano {len(draws)} losowań → {OUTPUT_FILE}")


def run_full():
    """Pierwsze uruchomienie — pobiera całe archiwum od 1981."""
    all_draws = []
    for year in range(START_YEAR, CURRENT_YEAR + 1):
        draws = scrape_year(year)
        all_draws.extend(draws)
        time.sleep(1)
    # Sortuj od najnowszego
    all_draws.sort(key=lambda x: x["no"], reverse=True)
    save_all(all_draws)
    print(f"Pełny scraping zakończony. Łącznie: {len(all_draws)} losowań")


def run_update():
    """Aktualizacja — tylko bieżący rok, dodaje nowe losowania."""
    existing = load_all()
    existing_nos = {d["no"] for d in existing}
    max_no = max(existing_nos, default=0)

    fresh = scrape_year(CURRENT_YEAR)
    if not fresh:
        return

    new = [d for d in fresh if d["no"] not in existing_nos]
    if new:
        all_draws = new + existing
        all_draws.sort(key=lambda x: x["no"], reverse=True)
        save_all(all_draws)
        print(f"Dodano {len(new)} nowych losowań")
    else:
        print("Brak nowych losowań")


if __name__ == "__main__":
    import sys
    if "--full" in sys.argv:
        run_full()
    else:
        run_update()
