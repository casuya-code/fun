"""Free result + kickoff lookup, and automatic settlement of ADM slips.

Everything here reads the same public source the app already uses, so no API
key is required. A match page exposes:

  <time class="timezone-convert-match-h2h-neo">  -> real kickoff date & time
  h2 "Final Results" + "H - A"                    -> only once the match is over

So: no "Final Results" heading means the match has not finished yet, and we
leave the leg pending instead of guessing.
"""
import re
import time as _time
from datetime import datetime, time, timedelta
from typing import Optional, Tuple

import requests
from bs4 import BeautifulSoup

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
BASE = "https://footystats.org"

# e.g. "Monday Oct 26, 2026 - 6:15pm (Europe/London time)"
_KICKOFF_RE = re.compile(
    r"([A-Za-z]{3,9})\s+(\d{1,2}),\s*(\d{4})\s*-\s*(\d{1,2}):(\d{2})\s*(am|pm)",
    re.I,
)
_MONTHS = {m.lower(): i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def _parse_kickoff(text: str) -> Optional[datetime]:
    """Parse the page's kickoff line into a UTC datetime (source is London time,
    treated here as UTC for scheduling comparison purposes only)."""
    if not text:
        return None
    m = _KICKOFF_RE.search(text)
    if not m:
        return None
    mon = _MONTHS.get(m.group(1)[:3].lower())
    if not mon:
        return None
    hh, mm = int(m.group(4)), int(m.group(5))
    if m.group(6).lower() == "pm" and hh != 12:
        hh += 12
    elif m.group(6).lower() == "am" and hh == 12:
        hh = 0
    try:
        return datetime(int(m.group(3)), mon, int(m.group(2)), hh, mm)
    except ValueError:
        return None


def fetch_match_page(url: str) -> Tuple[str, Optional[int], Optional[int], Optional[datetime]]:
    """Return (status, home_goals, away_goals, kickoff).

    status is 'finished' only when the page shows a final score.
    """
    full = url if url.startswith("http") else BASE + url
    resp = requests.get(full, headers=UA, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    kickoff = None
    t = soup.select_one("time.timezone-convert-match-h2h-neo")
    if t:
        kickoff = _parse_kickoff(t.get_text(" ", strip=True))

    # Try multiple patterns for finished matches
    # Pattern 1: "Final Results" heading (original)
    fin = next((x for x in soup.find_all("h2") if "Final Results" in x.get_text()), None)
    if fin:
        bits = []
        for el in fin.next_elements:
            if getattr(el, "name", None) == "h2" and el is not fin:
                break
            if isinstance(el, str):
                s = el.strip()
                if s and len(s) < 20:
                    bits.append(s)
            if len(bits) > 8:
                break
        nums = [int(v) for v in re.findall(r"\d+", " ".join(bits))]
        if len(nums) >= 2:
            return ("finished", nums[0], nums[1], kickoff)
        return ("finished_unknown", None, None, kickoff)

    # Pattern 2: Look for score boxes like "1 - 3" in certain contexts
    # Look for elements with score in class or containing dash with numbers
    for score_elem in soup.select('.score-box, [class*="scoreline"], .match-result, [class*="final-score"]'):
        text = score_elem.get_text(" ", strip=True)
        m = re.search(r'(\d+)\s*[-–]\s*(\d+)', text)
        if m:
            # Make sure it's not from H2H history - check if it's in current match context
            # Look for nearby "Full Time" or "FT"
            parent_text = score_elem.parent.get_text(" ", strip=True) if score_elem.parent else ""
            if 'Full-Time' in parent_text or 'Full Time' in parent_text or 'FT' in parent_text:
                return ("finished", int(m.group(1)), int(m.group(2)), kickoff)

    # Pattern 3: Look for "Full-Time" followed by score
    for ft in soup.find_all(string=re.compile(r'Full[- ]?Time', re.I)):
        # Look in siblings/parent for score
        parent = ft.parent
        for _ in range(5):  # look up a few levels
            if not parent:
                break
            text = parent.get_text(" ", strip=True)
            m = re.search(r'(\d+)\s*[-–]\s*(\d+)', text)
            if m and len(text) < 200:  # avoid long H2H sections
                # Avoid H2H history scores
                if 'vs' not in text or text.count('-') <= 2:
                    return ("finished", int(m.group(1)), int(m.group(2)), kickoff)
            parent = parent.parent

    # Pattern 6: Look for "meeting ended with the following result"
    for m in soup.find_all(string=re.compile(r'meeting ended', re.I)):
        parent = m.parent
        for _ in range(3):
            if not parent:
                break
            text = parent.get_text(" ", strip=True)
            # Look for score pattern like "Team A X - Y Team B"
            score_match = re.search(r'([A-Za-z\s]+)\s+(\d+)\s*[-–]\s*(\d+)\s+([A-Za-z\s]+)', text)
            if score_match:
                hg, ag = int(score_match.group(2)), int(score_match.group(3))
                return ("finished", hg, ag, kickoff)
            # or just two numbers
            nums = re.findall(r'(\d+)\s*[-–]\s*(\d+)', text)
            if nums:
                # take the first pair that makes sense (not percentages)
                for hg_s, ag_s in nums:
                    hg, ag = int(hg_s), int(ag_s)
                    if hg <= 10 and ag <= 10:  # reasonable score
                        return ("finished", hg, ag, kickoff)
            parent = parent.parent

    return ("scheduled", None, None, kickoff)


def refresh_kickoffs(db, matches, pause: float = 0.3):
    """Fill in real kickoff times for engine matches (enables the time ladder)."""
    from .models import EngineMatch
    updated = 0
    for m in matches:
        if m.kickoff_at:
            continue
        ko = None
        if m.match_url:
            try:
                _, _, _, ko = fetch_match_page(m.match_url)
            except Exception:
                ko = None
        if not ko:
            try:
                from .ai_results import fetch_kickoff_api
                ko = fetch_kickoff_api(m.home_team, m.away_team, m.match_date)
            except Exception:
                ko = None
        if ko:
            m.kickoff_at = ko
            updated += 1
            # propagate real kickoff to predictions of the SAME fixture/day only
            try:
                from .models import Prediction
                day_start = datetime.combine(m.match_date.date(), time.min)
                day_end = day_start + timedelta(days=1)
                db.query(Prediction).filter(
                    Prediction.home_team == m.home_team,
                    Prediction.away_team == m.away_team,
                    Prediction.match_date >= day_start,
                    Prediction.match_date < day_end,
                ).update({"match_date": ko}, synchronize_session=False)
            except Exception:
                pass
        _time.sleep(pause)
    db.commit()
    return updated
