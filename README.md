# Hardwood Basketball Simulator

A basketball front-office simulator for Windows. You take over a franchise in a 30-team league that starts in
2002 and run it season after season: roster, contracts, the salary cap, trades, the draft, coaching and the
owner's patience. Every other team is run by a CPU general manager with its own plan, wishes and trade logic.

**Early Access, v0.1.2.** The league, teams and players are fictional. Leagues are plain data files, so other
leagues can be added as mods (see [mods/README.md](mods/README.md)).

Not affiliated with, endorsed by or connected to any real basketball league, team or player.

## Highlights

- **29 CPU general managers with a mind of their own.** Each has a philosophy (pick hoarder, star chaser, cap
  guardian, patient builder...), skills, a multi-season plan and an owner who judges the results. Two teams with the same
  goal go about it differently, and you can read why.
- **Trades that make sense.** Every CPU trade starts from something a GM wants: a starter, a star, picks, getting
  under the tax, renting a veteran for a title run. Star upgrades, auctions, tax dumps, deadline rentals,
  three- and four-team deals, draft-night moves. Every trade is explained and graded.
- **Players who decide too.** Loyalty is earned, stars walk away from hopeless teams, frustrated stars ask to be
  traded, and free agents get real bidding wars that run night after night.
- **A league that moves.** Owners fire coaches and GMs, GMs are hired from a market and grow over their careers,
  plans change after failures, rebuilders become champions.
- **The era changes the game.** A 2002 league plays slow and inside; over the years it moves toward pace, space and
  threes, with the cap, contracts and every AI threshold following the years.
- **Possession-by-possession engine** with 14 coaching styles, points of emphasis, lineups, minutes and an opponent
  scouting tab. Simulate day by day with a Stop button, or straight to the deadline or the playoffs.
- **The whole offseason**: options, development and retirements, staff carousel, lottery, draft room, 12-day free
  agency, cut-down day.
- **Numbers for decades**: player database with full careers, league analytics, finances and CBA, awards, records,
  Hall of Fame, trophy rooms, All-Star Weekend, news.

**Everything in the game, system by system: [FEATURES.md](FEATURES.md).**
**What is coming next: [ROADMAP.md](ROADMAP.md).**

## Install and play

1. Download the latest `Hardwood-vX.Y.Z.zip` from the [Releases](../../releases) page.
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
