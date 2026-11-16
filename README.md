# Hardwood Basketball Simulator

A basketball front-office simulator for Windows. You take over a franchise in a 30-team league that starts in
2002 and run it season after season: roster, contracts, the salary cap, trades, the draft, coaching and the
owner's patience. Every other team is run by a CPU general manager with its own plan, wishes and trade logic.

**Early Access, v0.1.0.** The league, teams and players are fictional. Leagues are plain data files, so other
leagues can be added as mods (see [mods/README.md](mods/README.md)).

Not affiliated with, endorsed by or connected to any real basketball league, team or player.

## What is in v0.1

- **CPU general managers.** Each CPU team has a GM with skills, traits and a franchise plan (contend, retool,
  rebuild). Their trades come from what they want, and every trade says why it happened.
- **Contracts and free agency.** Extensions, player and team options, players who walk away from losing teams,
  same-night free-agency auctions between teams.
- **Draft.** Lottery, scouting, a draft board, CPU picks by fit and GM skill, trades on draft night.
- **Owners and the carousel.** Owners judge their coaches and GMs; coaches and GMs get fired and hired.
- **Simulation.** Possession by possession, day by day with a Stop button, or straight to a target (trade
  deadline, All-Star break, end of the regular season). Playoffs with a play-in.
- **Numbers.** Player database with full careers, League Analytics (advanced, rebounding, clutch and shot-zone
  stats, team four factors), awards, records, Hall of Fame, news.

## Install and play

1. Download `Hardwood-v0.1.0.zip` from the [Releases](../../releases) page.
2. Unzip it anywhere and run `Hardwood.exe`. No installer and no admin rights needed.
3. Start a new career from the main menu.

Saves, logs and mods live in `Documents\Hardwood\`. Settings > Saves folder > Open shows the folder.

Needs Windows 10 or 11 with the Microsoft Edge WebView2 runtime (Windows 11 has it; on Windows 10, install the
Evergreen WebView2 Runtime from Microsoft if the window stays blank).

## Known issues

- Only the 2002 starting era is available.
- A season that started before an update that adds new stats shows those stats empty until the next season.
- Short pauses can happen on busy simulation days.

## Report a bug

Open an issue with the **Bug report** template. Attach `Documents\Hardwood\logs\server.log` (and `crash.log` if
there is one) and say what you clicked just before the problem.

## Run from source

Python 3.13 and Node.js 22 or newer.

```
pip install -r requirements.txt
cd frontend && npm ci && npm run build && cd ..
python launcher.py                          # the game in its own window (needs pywebview)
```

For development, `python server.py` starts the backend on port 5000 and `cd frontend && npm run dev` the Vite
dev server. Tests: `python -m unittest discover -s tests` (standard library only). Build the Windows package
with `python scripts/build_exe.py` (needs `pip install -r requirements-build.txt`). See
[CONTRIBUTING.md](CONTRIBUTING.md).

## License

GPL-3.0. You can use, study, change and share the game; if you share a changed version, you share its source
under the same license. See [LICENSE](LICENSE).
