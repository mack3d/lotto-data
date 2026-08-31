"""
Scraper wyników Keno z megalotto.pl
- 20 liczb z zakresu 1-70
- Losowania co 4 minuty od 06:34 do 23:54
- Jeden plik JSON per dzień: data/keno/YYYY-MM-DD.json
- Aktualizacja bieżącego dnia co 10 minut przez GitHub Actions
"""
import requests
import json
import re
import os
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo

BASE_URL = "https://megalotto.pl/wyniki/keno/losowania-z-dnia-{date}"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; LottoScraper/1.0)"}
DATA_DIR = os.path.join("data", "keno")
TZ_PL = ZoneInfo("Europe/Warsaw")


def to_utc(date_str, time_str):
    """DD.MM.YYYY + HH:MM → ISO 8601 UTC"""
    try:
        dd, mm, yyyy = date_str.split(".")
        hh, mi = time_str.split(":")
        local_dt = datetime(int(yyyy), int(mm), int(dd), int(hh), int(mi), tzinfo=TZ_PL)
        utc_dt = local_dt.astimezone(__import__("datetime").timezone.utc)
        return utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None


def parse_page(html):
    """Parsuje stronę dzienną Keno — zwraca listę losowań."""
    soup = BeautifulSoup(html, "html.parser")
    results = []
    all_li = soup.find_all("li")

    i = 0
    while i < len(all_li):
        text = all_li[i].get_text(strip=True)

        # Numer losowania: "1503775."
        m = re.match(r'^(\d+)\.$', text)
        if m:
            draw_no = int(m.group(1))

            if i + 1 < len(all_li):
                date_text = all_li[i+1].get_text(strip=True)
                # Data: "31.08.2026"
                date_m = re.match(r'^(\d{2})\.(\d{2})\.(\d{4})$', date_text)
                if date_m:
                    draw_date = f"{date_m.group(1)}.{date_m.group(2)}.{date_m.group(3)}"
                    draw_time = None
                    multiplier = None
                    nums = []
                    j = i + 2

                    while j < len(all_li):
                        li_text = all_li[j].get_text(strip=True)

                        # Mnożnik — koniec bloku
                        if li_text.startswith("Mnożnik:"):
                            mult_m = re.search(r'x(\d+)', li_text)
                            if mult_m:
                                multiplier = int(mult_m.group(1))
                            break

                        # Godzina zlepiona z liczbą: "09:0231" → time=09:02, num=31
                        time_num = re.match(r'^(\d{2}:\d{2})(\d{1,2})$', li_text)
                        if time_num:
                            draw_time = time_num.group(1)
                            n = int(time_num.group(2))
                            if 1 <= n <= 70:
                                nums.append(n)
                            j += 1
                            continue

                        # Godzina z linku (fallback)
                        link = all_li[j].find("a", href=True)
                        if link:
                            href = link.get("href", "")
                            t = re.search(r'wygrane-z-dnia-(\d{2}:\d{2})-', href)
                            if t and draw_time is None:
                                draw_time = t.group(1)
                            break

                        # Liczba: 1-70
                        if re.match(r'^\d{1,2}$', li_text):
                            n = int(li_text)
                            if 1 <= n <= 70:
                                nums.append(n)

                        if len(nums) == 20:
                            j += 1
                            break

                        j += 1

                    if len(nums) == 20:
                        draw_time = draw_time or "?"
                        utc_dt = to_utc(draw_date, draw_time) if draw_time != "?" else None
                        results.append({
                            "no": draw_no,
                            "date": draw_date,
                            "time": draw_time,
                            "utc": utc_dt,
                            "multiplier": multiplier,
                            "numbers": sorted(nums)
                        })
                    i = j
                    continue
        i += 1

    return results


def date_to_filename(date_str):
    """DD.MM.YYYY → YYYY-MM-DD (dla nazwy pliku)"""
    dd, mm, yyyy = date_str.split(".")
    return f"{yyyy}-{mm}-{dd}"


