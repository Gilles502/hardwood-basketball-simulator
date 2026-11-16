# Contributing

Bug reports are the most useful help right now: use the issue template and attach the logs it asks for.

## Running things

```
pip install -r requirements.txt
python server.py                                   # backend on http://127.0.0.1:5000
cd frontend && npm ci && npm run dev               # frontend dev server

python -m unittest discover -s tests               # unit tests (standard library only)
python scripts/check_real_names.py                 # release check, needs a real-names mod in mods/
python scripts/health_check.py --seasons 5 --era 2002 --seed 42 --label mytest
python scripts/build_exe.py                        # Windows package: dist/Hardwood/Hardwood.exe
```

The health check simulates N seasons headlessly in a sandbox copy and writes a report with league metrics.
Runs are not bit-for-bit reproducible even with the same seed: judge a change by "no crash, no errors in the
log, metrics inside the usual spread".

In development the game writes its data inside the repo folder (`saves/`, `data/nba_sim.db`, `logs/`,
`mods/`); all of it is git-ignored.

## Code rules

- Code, comments, UI text and commit messages are in English. Some Italian words remain as data keys in saves
  and the database (owner personalities, save keys): they change only through a versioned save migration.
- Player roles are PG/SG/SF/PF/C everywhere (`core/roles.py`, `frontend/src/utils/roles.ts`).
- Every tunable number lives in a `core/config.py` dataclass section (`CONFIG.TRADES`, `CONFIG.ECONOMY`, ...).
- CPU trades are born from a GM wish (`core/front_office/wishes.py`); no per-window or per-team caps.
- No real league, team or player names in the repo. Real-name data belongs in a local mod.
- Keep each file's line endings (the repo mixes CRLF and LF).
- All tests pass before a commit.
