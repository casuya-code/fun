import re
import requests
from datetime import datetime, date, timedelta, time
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from .models import User, Prediction, EngineMatch
from .config import settings

URL = "https://footystats.org/stats/over15-goals"

# NOTE: footystats/Cloudflare rejects full Chrome headers (TLS/header mismatch
# triggers the "Just a moment" challenge). This bare UA is the one that works.
BARE_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def fetch_matches_footstats_ai():
    """AI scrape fallback for FootStats only (no external API data)."""
    headers_list = [
        BARE_UA,
        {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"},
    ]
    for headers in headers_list:
        try:
            resp = requests.get(URL, headers=headers, timeout=20, verify=False)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "lxml")
            # reuse parsing by calling a helper
            return _parse_footstats(soup)
        except Exception as e:
            print("footstats ai error:", e)
    return []

def _parse_footstats(soup):
    headings = []
    for h in soup.find_all(["h2", "h3"]):
        txt = h.get_text()
        if "Over" in txt and "Goals" in txt:
            headings.append(h)
    tables = []
    for h in headings:
        for sib in h.find_all_next():
            if sib.name == "table":
                tables.append(sib)
                break
    if not tables:
        for t in soup.find_all("table"):
            if "Over" in t.get_text():
                tables.append(t)
    results = []
    seen = set()
    all_rows = []
    for table in tables:
        all_rows.extend(table.find_all("tr"))
    for row in all_rows:
        cells = row.find_all("td")
        if len(cells) < 6:
            continue
        match_text = cells[1].get_text(" ", strip=True)
        over_text = cells[2].get_text(strip=True)
        avg_text = cells[3].get_text(strip=True)
        date_text = cells[4].get_text(strip=True)
        odds_text = cells[5].get_text(strip=True)
        try:
            over15 = float(re.sub(r"[^0-9.]", "", over_text))
        except ValueError:
            over15 = None
        try:
            avg_goals = float(re.sub(r"[^0-9.]", "", avg_text))
        except ValueError:
            avg_goals = None
        m = re.split(r"\s+vs\s+", match_text, flags=re.I)
        if len(m) != 2:
            continue
        home, away = m[0].strip(), m[1].strip()
        try:
            odds = float(odds_text)
        except ValueError:
            continue
        low = date_text.lower()
        if "today" in low:
            d = datetime.utcnow().date()
        elif "tomorrow" in low:
            d = datetime.utcnow().date() + timedelta(days=1)
        else:
            try:
                d = datetime.strptime(date_text, "%d %b").date().replace(year=datetime.utcnow().year)
            except Exception:
                d = datetime.utcnow().date()
        key = (home.lower(), away.lower(), str(d))
        if key in seen:
            continue
        seen.add(key)
        link = None
        for a in cells[1].find_all("a", href=True):
            if "h2h-stats" in a["href"]:
                link = a["href"]
                break
        results.append({"home": home, "away": away, "odds": odds, "date": d,
                        "over15": over15, "avg_goals": avg_goals, "link": link})
    return results

def fetch_matches_api():
    """Fallback: today's fixtures from API-Football when footystats is blocked."""
    try:
        from .config import settings
        import requests as _r
        key = getattr(settings, "football_api_key", None)
        if not key:
            return []
        host = getattr(settings, "football_api_host", "v3.football.api-sports.io")
        from datetime import date, datetime, timedelta
        today = date.today()
        r = _r.get(f"https://{host}/fixtures", headers={"x-apisports-key": key}, params={"date": today.isoformat()}, timeout=20)
        if r.status_code != 200:
            return []
        data = r.json().get("response", []) or []
        results = []
        for fx in data:
            try:
                home = fx["teams"]["home"]["name"]
                away = fx["teams"]["away"]["name"]
                ko = fx["fixture"].get("date")
                d = datetime.strptime(ko[:10], "%Y-%m-%d").date() if ko else today
                results.append({
                    "home": home, "away": away, "odds": 1.8, "date": d,
                    "over15": 78.0, "avg_goals": None, "link": None,
                })
            except Exception:
                continue
        return results
    except Exception as e:
        print("fetch_matches_api error:", e)
        return []

