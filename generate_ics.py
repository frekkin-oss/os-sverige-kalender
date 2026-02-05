import re
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser
from ics import Calendar, Event

SOK_URL = "https://sok.se/olympiska-spel/tavlingar/spelen/milano-cortina-2026/svenska-os-guiden.html"
TZ = ZoneInfo("Europe/Stockholm")

def fetch_html(url: str) -> str:
    r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    return r.text

def normalize_whitespace(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()

def find_candidate_lines(soup: BeautifulSoup) -> list[str]:
    """
    Vi tar ut synlig text och delar upp i rader, sedan plockar vi rader som ser ut som tider.
    Detta är medvetet robust, eftersom SOK kan ändra layout.
    """
    text = soup.get_text("\n")
    lines = [normalize_whitespace(x) for x in text.split("\n")]
    lines = [x for x in lines if x]
    return lines

TIME_RE = re.compile(r"\b(\d{1,2})[:.](\d{2})\b")
DATE_RE = re.compile(r"\b(\d{1,2})\s+(januari|februari|mars|april|maj|juni|juli|augusti|september|oktober|november|december)\b", re.IGNORECASE)

MONTHS = {
    "januari": 1, "februari": 2, "mars": 3, "april": 4, "maj": 5, "juni": 6,
    "juli": 7, "augusti": 8, "september": 9, "oktober": 10, "november": 11, "december": 12
}

def parse_date_from_line(line: str, default_year: int) -> datetime | None:
    m = DATE_RE.search(line)
    if not m:
        return None
    day = int(m.group(1))
    month_name = m.group(2).lower()
    month = MONTHS.get(month_name)
    if not month:
        return None
    return datetime(default_year, month, day, 0, 0, tzinfo=TZ)

def parse_time_from_line(line: str) -> tuple[int, int] | None:
    m = TIME_RE.search(line)
    if not m:
        return None
    hh = int(m.group(1))
    mm = int(m.group(2))
    if hh < 0 or hh > 23 or mm < 0 or mm > 59:
        return None
    return hh, mm

def build_events(lines: list[str]) -> list[Event]:
    """
    Heuristik:
    - Vi letar efter datumrader (t.ex. "5 februari") och sätter current_date.
    - Vi letar efter rader som innehåller tid och verkar beskriva en svensk start.
    - Vi försöker bygga titel + beskrivning från närliggande rader.
    """
    now = datetime.now(TZ)
    year_guess = now.year  # Milano Cortina 2026 ligger i 2026, men vi låter detta vara dynamiskt
    current_date = None

    events: list[Event] = []

    for i, line in enumerate(lines):
        dt = parse_date_from_line(line, year_guess)
        if dt:
            current_date = dt
            continue

        t = parse_time_from_line(line)
        if not t or not current_date:
            continue

        # Kandidat: rader nära tiden brukar innehålla sport och namn
        window = []
        for j in range(max(0, i - 2), min(len(lines), i + 4)):
            window.append(lines[j])
        blob = " | ".join(window)

        # Filter: ska ha något som tyder på Sverige eller svenskar.
        # SOK-guiden är redan "svensk", men detta minskar risken att vi plockar upp andra tider.
        sw_markers = ["Sverige", "svensk", "svenska", "SWE", "SE", "svenskar"]
        if not any(m.lower() in blob.lower() for m in sw_markers):
            # Om SOK-guiden i praktiken bara listar svenska starter kan du kommentera bort detta filter.
            continue

        hh, mm = t
        start = current_date.replace(hour=hh, minute=mm)
        # Om tiden är mitt i natten och datumet eventuellt rullar, kan SOK ibland lista "00:30" under föregående dag.
        # Vi gör en enkel korrigering om start hamnar "bakåt" mer än 12h jämfört med föregående tider.
        # (Behåller hellre fel dag än att flytta för aggressivt.)
        end = start + timedelta(minutes=60)

        # Titel: ta själva raden som innehåller tid, men gör den trevligare
        title = line
        # Om raden är väldigt kort, ta nästa rad som titel
        if len(title) < 10 and i + 1 < len(lines):
            title = f"{line} {lines[i+1]}"

        title = normalize_whitespace(title)
        description = normalize_whitespace(blob)

        e = Event()
        e.name = title
        e.begin = start
        e.end = end
        e.description = description
        e.uid = f"{hash((title, start.isoformat()))}@os-sverige-kalender"
        events.append(e)

    return events

def main() -> int:
    html = fetch_html(SOK_URL)
    soup = BeautifulSoup(html, "html.parser")

    lines = find_candidate_lines(soup)
    events = build_events(lines)

    cal = Calendar()
    for e in events:
        cal.events.add(e)

    with open("svenska-os-starter.ics", "w", encoding="utf-8") as f:
        f.writelines(cal.serialize_iter())

    print(f"Skapade {len(events)} events i svenska-os-starter.ics")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
