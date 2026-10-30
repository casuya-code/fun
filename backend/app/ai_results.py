import re
import json
import requests
from datetime import datetime, timedelta, date
from typing import Optional, Tuple
from bs4 import BeautifulSoup
from .config import settings


class AIResult:
    def __init__(self, finished=False, home_score=None, away_score=None, confidence=0.0, source=None,
                 postponed=False):
        self.finished = finished
        self.home_score = home_score
        self.away_score = away_score
        self.confidence = confidence
        self.source = source
        # True when the source says the match will not be played as scheduled
        # (postponed / cancelled / abandoned / suspended) - no score exists.
        self.postponed = postponed


def fetch_via_web_scrape(home_team: str, away_team: str, match_date=None) -> Optional[AIResult]:
    """Try multiple free sources without API keys."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    # Try Livescore
    try:
        # Try to find match on livescore
        search_url = f"https://www.livescore.com/en/football/search/?q={home_team.replace(' ', '%20')}%20{away_team.replace(' ', '%20')}"
        r = requests.get(search_url, headers=headers, timeout=15)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'lxml')
            text = soup.get_text(' ', strip=True)
            # Look for score patterns
            # Pattern like "Team1 X - Y Team2" or "X - Y"
            patterns = [
                rf'{re.escape(home_team)}.*?(\d+)\s*[-–]\s*(\d+).*?{re.escape(away_team)}',
                rf'{re.escape(away_team)}.*?(\d+)\s*[-–]\s*(\d+).*?{re.escape(home_team)}',
            ]
            for pattern in patterns:
                m = re.search(pattern, text, re.I | re.S)
                if m:
                    try:
                        if re.search(pattern, text, re.I | re.S).group(0).lower().find(home_team.lower()) < re.search(pattern, text, re.I | re.S).group(0).lower().find(away_team.lower()):
                            hg, ag = int(m.group(1)), int(m.group(2))
                        else:
                            ag, hg = int(m.group(1)), int(m.group(2))
                        if hg <= 15 and ag <= 15:
                            return AIResult(finished=True, home_score=hg, away_score=ag, confidence=0.85, source="livescore")
                    except:
                        pass
            # General score patterns near team names
            for m in re.finditer(r'(\d+)\s*[-–]\s*(\d+)', text):
                start = max(0, m.start()-100)
                end = min(len(text), m.end()+100)
                context = text[start:end].lower()
                if home_team.lower()[:4] in context and away_team.lower()[:4] in context:
                    hg, ag = int(m.group(1)), int(m.group(2))
                    if hg <= 15 and ag <= 15:
                        return AIResult(finished=True, home_score=hg, away_score=ag, confidence=0.8, source="livescore")
    except Exception as e:
        print(f"Livescore search error: {e}")
    
    # Try Flashscore
    try:
        search_url = f"https://www.flashscore.com/search/?q={home_team.replace(' ', '+')}+{away_team.replace(' ', '+')}"
        r = requests.get(search_url, headers=headers, timeout=15)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'lxml')
            text = soup.get_text(' ', strip=True)
            for m in re.finditer(r'(\d+)\s*[-–]\s*(\d+)', text):
                start = max(0, m.start()-150)
                end = min(len(text), m.end()+150)
                context = text[start:end].lower()
                if home_team.lower()[:4] in context and away_team.lower()[:4] in context:
                    # Check if it says finished/FT
                    if 'ft' in context or 'finished' in context or 'result' in context:
                        hg, ag = int(m.group(1)), int(m.group(2))
                        if hg <= 15 and ag <= 15:
                            return AIResult(finished=True, home_score=hg, away_score=ag, confidence=0.9, source="flashscore")
    except Exception as e:
        print(f"Flashscore search error: {e}")
    
    # Try ESPN
    try:
        search_url = f"https://www.espn.com/soccer/search/_/q/{home_team.replace(' ', '%20')}%20{away_team.replace(' ', '%20')}"
        r = requests.get(search_url, headers=headers, timeout=15)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'lxml')
            text = soup.get_text(' ', strip=True)
            for m in re.finditer(r'(\d+)\s*[-–]\s*(\d+)', text):
                start = max(0, m.start()-100)
                end = min(len(text), m.end()+100)
                context = text[start:end].lower()
                if home_team.lower()[:4] in context and away_team.lower()[:4] in context:
                    if 'final' in context or 'ft' in context:
                        hg, ag = int(m.group(1)), int(m.group(2))
                        if hg <= 15 and ag <= 15:
                            return AIResult(finished=True, home_score=hg, away_score=ag, confidence=0.85, source="espn")
    except Exception as e:
        print(f"ESPN search error: {e}")
    
    return None


# Simple in-memory cache for API-Football fixtures by date, with a TTL so a
# fixture cached before kickoff does not stay "not started" forever.
_FIXTURE_CACHE = {}
_FIXTURE_TTL = 600  # seconds

def _get_fixtures(host: str, key: str, ds: str) -> list:
    import time as _time
    hit = _FIXTURE_CACHE.get(ds)
    if hit and (_time.time() - hit[0]) < _FIXTURE_TTL:
        return hit[1]
    data = []
    try:
        r = requests.get(f"https://{host}/fixtures", headers={"x-apisports-key": key},
                         params={"date": ds}, timeout=15)
        if r.status_code == 200:
            data = r.json().get("response", []) or []
    except Exception as e:
        print(f"API-Football error ({ds}): {e}")
        data = []
    _FIXTURE_CACHE[ds] = (_time.time(), data)
    return data

import unicodedata
def _norm(s):
    s = unicodedata.normalize('NFKD', s or '')
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]', '', s.lower())

def _names_match(api_home, api_away, home_team, away_team):
    ah, aa = _norm(api_home), _norm(api_away)
    hh, aw = _norm(home_team), _norm(away_team)
    home_ok = (hh in ah) or (ah in hh) or (hh[:4] and hh[:4] in ah)
    away_ok = (aw in aa) or (aa in aw) or (aw[:4] and aw[:4] in aa)
    return home_ok and away_ok

def fetch_via_api_football(home_team: str, away_team: str, match_date=None) -> Optional[AIResult]:
    key = getattr(settings, "football_api_key", None)
    if not key:
        return None
    host = getattr(settings, "football_api_host", "v3.football.api-sports.io")
    # determine date range
    if isinstance(match_date, datetime):
        base = match_date.date()
    elif isinstance(match_date, date):
        base = match_date
    else:
        try:
            base = datetime.strptime(str(match_date)[:10], "%Y-%m-%d").date()
        except Exception:
            base = datetime.utcnow().date()
    dates = [base + timedelta(days=d) for d in (-1, 0, 1)]
    for d in dates:
        ds = d.isoformat()
        fixtures = _get_fixtures(host, key, ds)
        for fx in fixtures:
            try:
                api_home = fx["teams"]["home"]["name"]
                api_away = fx["teams"]["away"]["name"]
                if not _names_match(api_home, api_away, home_team, away_team):
                    continue
                status = (fx.get("fixture", {}).get("status", {}) or {}).get("short", "")
                goals = fx.get("goals", {}) or {}
                hg = goals.get("home")
                ag = goals.get("away")
                if status in ("FT", "AET", "PEN", "AWD", "WO") and hg is not None and ag is not None:
                    return AIResult(finished=True, home_score=int(hg), away_score=int(ag),
                                    confidence=0.99, source="api-football")
                if status in ("PST", "CANC", "ABD", "SUSP", "INT"):
                    # match will not be played / was interrupted - never guess a score
                    return AIResult(postponed=True, confidence=0.99, source="api-football",
                                    finished=False)
                # not finished yet
                return None
            except Exception as e:
                print(f"API-Football parse error: {e}")
    return None

def ai_fetch_score(home_team: str, away_team: str, match_date=None,
                   alt_home: str = None, alt_away: str = None) -> Optional[AIResult]:
    """Main settlement function - tries API-Football first, then web scraping.

    alt_home/alt_away: alternate names for the same fixture (e.g. a slug
    derived from the footystats URL like "dac 1904 dunajska streda" vs the DB
    short name "DAC") - used only when the primary names find no fixture.
    """
    def _try(h, a):
        try:
            r = fetch_via_api_football(h, a, match_date)
            if r and (r.finished or r.postponed) and r.confidence >= 0.9:
                return r
        except Exception as e:
            print(f"API-Football fetch error: {e}")
        return None

    # 1) API-Football (reliable)
    result = _try(home_team, away_team)
    if result:
        return result
    # 1b) API-Football with alternate names
    if alt_home and alt_away:
        result = _try(alt_home, alt_away)
        if result:
            return result
    # 2) web scraping fallback
    result = fetch_via_web_scrape(home_team, away_team, match_date)
    if result and result.finished and result.confidence >= 0.7:
        return result
    return None


def fetch_kickoff_api(home_team: str, away_team: str, match_date=None):
    key = getattr(settings, "football_api_key", None)
    if not key:
        return None
    host = getattr(settings, "football_api_host", "v3.football.api-sports.io")
    if isinstance(match_date, datetime):
        base = match_date.date()
    elif isinstance(match_date, date):
        base = match_date
    else:
        try:
            base = datetime.strptime(str(match_date)[:10], "%Y-%m-%d").date()
        except Exception:
            base = datetime.utcnow().date()
    for d in (base + timedelta(days=x) for x in (-1, 0, 1)):
        ds = d.isoformat()
        for fx in _get_fixtures(host, key, ds):
            try:
                if not _names_match(fx["teams"]["home"]["name"], fx["teams"]["away"]["name"], home_team, away_team):
                    continue
                dt_str = fx["fixture"].get("date")
                if dt_str:
                    return datetime.fromisoformat(dt_str.replace("Z", "+00:00")).replace(tzinfo=None)
            except Exception:
                continue
    return None
