# The share link — what the hosted viewer receives

An answer can be opened as a web page at the viewer (`docs/` of this repository,
served by GitHub Pages). The whole answer travels in the URL fragment; nothing is
stored on a server and the fragment never leaves the browser. `scripts/share.py`
builds the link, `build.py --link-only` prints it as a `Link:` line for Claude to put in
the reply when the person asks for it (a full `build.py` run also puts it in the HTML
page's share bar). This file is the contract
between `share.py` and the viewer's `decode.js` / `render.js`.

## URL

```
https://<viewer>/#1.<base64url(zlib_compress(utf8(json)))>
```

- `1` is the **encoding version**; the viewer rejects anything else. The JSON has its
  own `v` field (payload version), so the two can move independently.
- `zlib_compress` is Python's `zlib.compress(data, 9)` with the zlib wrapper (not raw
  deflate). The browser inflates it with `DecompressionStream("deflate")`. The wrapper's
  Adler-32 checksum means a mistyped character fails deterministically ("damaged link")
  instead of producing garbage.
- base64url alphabet (`-` and `_`), padding removed. The JSON is minified
  (`separators=(",", ":")`, `ensure_ascii=False`).
- A link in the page can be up to `EMBED_MAX_CHARS` (8000): nobody types it. The printed
  link is capped at `LINK_MAX_CHARS` (3000, env
  `MTG_JUDGE_LINK_MAX`), because Claude then types it into the reply by hand, about as
  slowly as writing a long paragraph. A typical answer is 1,000–2,000 characters.

## Payload (`v: 1`)

```jsonc
{
  "v": 1,
  "lang": "en",                      // "en" | "fr": viewer labels
  "title": "...", "question": "...", "shortAnswer": "...",   // same inline markup as answer-schema.md
  "confidence": { "level": "high", "reasons": [], "assumptions": [], "notRetrieved": [] },
  "steps": [ { "text": "...", "note": "..." } ],
  "reddit": { ...full object... } | false | absent,   // false = section hidden; absent = viewer shows the
                                                       // default "search r/mtgrules yourself" block
  "cr": "September 25, 2026",        // Comprehensive Rules the answer was checked against (text, as in the CR header)
  "at": "2026-10-06",                // generatedAt
  "db": "2026-10-05",                // card database build date

  "cards": [
    // (a) a card from the database: slim. The viewer fetches text and image from Scryfall.
    { "id": "ruby-medallion", "name": "Ruby Medallion", "oid": "<Scryfall oracle_id>", "h": "3f9a1c2e", "note": "commander" },
    // (b) a card from the web fallback (no oracle id): full object, exactly as in answer-schema.md.
    //     The viewer shows this text as-is and only asks Scryfall for an image, by name.
    { "id": "new-card", "name": "New Card", "manaCost": "{1}{U}", "typeLine": "...", "oracleText": "...",
      "power": "1", "toughness": "3", "colors": ["U"], "faces": [ ... ], "source": "mtg.wtf, 2026-10-02" }
  ],

  "rules": ["601.2b", "601.2f"],     // every cited rule number; the viewer fetches the text from docs/data/rules/<SSS>.json

  "rulings": [
    // (a) a ruling from the database: reference. The viewer fetches the card's rulings from Scryfall
    //     and picks the one whose text hash matches; if none matches it falls back to the date and says so.
    { "id": "ruby-medallion-1", "card": "ruby-medallion", "d": "2004-10-04", "h": "a1b2c3d4" },
    // (b) a hand-written ruling (answer.json gave a full object, or the card is a web-fallback card): full.
    { "id": "new-card-1", "card": "new-card", "date": "2026-09-01", "source": "wotc", "text": "..." }
  ]
}
```

Rules of thumb: a card **with** `oid` is slim and resolved live; a card **without** `oid`
is complete and never overridden. A ruling **with** `h` is a reference; one **with**
`text` is complete. `id` is `slug(name)`: lowercase, every run of characters outside
`a-z0-9` becomes `-`, leading/trailing `-` removed (same regex in `carddb.py`,
`render.py` and the viewer), so `[[card:...]]` and `[[ruling:...]]` refs resolve before
any network request.

## Hashes

`h` = first 8 hex digits of SHA-1 over the UTF-8 bytes of a canonical string:

- **card:** if the card has `faces`, `"\n//\n".join(face.oracleText or "" for each face)`,
  otherwise `oracleText or ""`. From Scryfall data that is `card_faces[].oracle_text`
  joined with `"\n//\n"`, or `oracle_text`.
- **ruling:** the ruling text exactly as Scryfall's `comment`.

Known vectors: `sha1("Flash")[:8] = b6248223`, `sha1("x")[:8] = 11f6ad8e`.
A mismatch is not an error: the viewer shows the current text with a small
"text changed since this answer" note. The short answer in the chat was reasoned from
the text retrieved at the time and remains the verified copy.

## What the viewer fetches

- `docs/data/meta.json` — `crEffectiveDate`, `crEffectiveIso`, `cardDataDate`,
  `sections`, `ruleCount`. When `crEffectiveDate` differs from the payload's `cr`, the
  viewer notes that the rules were updated since the answer.
- `docs/data/rules/<SSS>.json` — `{ "id": "601", "title": "Casting Spells", "rules": { "601.2f": "text..." } }`,
  one file per three-digit section. Rule text keeps its `Example:` lines, joined with
  `"\n    "`. Both are written by `tools/build_site_data.py` from the bundled CR, in the
  same commit as every data update.
- Scryfall: one `POST https://api.scryfall.com/cards/collection` with
  `{"identifiers": [{"oracle_id": ...}, {"name": ...}]}` (75 max), then
  `GET <card.rulings_uri>` for each card that has ruling references.

## Fixtures

`tests/fixtures/<name>.in.json` → `.resolved.json` (build.py output) → `.share.json`
(this payload) → `.fragment.txt` (the `1.…` fragment). Regenerate with
`python3 tests/make_fixtures.py`; check with `python3 tests/test_share.py`. The viewer
loads a fixture directly with `?fixture=<name>` (copies live in `docs/fixtures/`).
