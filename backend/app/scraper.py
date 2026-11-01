import re
import os
import json
import requests
from datetime import datetime, timedelta, time
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from .models import User, EngineMatch
from .config import settings

URL = "https://footystats.org/stats/over15-goals"


def _proxies():
    pu = getattr(settings, "proxy_url", "") or os.getenv("PROXY_URL", "")
    if not pu:
        return None
    return {"http": pu, "https": pu}

# Optional cloudscraper (bypasses Cloudflare JS challenge)
try:
    import cloudscraper as _cloudscraper
    _HAS_CLOUDSCRAPER = True
except Exception:
    _cloudscraper = None
    _HAS_CLOUDSCRAPER = False

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.google.com/",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}
BARE_UA = BROWSER_HEADERS

# Cache file for FootyStats data (used when scraping is blocked)
CACHE_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "footystats_cache.json")

# Playwright stealth browser scraping (bypasses Cloudflare)
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

    Tries multiple techniques to bypass Cloudflare. Falls back to cached
    data if all fail. FootyStats is the trusted source.
    """
    print("fetch_matches: trying FootyStats (primary and only source)...")

    # --- Attempt 1: FootyStats with cloudscraper + browser headers ---
    headers = dict(BROWSER_HEADERS)
    resp = None
    for verify in [True, False]:
        try:
            # Try cloudscraper first (without custom headers - works better)
            if _HAS_CLOUDSCRAPER:
                try:
                    scraper = _cloudscraper.create_scraper()
                    proxies = _proxies()
                    if proxies:
                        scraper.proxies.update(proxies)
                    # Try without headers first (cloudscraper sets its own)
                    resp = scraper.get(URL, timeout=30)
                    if resp.status_code == 200 and "Just a moment" not in resp.text:
                        break
                    # Try with headers
                    resp = scraper.get(URL, headers=headers, timeout=30)
                    if resp.status_code == 200 and "Just a moment" not in resp.text:
                        break
                    resp = None
                except Exception as e:
                    print(f"cloudscraper error: {e}")
                    resp = None
            # Plain requests fallback
            if resp is None:
                proxies = _proxies()
                kwargs = {"url": URL, "headers": headers, "timeout": 30, "verify": verify}
                if proxies:
                    kwargs["proxies"] = proxies
                try:
                    resp = requests.get(**kwargs)
                    if resp.status_code == 200 and "Just a moment" not in resp.text:
                        break
                    resp = None
                except Exception as e:
                    print(f"requests error (verify={verify}): {e}")
                    resp = None
        except Exception as e:
            print(f"fetch_matches error (verify={verify}): {e}")
            resp = None

    if resp is not None and resp.status_code == 200:
        soup = BeautifulSoup(resp.text, "lxml")
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
        if tables:
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
        if results:
            print(f"fetch_matches: {len(results)} matches from FootyStats (primary source)")
            _save_cache(results)
            return results
        else:
            print("fetch_matches: FootyStats returned 0 matches (Cloudflare block or page change)")

    # --- Attempt 2: FootyStats API (if key configured) ---
    api_results = fetch_matches_footstats_api()
    if api_results:
        print(f"fetch_matches: {len(api_results)} matches from FootyStats API")
        _save_cache(api_results)
        return api_results

    # --- Attempt 4: Use cached data from previous successful scrape ---
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
    n = ingest_engine(db, matches)
    print(f"Ingested {n} new engine matches, {len(matches)} total from FootyStats")
    return n
