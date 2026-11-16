# League mods

A mod is a folder with a `league.json` (and optionally draft classes). Put it in `Documents\Hardwood\mods\`
(or `mods/` in the repo when running from source), open **Mods** in the main menu, pick it and press
**Build & use**, then start a new career. Careers already started keep their own league.

```
Documents\Hardwood\mods\
  My League\
    league.json
    draft_classes\          (optional)
      DRAFT_2003.json
      DRAFT_2004.json
```

## Start from the built-in league

Copy the built-in league file and edit it: `data/leagues/fictional_2002/league.json` in the repo, or
`_internal\data\leagues\fictional_2002\league.json` next to `Hardwood.exe`.

## league.json

```
{"schema_version": 1,
 "meta": {"name": "My League", "era": "2002", "start_year": 2002},
 "franchises": [ ...30 teams... ],
 "players": {"BOS": [ ...players... ], ...},
 "free_agents": [ ...players... ],
 "rivalries": [["BOS", "LAL", 50.0], ...],
 "marquee_hosts": {"mlk_day": ["ATL", "MEM"]},
 "staff": {"coach_names": [...], "owner_names": [...], "gms": {"starting": [...], "arrivals": [...]}}}
```

- **franchises**: exactly 30, 15 per conference (`East`/`West`). Each has a short `id` (e.g. `BOS`, the key
  used everywhere else), `name`, `city`, `nickname`, `abbreviation`, `conference`, `division`, `arena`, colours and
  market data: copy the fields of the built-in league.
- **players**: by franchise id. Each player has an `id` you choose once (e.g. `p0001`, never reused), `name`,
  `role` (PG/SG/SF/PF/C), `age`, `overall`, `potential` and the `abilities` and `tendencies` blocks with the
  same keys as the built-in league. Ratings 1-99, abilities and tendencies 0-100, ages 15-50, at least 10
  players per team.
- **staff.gms**: the CPU general managers. Without them the game generates GMs.

The Mods screen lists every problem in a file (missing field, wrong team count, out-of-range rating) instead
of starting a broken league.

## Draft classes

`draft_classes/DRAFT_<year>.json` is a list of prospects for that year's draft. Each prospect has `name`,
`role`, `age`, `overall`, `potential`, `provenance`, `pedigree`, `abilities` and `tendencies`. Years without a
file get generated rookies. A new career copies the mod's draft classes into its save.
