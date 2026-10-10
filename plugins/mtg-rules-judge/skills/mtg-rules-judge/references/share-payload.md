# The share link — what the hosted viewer receives

An answer can be opened as a web page at the viewer (`docs/` of this repository,
served by GitHub Pages). The whole answer travels in the URL fragment; nothing is
stored on a server and the fragment never leaves the browser. `scripts/share.py`
builds the link, `build.py --link-only` prints it as a `Link:` line for Claude to put in
the reply (in the first turn by default, or when the person asks for it after a
`quick` answer; a full `build.py` run also puts it in the HTML
page's share bar). This file is the contract
between `share.py` and the viewer's `decode.js` / `render.js`.

## URL

The same payload (below) can be written two ways. The number before the first `.` is the
**encoding version**; the payload has its own `v` field, so the two move independently.
The viewer reads both; `share.make_link` writes the readable one whenever it can.

### Readable (`2`): what Claude types

```
https://<viewer>/#2.<lang>=t<title>=q<question>=a<short answer>=c<level>=r<reason>...=z<check>
```

Claude has to type the link into its reply. It copies compressed text (random characters)
at about 50 characters a second and ordinary words about five times faster, so this form
keeps the prose as words: a link of ~2,200 characters takes ~12 s where the compressed
~1,500 characters took ~30 s (measured by having the model copy both).

**Text.** Letters and digits of any language and `- . , : ; /` are written as they are; a
space is `+`; everything else is `!` and one character, or `!u<hex>;` for any other code
point (also for a `.` followed by another `.`):

| code | stands for | code | stands for | code | stands for |
|---|---|---|---|---|---|
| `!r` | `[[rule:` | `!p` `!P` | `(` `)` | `!x` | `!` |
| `!c` | `[[card:` | `!m` `!M` | `{` `}` | `!w` | `?` |
| `!g` | `[[ruling:` | `!a` `!A` | `'` `’` | `!N` | newline |
| `!l` | `[[link:` | `!q` | `"` | `!s` `!S` | no-break space, narrow no-break space |
| `!z` | `]]` | `!b` `!i` | `**` `*` | `!d` `!D` | `«` `»` |
| `!y` | `[[` | `!t` `!e` | `+` `=` | `!k` `!K` `!E` | `—` `–` `…` |

So the link only ever holds letters, digits and `- . , : ; / ! + =`: nothing a chat app
turns into formatting (`*`, `_`, `~`, `$`), nothing that ends a link early (brackets,
quotes, spaces), and it ends on a letter or digit.

**Fields.** After `2.` comes the language, then fields, each introduced by `=` and one
letter. Fields that repeat appear once per item, in order. A reader skips letters it
doesn't know.

| field | payload | field | payload |
|---|---|---|---|
| `=t` `=q` `=a` | `title`, `question`, `shortAnswer` | `=k` | a slim card: its `name` (`id` is `slug(name)`) |
| `=c` | `confidence.level` | `=i` `=h` | that card's `oid` and `h`, as they are |
| `=r` `=u` `=n` | one item of `confidence.reasons` / `assumptions` / `notRetrieved` | `=m` `=j` | that card's `note`; its `id` when it isn't `slug(name)` |
| `=s` | a step's `text` | `=l` | `rules`, comma-separated |
| `=o` | the `note` of the step before it | `=g` | a ruling reference (below) |
| `=d` `=e` `=f` | `cr`, `at`, `db` | `=y0` | `reddit: false` |
| `=x` | everything else, compressed (below) | `=z` | checksum, always last |

- `=g<id>,<d>,<h>`: `id` is written `<p>-<n>` when it is `<id of the p-th =k card>-<n>`
  (the usual case: `1-4` for `ruby-medallion-4`), `d` is left empty when it equals the
  date of the ruling before, and a fourth item gives `card` when it isn't the id minus
  its last `-<n>`.
- `=x`: cards with their full text (web fallback), hand-written rulings and a `reddit`
  object have no readable form. They travel as
  `base64url(zlib_compress(json))` of `{"cards": [[index, card]...], "rulings": [[index, ruling]...], "reddit": {...}}`,
  with `.` in place of `_`; each `[index, object]` is inserted at that index, in order.
- `=z`: the low 16 bits of CRC-32 over the UTF-8 bytes of everything before `=z`
  (NFC-normalised), as 4 hex digits. When it doesn't match, the viewer still shows the
  page, with a notice that the link was altered. When it is missing, the link was cut
  short (clicked while the reply was still streaming, say): the viewer drops the last,
  partial field, shows the rest and says the link isn't complete. `share.py` raises in
  both cases.

`share.encode_readable` decodes what it wrote and compares it with the payload (see
`canon`); for a payload this form can't carry exactly (an unknown field, a number where
text belongs) it returns `None` and `make_link` writes the compressed form instead.
`MTG_JUDGE_LINK_FORMAT=1` forces the compressed form. A readable link can be up to
`READABLE_MAX_CHARS` (8000) long.

### Compressed (`1`)

```
https://<viewer>/#1.<base64url(zlib_compress(utf8(json)))>
```

- `zlib_compress` is Python's `zlib.compress(data, 9)` with the zlib wrapper (not raw
  deflate). The browser inflates it with `DecompressionStream("deflate")`. The wrapper's
  Adler-32 checksum means a mistyped character fails deterministically ("damaged link")
  instead of producing garbage.
- base64url alphabet (`-` and `_`), padding removed. The JSON is minified
  (`separators=(",", ":")`, `ensure_ascii=False`).
- Capped at `LINK_MAX_CHARS` (3000), about a minute of typing for Claude. A typical
  answer is 1,000–2,000 characters. The env variable `MTG_JUDGE_LINK_MAX` overrides the
  cap of whichever form is written.

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
    { "id": "ruby-medallion-1", "card": "ruby-medallion", "d": "2023-07-28", "h": "a1b2c3d4" },
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
- PullPush (an archive of Reddit; Reddit itself refuses requests from other sites): when
  the `reddit` block has no threads, one
  `GET https://api.pullpush.io/reddit/search/submission/?subreddit=mtgrules&q="Card A" "Card B"`
  with the first three card names, then the first two if nothing names all three. The
  newest six threads are listed as found by the page, not read for the answer.

## Fixtures

`tests/fixtures/<name>.in.json` → `.resolved.json` (build.py output) → `.share.json`
(this payload) → `.fragment.txt` (the `1.…` fragment) and `.readable.txt` (the `2.…`
fragment). Regenerate with `python3 tests/make_fixtures.py`; check with
`python3 tests/test_share.py`, which also runs the viewer's decoder on them
(`tests/test_decode.mjs`) when node is installed. The viewer
loads a fixture directly with `?fixture=<name>` (copies live in `docs/fixtures/`).
