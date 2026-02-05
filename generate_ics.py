import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from ics import Calendar, Event

SOK_URL = "https://sok.se/olympiska-spel/tavlingar/spelen/milano-cortina-2026/svenska-os-guiden.html"
TZ = ZoneInfo("Europe/Stockholm")

TIME_RE = re.compile(r"\b(\d{1,2})[:.](\d{2})\b")

# Klarar både "5 februari" och "5 feb"
DATE_RE = re.compile(
    r"\b(\d{1,2})\s+"
    r"(jan(?:uari)?|feb(?:ruari)?|mar(?:s)?|apr(?:il)?|maj|jun(?:i)?|jul(?:i)?|aug(?:usti)?|"
    r"sep(?:tember)?|okt(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b",
    re.IGNORECASE
)

MONTHS = {
    "jan": 1, "januari": 1,
    "feb": 2, "februari": 2,
    "mar": 3, "mars": 3,
    "apr": 4, "april": 4,
    "maj": 5,
    "jun": 6, "juni": 6,
    "jul": 7, "juli": 7,
    "aug": 8, "augusti": 8,
    "sep": 9, "september": 9,
    "okt": 10, "oktober": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


def fetch_html(url: str) -> str:
    r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    return r.text


def normalize_whitespace(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def extract_lines(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n")
    lines = [normalize_whitespace(x) for x in text.split("\n")]
    return [x for x in lines if x]


def parse_date_from_line(line: str, default_year: int) -> datetime | None:
    m = DATE_RE.search(line)
    if not m:
        return None
    day = int(m.group(1))
    month_name = m.group(2).lower()
    month_key = month_name[:3]  # "februari" -> "feb"
    month = MONTHS.get(month_key) or MONTHS.get(month_name)
    if not month:
        return None
    return datetime(default_year, month, day, 0, 0, tzinfo=TZ)


def parse_time_from_line(line: str) -> tuple[int, int] | None:
    m = TIME_RE.search(line)
    if not m:
        return None
    hh = int(m.group(1))
    mm = int(m.group(2))
    if 0 <= hh <= 23 and 0 <= mm <= 59:
        return hh, mm
    return None


def build_events(lines: list[str]) -> list[Event]:
    """
    Heuristik:
    - Hitta datumrader och håll aktuell dag i current_date.
    - För varje rad med tid: skapa event med titel och en beskrivning från ett närliggande textfönster.
    - Ingen extra "Sverige"-filterering (SOK-guiden är redan svensk).
    """
    now = datetime.now(TZ)
    year_guess = 2026 if now.year <= 2026 else now.year  # Milano-Cortina 2026

    current_date: datetime | None = None
    events: list[Event] = []

    for i, line in enumerate(lines):
        dt = parse_date_from_line(line, year_guess)
        if dt:
            current_date = dt
            continue

        t = parse_time_from_line(line)
        if not t or not current_date:
            continue

        hh, mm = t
        start = current_date.replace(hour=hh, minute=mm)

        # Bygg titel: om raden är kort (bara "10:30"), ta med nästa rad också.
        title = line
        if len(title) <= 6 and i + 1 < len(lines):
            title = f"{line} {lines[i+1]}"
        title = normalize_whitespace(title)

        # Beskrivning: ta lite kontext runt raden
        window = []
        for j in range(max(0, i - 2), min(len(lines), i + 4)):
            window.append(lines[j])
        description = normalize_whitespace(" | ".join(window))

        # Sätt en rimlig default-längd på eventet
        end = start + timedelta(minutes=60)

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
    lines = extract_lines(html)
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
