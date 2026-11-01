import re
import os
import json
import time
import warnings
from datetime import datetime, date, timedelta, time
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from .models import User, Prediction, EngineMatch
from .config import settings

URL = "https://footystats.org/stats/over15-goals"

# Cache file for FootyStats data (used when scraping is blocked)
CACHE_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "footystats_cache.json")

# Playwright stealth browser scraping (bypasses Cloudflare)
def _fetch_footystats_playwright():
    """Use Playwright with stealth to bypass Cloudflare and fetch FootyStats page."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright not installed, skipping")
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                ]
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={"width": 1440, "height": 900},
                device_scale_factor=1,
                is_mobile=False,
                has_touch=False,
                locale="en-US",
            )
            page = context.new_page()
            page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
            """)

            try:
                page.goto(URL, wait_until="domcontentloaded", timeout=60000)
                # Wait for Cloudflare challenge to pass
                page.wait_for_timeout(8000)
                html_content = page.content()
                browser.close()

                if "Just a moment" in html_content:
                    print("Playwright: Cloudflare challenge not passed")
                    return None
                if len(html_content) < 5000:
                    print("Playwright: page too short, likely blocked")
                    return None
                print(f"Playwright: fetched {len(html_content)} bytes successfully")
                return html_content
            except Exception as e:
                browser.close()
                print(f"Playwright fetch error: {e}")
                return None
    except Exception as e:
        print(f"Playwright launch error: {e}")
        return None


def _parse_footstats_html(html):
    """Parse FootyStats HTML and extract matches."""
    soup = BeautifulSoup(html, "lxml")
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


def _save_cache(matches):
    """Save FootyStats matches to cache file for fallback use."""
    try:
        cache_path = os.path.abspath(CACHE_FILE)
        data = []
        for m in matches:
            data.append({
                "home": m["home"],
                "away": m["away"],
                "odds": m["odds"],
                "date": str(m["date"]),
                "over15": m["over15"],
                "avg_goals": m["avg_goals"],
                "link": m.get("link"),
            })
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump({"saved_at": datetime.utcnow().isoformat(), "matches": data}, f, ensure_ascii=False)
        print(f"FootyStats cache saved: {len(data)} matches")
    except Exception as e:
        print(f"cache save error: {e}")


def _load_cache():
    """Load cached FootyStats matches if available and recent (within 3 days)."""
    try:
        cache_path = os.path.abspath(CACHE_FILE)
        if not os.path.exists(cache_path):
            return []
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        saved_at = datetime.fromisoformat(data["saved_at"])
        if (datetime.utcnow() - saved_at).days > 3:
            print("FootyStats cache too old (>3 days), ignoring")
            return []
        matches = []
        for m in data.get("matches", []):
            try:
                d = datetime.strptime(m["date"], "%Y-%m-%d").date()
                matches.append({
                    "home": m["home"],
                    "away": m["away"],
                    "odds": m["odds"],
                    "date": d,
                    "over15": m["over15"],
                    "avg_goals": m["avg_goals"],
                    "link": m.get("link"),
                })
            except Exception:
                continue
        print(f"FootyStats cache loaded: {len(matches)} matches (saved {saved_at})")
        return matches
    except Exception as e:
        print(f"cache load error: {e}")
        return []


def fetch_matches_footstats_api():
    """Fallback: FootyStats API when scraping is blocked. Requires FOOTYSTATS_API_KEY."""
    key = getattr(settings, "footystats_api_key", "") or os.getenv("FOOTYSTATS_API_KEY", "")
    if not key:
        return []
    try:
        import requests
        r = requests.get("https://api.football-data-api.com/todays-matches",
                         params={"key": key}, timeout=20)
        if r.status_code != 200:
            print(f"fetch_matches_footstats_api: HTTP {r.status_code}")
            return []
        data = r.json()
        if not data.get("success"):
            print(f"fetch_matches_footstats_api: {data.get('message', 'failed')}")
            return []
        matches = []
        for m in (data.get("data") or []):
            try:
                home = m.get("home_name") or m.get("homeName") or ""
                away = m.get("away_name") or m.get("awayName") or ""
                if not home or not away:
                    continue
                du = m.get("date_unix") or m.get("dateUnix")
                if du:
                    d = datetime.utcfromtimestamp(int(du)).date()
                else:
                    d = datetime.utcnow().date()
                odds = float(m.get("odds_ft_over15") or m.get("oddsFtOver15") or 1.8)
                o15 = m.get("o15_potential") or m.get("over15_potential")
                try:
                    o15 = float(o15) if o15 is not None else 78.0
                except (ValueError, TypeError):
                    o15 = 78.0
                if o15 == 0:
                    o15 = 78.0
                avg = float(m.get("avg_potential") or m.get("avgPotential") or 2.5)
                if avg == 0:
                    avg = 2.5
                link = m.get("match_url") or m.get("matchUrl")
                matches.append({"home": home, "away": away, "odds": odds, "date": d,
                                "over15": o15, "avg_goals": avg, "link": link})
            except Exception as e:
                print(f"fetch_matches_footstats_api parse error: {e}")
                continue
        print(f"fetch_matches_footstats_api: {len(matches)} matches from FootyStats API")
        return matches
    except Exception as e:
        print(f"fetch_matches_footstats_api error: {e}")
        return []