def load_day(file_date):
    """Wczytaj plik dnia (YYYY-MM-DD)."""
    path = os.path.join(DATA_DIR, f"{file_date}.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return []


def save_day(file_date, draws):
    """Zapisz plik dnia, posortowany malejąco po numerze."""
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, f"{file_date}.json")
    draws_sorted = sorted(draws, key=lambda x: x["no"], reverse=True)
    with open(path, "w") as f:
        json.dump(draws_sorted, f, ensure_ascii=False)
    return len(draws_sorted)


def scrape_day(page_date):
    """
    Pobierz wyniki dla danej daty.
    page_date: DD.MM.YYYY (format URL)
    """
    url = BASE_URL.format(date=page_date)
    print(f"Scrapuję {page_date}...", end=" ", flush=True)
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        draws = parse_page(r.text)
        print(f"{len(draws)} losowań")
        return draws
    except Exception as e:
        print(f"BŁĄD: {e}")
        return []


def update_day(page_date):
    """Aktualizuj jeden dzień — dociągnij nowe losowania."""
    file_date = date_to_filename(page_date)
    existing = load_day(file_date)
    existing_nos = {d["no"] for d in existing}

    fresh = scrape_day(page_date)
    if not fresh:
        return 0

    new_draws = [d for d in fresh if d["no"] not in existing_nos]
    if new_draws:
        all_draws = existing + new_draws
        count = save_day(file_date, all_draws)
        print(f"  +{len(new_draws)} nowych → łącznie {count} losowań w {file_date}.json")
        return len(new_draws)
    else:
        print(f"  Brak nowych losowań dla {page_date}")
        return 0


def save_index():
    """Zapisz index.json z listą dostępnych dni."""
    days = []
    if os.path.exists(DATA_DIR):
        for fname in sorted(os.listdir(DATA_DIR)):
            if fname.endswith(".json") and fname != "index.json":
                path = os.path.join(DATA_DIR, fname)
                with open(path) as f:
                    draws = json.load(f)
                if draws:
                    days.append({
                        "date": fname.replace(".json", ""),
                        "count": len(draws),
                        "first_no": draws[-1]["no"],
                        "last_no": draws[0]["no"],
                        "first_time": draws[-1].get("time"),
                        "last_time": draws[0].get("time"),
                    })

    days.sort(key=lambda x: x["date"], reverse=True)
    total = sum(d["count"] for d in days)

    index = {"days": days, "total": total, "total_days": len(days)}
    with open(os.path.join(DATA_DIR, "index.json"), "w") as f:
        json.dump(index, f, ensure_ascii=False)
    print(f"Index: {total} losowań, {len(days)} dni")


def run_today():
    """Aktualizacja bieżącego dnia (co 10 minut przez GitHub Actions)."""
    now_pl = datetime.now(TZ_PL)
    today = now_pl.strftime("%d.%m.%Y")
    print(f"Aktualizacja dnia: {today}")
    update_day(today)
    save_index()


def run_full(days_back=30):
    """
    Pełne pobieranie — ostatnie N dni.
    Keno nie ma archiwalnych stron rocznych — tylko per dzień.
    """
    now_pl = datetime.now(TZ_PL)
    print(f"Pełne pobieranie — ostatnie {days_back} dni")
    for i in range(days_back - 1, -1, -1):
        day = now_pl - timedelta(days=i)
        page_date = day.strftime("%d.%m.%Y")
        fresh = scrape_day(page_date)
        if fresh:
            file_date = date_to_filename(page_date)
            save_day(file_date, fresh)
        __import__("time").sleep(1)
    save_index()
    print("Gotowe.")


if __name__ == "__main__":
    import sys
    if "--full" in sys.argv:
        # Opcjonalnie: --full 90 (ostatnie 90 dni)
        days = 30
        for arg in sys.argv:
            if arg.isdigit():
                days = int(arg)
        run_full(days)
    else:
        run_today()
