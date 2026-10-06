# answer.json — the input to build.py

You write prose and ids; `scripts/build.py` resolves them into the full answer data
and `scripts/render.py` turns that data into static HTML. The resolved data (with
`"schemaVersion": 1`) is embedded in the page as `<script id="answer-data">` and can be
written to its own file with `build.py --json`, so another renderer can reuse it.
Text fields may contain:

- `[[card:Name]]` — hover shows the card (English name, or any name `lookup.py` resolves)
- `[[rule:704.5b]]` — hover shows the verbatim rule
- `[[ruling:ruby-medallion-1]]` — hover shows the ruling (ids come from `lookup.py`)
- `[[link:Label|https://...]]` — plain link
- `{U} {2} {X} {U/B} {T}` — mana and tap symbols
- Light markup: `**bold**`, `*italic*`, `` `code` ``; a blank line starts a new paragraph

```jsonc
{
  "lang": "en",                        // "en" or "fr": picks the page labels
  "title": "Short name for the question",
  "question": "The person's question, lightly cleaned up",
  "shortAnswer": "1–3 sentences with [[rule:...]] and [[ruling:...]] refs.",
  "confidence": {
    "level": "high",                   // "high" | "medium" | "low" — see the levels below
    "reasons": ["Why the evidence settles it (or doesn't)."],
    "assumptions": ["Game-state facts you had to assume."],
    "notRetrieved": ["Anything you could not fetch, or fetched from the web, and how it affects the answer."]
  },

  "cards": [                           // shown in this order; inline-referenced cards are added after
    "Thassa's Oracle",                 // from the card database
    { "name": "Sol Ring", "note": "commander" },   // database card + a small tag
    {                                  // a card NOT in the database (web fallback): full object
      "name": "New Card",
      "manaCost": "{1}{U}",
      "typeLine": "Creature — Merfolk Wizard",
      "oracleText": "Verbatim Oracle text.",
      "power": "1", "toughness": "3",  // or "loyalty", or "defense"
      "colors": ["U"],
      "faces": [ { "name": "Front", "manaCost": "...", "typeLine": "...", "oracleText": "..." } ],  // optional
      "url": "https://mtg.wtf/card/...",   // required: the page the text was copied from
      "source": "mtg.wtf, 2026-10-02"
    }
  ],

  "rules": ["704.5a"],                 // extra rules to list; inline-cited rules are added automatically

  "rulings": [
    "thassas-oracle-2",                // a ruling id from lookup.py
    "sol-ring-*",                      // all rulings of that card
    {                                  // a ruling for a web-fallback card: full object
      "id": "new-card-1", "card": "new-card", "date": "2026-09-01",
      "source": "wotc",                // "wotc" = official; "scryfall" = Scryfall note
      "text": "Verbatim ruling text.",
      "url": "https://..."             // required: the page it was copied from
    }
  ],

  "steps": [
    { "text": "What happens, citing [[rule:603.2]] or [[ruling:id]] for each claim.", "note": "Optional aside." }
  ],

  // Omit "reddit" for the default "search r/mtgrules yourself" link block,
  // set it to false to hide the section, or give the full object when you searched:
  "reddit": {
    "searched": true,
    "threads": [
      { "title": "Thread title", "url": "https://www.reddit.com/r/mtgrules/comments/...", "subreddit": "r/mtgrules",
        "date": "2021-03-02", "comments": 14, "judgeFlair": false, "summary": "What the thread concluded." }
    ],
    "overview": "What the discussion looks like overall.",
    "opinions": ["Opinion 1 and who held it."],
    "agreesWithOfficial": "yes",       // "yes" | "partly" | "no" | "unknown"
    "notes": "Caveats: old rules, different card, etc.",
    "searchUrl": "https://www.reddit.com/r/mtgrules/search/?q=..."
  }
}
```

## Confidence levels

- **high** — every card came from the database, every step cites retrieved text, no
  assumption flips the verdict, and either a ruling addresses this interaction or no step
  of the rules chain can reasonably be read another way.
- **medium** — one step rests on interpretation, or on a stated assumption.
- **low** — something could not be retrieved, text came from the web or from the person,
  or the rules don't settle it.

`build.py` enforces what it can check: `high` is refused when `notRetrieved` isn't
empty, when a card or a ruling came from the web, or when the short answer cites no rule
or ruling. The rest is judgment.

## What build.py checks

Every id must resolve. A card or ruling written by hand (web fallback) must carry the
`url` it was copied from, is shown on the page as "from the web, not verified", and keeps
confidence below `high`. A hand-written ruling on a card the database holds, dated on or
before the database build, is refused: a real one would be in the database. With
`--check` or `--link-only`, the script also prints the verbatim text behind each rule and
ruling the short answer cites, so you can re-read them against your sentence.

`build.py` adds `crEffectiveDate`, `cardDataDate`, `generatedAt`, `allCardsLink` (one
Scryfall link for all cards), each card's text, link, image and `oracleId`, and the
verbatim text of every rule and ruling (hand-written ruling objects get `"custom": true`).
A card id is its name in lowercase with dashes (`Thassa's Oracle` → `thassas-oracle`),
which is also the prefix of its ruling ids. The same data, reduced to prose and ids,
is what the share link carries: see `share-payload.md`.

Never invent a thread URL: if nothing could be retrieved, leave `threads` empty and
keep `searchUrl` so the person can look themselves.
