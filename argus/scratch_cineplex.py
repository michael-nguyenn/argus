# scratch, repo root: python -m scratch_cineplex
from argus.adapters.cineplex import CineplexAdapter
p = {"id": "test", "film_id": 37617, "location_id": 7408,
     "after_date": "2026-08-12", "experience": ["IMAX", "70mm"]}
r = CineplexAdapter().check(p)
print(r.status, r.latency_ms, r.error)