def fetch_matches():
    headers = dict(BARE_UA)
    resp = None
    for verify in [True, False]:
        try:
            resp = requests.get(URL, timeout=30, headers=headers, verify=verify)
            resp.raise_for_status()
            break
        except Exception as e:
            print(f"fetch_matches error (verify={verify}):", e)
            resp = None
    if resp is None:
        # FootStats only: try AI scrape of the same page
        return fetch_matches_footstats_ai()
    soup = BeautifulSoup(resp.text, "lxml")
    # Find ALL over-X sections (1.5, 2.5, 3.5, 4.5) and combine
    headings = []
    for h in soup.find_all(["h2", "h3"]):
        txt = h.get_text()
        if "Over" in txt and "Goals" in txt:
            headings.append(h)
    # collect tables from each heading
    tables = []
    for h in headings:
        for sib in h.find_all_next():
            if sib.name == "table":
                tables.append(sib)
                break
    if not tables:
        # fallback: any table containing "Over"
        for t in soup.find_all("table"):
            if "Over" in t.get_text():
                tables.append(t)
    results = []
    seen = set()
    if not tables:
        return fetch_matches_footstats_ai()
    all_rows = []
    for table in tables:
        all_rows.extend(table.find_all("tr"))
    for row in all_rows:
        cells = row.find_all("td")
        if len(cells) < 6:
            continue
        # match cell usually second
        match_text = cells[1].get_text(" ", strip=True)
        over_text = cells[2].get_text(strip=True)
        avg_text = cells[3].get_text(strip=True)
        date_text = cells[4].get_text(strip=True)
        odds_text = cells[5].get_text(strip=True)
        # parse percentages / averages
        try:
            over15 = float(re.sub(r"[^0-9.]", "", over_text))
        except ValueError:
            over15 = None
        try:
            avg_goals = float(re.sub(r"[^0-9.]", "", avg_text))
        except ValueError:
            avg_goals = None
        # parse "TeamA vs TeamB"
        m = re.split(r"\s+vs\s+", match_text, flags=re.I)
        if len(m) != 2:
            continue
        home, away = m[0].strip(), m[1].strip()
        try:
            odds = float(odds_text)
        except ValueError:
            continue
        # date
        low = date_text.lower()
        if "today" in low:
            d = datetime.utcnow().date()
        elif "tomorrow" in low:
            d = datetime.utcnow().date() + timedelta(days=1)
        else:
            # try parse date
            try:
                d = datetime.strptime(date_text, "%d %b").date().replace(year=datetime.utcnow().year)
            except Exception:
                d = datetime.utcnow().date()
        key = (home.lower(), away.lower(), str(d))
        if key in seen:
            continue
        seen.add(key)
        # per-match page (carries the final result once played)
        link = None
        for a in cells[1].find_all("a", href=True):
            if "h2h-stats" in a["href"]:
                link = a["href"]
                break
        results.append({"home": home, "away": away, "odds": odds, "date": d,
                        "over15": over15, "avg_goals": avg_goals, "link": link})
    if not results:
        return fetch_matches_footstats_ai()
    return results

def ingest_engine(db: Session, matches=None):
    """Store/refresh matches in the private admin engine table."""
    if matches is None:
        matches = fetch_matches()
    stored = 0
    for m in matches:
        match_dt = datetime.combine(m["date"], time(12, 0))
        row = db.query(EngineMatch).filter(
            EngineMatch.home_team == m["home"],
            EngineMatch.away_team == m["away"],
            EngineMatch.match_date == match_dt,
        ).first()
        if row:
            # refresh stats on re-scan (odds and % move daily)
            row.odds = m["odds"]
            row.over15_pct = m["over15"]
            row.avg_goals = m["avg_goals"]
            if m.get("link"):
                row.match_url = m["link"]
        else:
            db.add(EngineMatch(
                home_team=m["home"], away_team=m["away"], match_date=match_dt,
                odds=m["odds"], over15_pct=m["over15"], avg_goals=m["avg_goals"],
                match_url=m.get("link"), filter_type="over15",
            ))
            stored += 1
    db.commit()
    return stored

def ingest(db: Session):
    admin = db.query(User).filter(User.role == "admin").first()
    if not admin:
        return 0
    matches = fetch_matches()
    ingest_engine(db, matches)
    count = 0
    for m in matches:
        match_dt = datetime.combine(m["date"], time(12, 0))
        # match by home/away and same day (kickoff may already be filled)
        exists = db.query(Prediction).filter(
            Prediction.home_team == m["home"],
            Prediction.away_team == m["away"],
            Prediction.match_date >= datetime.combine(m["date"], time(0,0)),
            Prediction.match_date < datetime.combine(m["date"] + timedelta(days=1), time(0,0)),
        ).first()
        if exists:
            continue
        p = Prediction(
            home_team=m["home"],
            away_team=m["away"],
            match_date=match_dt,
            odds=m["odds"],
            status="scheduled",
            allowed=True,
            allowed_at=datetime.utcnow(),
            created_by=admin.id,
        )
        db.add(p)
        count += 1
    db.commit()
    return count