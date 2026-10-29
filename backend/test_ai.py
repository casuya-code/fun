from app.ai_results import ai_fetch_score
r = ai_fetch_score('National Bank of Egypt', 'Al Masry')
print(r.finished if r else None, r.home_score if r else None, r.away_score if r else None, r.source if r else None)
r = ai_fetch_score('Vora', 'Vllaznia Shkodër')
print(r.finished if r else None, r.home_score if r else None, r.away_score if r else None, r.source if r else None)
r = ai_fetch_score('Kukësi', 'Kastrioti Krujë')
print(r.finished if r else None, r.home_score if r else None, r.away_score if r else None, r.source if r else None)