def fetch_matches():
    """Fetch matches from FootyStats (PRIMARY and ONLY source).

    Uses Playwright stealth browser to bypass Cloudflare. Falls back to
    cached data if scraping fails. FootyStats is the trusted source.
    """
    print("fetch_matches: trying FootyStats with Playwright stealth...")

    # --- Attempt 1: Playwright stealth browser ---
    html = _fetch_footystats_playwright()
    if html:
        results = _parse_footstats_html(html)
        if results:
            print(f"fetch_matches: {len(results)} matches from FootyStats (Playwright)")
            _save_cache(results)
            return results
        else:
            print("fetch_matches: Playwright got page but no matches parsed")

    # --- Attempt 2: FootyStats API (if key configured) ---
    api_results = fetch_matches_footstats_api()
    if api_results:
        print(f"fetch_matches: {len(api_results)} matches from FootyStats API")
        _save_cache(api_results)
        return api_results

    # --- Attempt 3: Use cached data from previous successful scrape ---
    print("fetch_matches: all live sources failed, trying cached data...")
    cached = _load_cache()
    if cached:
        print(f"fetch_matches: {len(cached)} matches from cache")
        return cached

    print("fetch_matches: ALL sources failed, no cached data available")
    return []


def ingest_engine(db: Session, matches=None):
    """Store/refresh matches in the private admin engine table."""
    if matches is None:
        matches = fetch_matches()

    # Clean up duplicate EngineMatch rows (same home, away, day)
    from sqlalchemy import func
    dupes = db.query(
        EngineMatch.home_team, EngineMatch.away_team,
        func.date(EngineMatch.match_date).label("d")
    ).group_by(
        EngineMatch.home_team, EngineMatch.away_team, func.date(EngineMatch.match_date)
    ).having(func.count() > 1).all()
    for home, away, d in dupes:
        rows = db.query(EngineMatch).filter(
            EngineMatch.home_team == home,
            EngineMatch.away_team == away,
            EngineMatch.match_date >= datetime.combine(d, time(0, 0)),
            EngineMatch.match_date < datetime.combine(d, time(0, 0)) + timedelta(days=1),
        ).order_by(EngineMatch.kickoff_at.desc().nullslast(), EngineMatch.id).all()
        for row in rows[1:]:
            from ..models import EngineSlipLeg
            db.query(EngineSlipLeg).filter(EngineSlipLeg.match_id == row.id).delete()
            db.delete(row)
    db.commit()

    stored = 0
    for m in matches:
        match_date = m["date"]
        day_start = datetime.combine(match_date, time(0, 0))
        day_end = day_start + timedelta(days=1)
        row = db.query(EngineMatch).filter(
            EngineMatch.home_team == m["home"],
            EngineMatch.away_team == m["away"],
            EngineMatch.match_date >= day_start,
            EngineMatch.match_date < day_end,
        ).first()
        if row:
            row.odds = m["odds"]
            row.over15_pct = m["over15"]
            row.avg_goals = m["avg_goals"]
            if m.get("link"):
                row.match_url = m["link"]
        else:
            match_dt = datetime.combine(match_date, time(12, 0))
            db.add(EngineMatch(
                home_team=m["home"], away_team=m["away"], match_date=match_dt,
                odds=m["odds"], over15_pct=m["over15"], avg_goals=m["avg_goals"],
                match_url=m.get("link"), filter_type="over15",
            ))
            stored += 1
    db.commit()
    return stored


def _fetch_kickoff_for_match(home, away, match_date):
    """Try to get real kickoff time from API-Football."""
    try:
        from .ai_results import fetch_kickoff_api
        ko = fetch_kickoff_api(home, away, match_date)
        if ko:
            return ko
    except Exception as e:
        print("kickoff fetch error for", str(home).encode("ascii", "replace").decode(), "vs", str(away).encode("ascii", "replace").decode(), ":", e)
    return None


def ingest(db: Session):
    admin = db.query(User).filter(User.role == "admin").first()
    if not admin:
        return 0
    matches = fetch_matches()
    ingest_engine(db, matches)
    count = 0
    for m in matches:
        match_date = m["date"]
        ko = _fetch_kickoff_for_match(m["home"], m["away"], match_date)
        if ko:
            match_dt = ko
        else:
            match_dt = datetime.combine(match_date, time(12, 0))
        exists = db.query(Prediction).filter(
            Prediction.home_team == m["home"],
            Prediction.away_team == m["away"],
            Prediction.match_date >= datetime.combine(match_date, time(0, 0)),
            Prediction.match_date < datetime.combine(match_date + timedelta(days=1), time(0, 0)),
        ).first()
        if exists:
            if ko and exists.match_date != ko:
                exists.match_date = ko
                db.commit()
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

    # Update EngineMatch kickoff_at and match_date
    for m in matches:
        match_date = m["date"]
        ko = _fetch_kickoff_for_match(m["home"], m["away"], match_date)
        if ko:
            day_start = datetime.combine(match_date, time(0, 0))
            day_end = day_start + timedelta(days=1)
            row = db.query(EngineMatch).filter(
                EngineMatch.home_team == m["home"],
                EngineMatch.away_team == m["away"],
                EngineMatch.match_date >= day_start,
                EngineMatch.match_date < day_end,
            ).first()
            if row:
                row.kickoff_at = ko
                row.match_date = ko
                db.commit()

    return count