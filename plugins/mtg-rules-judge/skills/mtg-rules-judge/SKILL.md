---
name: mtg-rules-judge
description: "Answer Magic: The Gathering rules questions like a careful judge, grounded in the bundled Comprehensive Rules and an offline database of Oracle text and official card rulings, delivered as a short answer with a confidence level and, when the person then asks for it (\"link\"), a link to a full answer page (hover cards, rules and rulings), with Reddit discussion on request. Use it for ANY MTG rules question, card interaction, \"does X work with Y\", \"what happens if\", timing, stack, layers, replacement effects, combat, commander rules or a disputed play at the table, in English or French, even when the person only names cards and describes a board state without saying \"rules\", and for the follow-up \"link\" / \"lien\" after such an answer."
---

# MTG Rules Judge

The person wants rules answers they can trust at the table. The failure this skill
exists to prevent is the confident, plausible, wrong answer: a misremembered Oracle
text, an invented rule number, a ruling from the wrong card. So the whole method
rests on one principle:

**Every factual claim in the answer is backed by text you retrieved during this
conversation** — a Comprehensive Rules (CR) excerpt, an Oracle text, or an official
ruling — and is quoted so the person can check it. If you didn't retrieve it, you
don't assert it. "The rules don't directly address this" and "I couldn't retrieve
this card's text, here is what I'd expect but can't confirm" are acceptable answers;
a guess dressed as fact is not.

Your memory of Magic is useful for knowing *where to look* and *what might matter*.
It is not a source. Cards get errata, rules get rewritten every few months, and
memory blends versions.

## Speed: the answer now, the link on request

The evidence is all local, so an answer is four short steps, and then you stop:

1. **One `lookup.py` call** with every card and every rule you expect to need.
2. **Think it through.** At most one more `lookup.py` call if the reasoning turns up
   a rule you didn't ask for.
3. **Write `answer.json`** (prose and ids only).
4. **Reply with the short answer and the confidence level, and end your turn.**

That is the whole first turn. The person is often mid-game and the short answer is
what they are waiting for, so nothing else runs before it: no `build.py`, no page, no
artifact, no link. The link is a **second turn**, and only when the person asks for it
(they type "link"): one `build.py --link-only` call, then the link.

Don't create a task list, don't read the template or the schema file (the example
below is enough), and don't run `rules.py info` (the lookup header shows the dates).
Put independent tool calls in the same turn.

### Finding the scripts

`<skill-dir>` below is the folder that holds this file. Use the base directory shown
when the skill loaded, if a real path was shown. If none was shown, don't build a path
from the skill's name: a guess such as `/mnt/skills/…` costs a failed call and then a
search. Start your first command with this line instead, which finds the folder, and
use `"$D"` as `<skill-dir>` in that same command:

```
D=$(find ~/.claude /root/.claude /mnt / -type d -path '*/skills/mtg-rules-judge' -not -path '*/.trash/*' -print -quit 2>/dev/null)
```

`lookup.py` prints the folder on its first line (`# Skill dir: …`); use that path in
every later command.

## Resources

- `scripts/lookup.py` — cards, rulings, CR rules, glossary and rule search in one call.
- `data/cards.json` — offline Oracle text and rulings for every card (built from
  Scryfall bulk data by `scripts/build_card_db.py`, run on a computer with internet).
- `scripts/build.py` — checks every reference in your compact answer JSON, fills in
  every verbatim text and, with `--link-only`, prints the link to the full answer page.
  (It can also render that page to a static HTML file; that delivery is switched off.)
- `references/MagicCompRules.txt` + `scripts/rules.py` — the CR; `rules.py` still works
  for one-off queries (`rule`, `search`, `glossary`, `toc`).
- `scripts/scryfall.py` — live Scryfall API; only useful where the sandbox has network.
- `references/answer-schema.md` — the fields of `answer.json`; read it only for an
  unusual field.

## Workflow

### 1. Frame the question (in your head)

- Every card named or implied (tokens, emblems, copies, the commander).
- The game-state facts given: zones, controllers, phase/step, what's on the stack.
- The actual question — often narrower than the story around it.
- Missing facts that would change the answer (format, haste, who is the active
  player...). If the answer flips on one, ask, or answer both branches explicitly.
  Don't silently assume.

### 2. Gather the evidence in one call

```
python3 <skill-dir>/scripts/lookup.py --card "Card A" --card "Card B" \
    --rule 601.2f 118.7a 702.19 --glossary trample --search generic reduce
```

- `--card` for **every** card. English or French names, face names and small
  misspellings all resolve; the output says which card it resolved to — check it.
- `--rule`: ask generously. A rule without a letter (`702.19`) prints its subrules; a
  section (`613`) prints the whole section. Asking for an extra rule costs nothing; a
  second round trip costs time.
- `--glossary` for each keyword or game term; `--search` when you don't know the number.
- Read **every** ruling printed. Rulings exist to settle interactions, and a ruling on
  a third card sometimes settles the question outright. Each has an id like
  `ruby-medallion-1`; those ids are what you cite.

Where to look in the CR (a map, not a checklist):

| Topic | Rules |
|---|---|
| Golden rules, card vs rules conflicts | 101 |
| Priority, stack, casting, resolving | 117, 405, 601, 608 |
| Costs, cost increases and reductions | 118, 601.2b, 601.2f |
| Colour, characteristics, mana value | 105, 109.3, 202 |
| Activated / triggered / static abilities | 602, 603, 604 |
| Replacement & prevention effects | 614, 615, 616 |
| Continuous effects, layers, dependency, timestamps | 611, 613 |
| State-based actions | 704 |
| Combat | 506–511 |
| Keywords (actions / abilities) | 701, 702 |
| Copies, copiable values | 707 |
| Face-down, double-faced, split, etc. | 708–712 |
| Leaving/changing zones, "new object" | 400.7, 603.6, 603.10 |
| Commander | 903 |
| Multiplayer | 800–810 |

**If a card prints `NOT_IN_BUNDLE`** (newer than the database, a misspelling, or the
database isn't installed), get it from the web in **one turn**, firing these in
parallel and keeping the first that works:

- WebFetch `https://api.scryfall.com/cards/named?fuzzy=<url-encoded name>`
- WebFetch `https://mtg.wtf/card?q=%21%22<url-encoded exact name>%22`
- WebSearch `"<name>" mtg card rulings` — then WebFetch an mtg.wtf link of the form
  `https://mtg.wtf/card/<set>/<number>/<Name>` from the results (that form often works
  when the search form fails).

Ask WebFetch for verbatim fields: *"Copy character for character, no paraphrase: name,
mana cost, type line, full Oracle text, power/toughness, and every ruling with its
date."* Put that card in `answer.json` as a full object (see below) and say where its
text came from under `confidence.notRetrieved`. If nothing works, ask the person to
paste the Oracle text and mark confidence Low. For a French name the database doesn't
know, WebSearch `"<nom>" carte magic` for the English name, then look it up again.

### 3. Reason it through

Think freely, but trace the actual sequence of events in order and name the rule or
ruling that governs each step (cast → triggers → stack order → resolution →
replacement effects → state-based actions → next priority...). Walking the sequence
catches most errors a "vibes" answer misses.

Then argue the opposite conclusion. If a competent player would read it the other
way, find the rule or ruling that decides between the two readings. If nothing
decides it, say so — that is a real and useful answer.

Check the result against the official rulings: if a ruling contradicts your trace,
the ruling wins and your trace has a mistake — find it.

### 4. Community discussion — only on request

By default, skip it: the answer page carries a small "search r/mtgrules yourself"
link. Search only when the person asks, or when the official sources truly don't
decide the question. Then do one WebSearch (e.g. `reddit mtgrules "<Card A>" "<Card B>"`)
and work from the snippets — don't try to open Reddit threads, they can't be fetched.
Never invent a thread.

This material is **not evidence** for the main answer. People are often wrong, talk
about older rules or a different card, or answer a slightly different question. Use it
only for the separate community section: what people concluded, where they disagreed,
and whether the consensus matches the official sources (if it contradicts the CR or a
ruling, say so plainly). Note thread dates when old rules may be involved.

### 5. Write `answer.json`

Write `answer.json` in your working directory. It is the full answer in compact form,
and the link is made from it later. You write **only prose and ids**; `build.py` fills
in the verbatim Oracle text, rule text and ruling text, the dates and the Scryfall
links.

```json
{
  "lang": "en",
  "title": "Ruby Medallion and X spells",
  "question": "How does Ruby Medallion interact with {X} spells?",
  "shortAnswer": "It reduces the X part. You announce X first ([[rule:601.2b]]), then [[card:Ruby Medallion]] takes {1} off the total cost ([[rule:601.2f]], [[ruling:ruby-medallion-1]]).",
  "confidence": {
    "level": "high",
    "reasons": ["An official ruling on Ruby Medallion addresses X spells directly."],
    "assumptions": ["The X spell is red."],
    "notRetrieved": []
  },
  "cards": ["Ruby Medallion"],
  "rulings": ["ruby-medallion-*"],
  "steps": [
    { "text": "**Announce X** ([[rule:601.2b]]).", "note": "Optional aside." }
  ]
}
```

- Inline references — `[[card:Name]]`, `[[rule:601.2f]]`, `[[ruling:ruby-medallion-1]]`,
  `[[link:Label|https://...]]` — become hover popovers in any text field, step notes
  included. Every card, rule and ruling referenced inline is added to the page
  automatically.
- `cards`: names, in the order to show them. `{"name": "X", "note": "commander"}` adds a
  tag. A card you got from the web goes in as a full object — see
  `references/answer-schema.md`.
- `rules`: extra rule ids to list beyond those cited inline. Use exact numbers
  (`702.19c`, not `702.19` when you mean the subrule).
- `rulings`: extra ruling ids; `"<card-id>-*"` adds all of a card's rulings. Use `-*`
  for the cards at the heart of the question when they have up to ~8 rulings; for
  cards with many, list the relevant ones.
- `reddit`: leave it out for the default link block, `false` to hide the section, or a
  full object when you did search (see the schema file).

**Keep it tight:** the person is waiting while you write this file, and the length of
the link follows the length of your prose (card, rule and ruling texts cost almost
nothing: they travel as ids). A few short steps beat a long walkthrough.

Don't run `build.py` now.

### 6. Reply with the short answer, then stop

As soon as `answer.json` is written, send the reply. It holds, in the person's
language:

- the verdict: 1–3 sentences per question asked, with the key rule/ruling number;
- the confidence level, with the reason in a few words when it isn't high;
- any assumption or missing fact that matters;
- a last line offering the link.

```
No. Ruby Medallion takes {1} off the total cost once, not once per X (CR 601.2f;
ruling of 2004-10-04). Confidence: high.

Say "link" for the full page: cards, rules, rulings and the step-by-step.
```

In French the last line is: `Dites « lien » pour la page complète : cartes, règles,
rulings et le déroulement pas à pas.`

Then **end your turn**. After `answer.json` there is no other tool call in this turn:
no `build.py`, no HTML page, no artifact, no file sent. The person may never ask for
the link, and everything built ahead of the answer is time they spend waiting.

One exception: if the person already asked for the link in the same message as the
question, do step 7 in this turn and put the link under the short answer.

### 7. When the person asks for the link

"link", "lien", "full page", "show me the details / the sources": any of these after an
answer means this step, and nothing more than this step.

```
python3 <skill-dir>/scripts/build.py answer.json --link-only
```

It writes no file. It checks every reference and prints a `Link: …` line.

- If it prints `ERROR` lines, fix those ids in `answer.json` and run it again.
- If `answer.json` is gone (new session, cleaned sandbox), write it again from the
  conversation, then run the command.
- When the line holds a URL, the reply is that URL on its own line (e.g.
  "Full answer: <url>") and nothing else: the person already has the answer. Copy it
  character for character; never shorten or rebuild it.
- If the line says the link was omitted, say in one sentence that the answer is too
  large for a link and offer the plain-text version below.
- If fixing the file changed your conclusion, say so plainly before the link.

<!-- DISABLED (page and artifact delivery are switched off; do not follow this block. Restore it to bring them back):
Run `python3 <skill-dir>/scripts/build.py answer.json -o answer.html`, then **publish
`answer.html` by its file path** with your artifact tool. Never paste the HTML into your
reply — it's a 25–50 KB file and retyping it is the slowest thing this skill could do.
If there is no artifact tool, send the file.
-->

**Language:** write the prose in the language the person used and set `"lang"`
(`"en"` or `"fr"`) so the page labels match. CR text, Oracle text and rulings stay
verbatim in English; when the person writes in French, add a short translation after a
quote in your prose where it helps.

**Plain-text version:** if the person asks for the details as text, or no link can be
made, use these sections in Markdown with the same content: Short answer · Cards
(Oracle text + one Scryfall link for all cards) · Relevant rules (CR date) · Official
rulings · How it plays out (numbered steps with rule/ruling citations) · Confidence
(with assumptions and anything not retrieved).

For a quick, simple question ("does deathtouch work with fight?"), keep every section
short.

## Keeping the data current

The rules file and the card database are refreshed automatically: a scheduled job
rebuilds them when Wizards publishes new Comprehensive Rules or a new set is released,
and the plugin updates itself for everyone who installed it. You don't need to manage
that. Two things still matter at answer time:

- **Comprehensive Rules:** the lookup header shows the effective date. If the question
  involves a mechanic the bundled CR doesn't define (a brand-new keyword, say), say so
  plainly and don't improvise rules for it; the next update will carry them. You can
  check `https://magic.wizards.com/en/rules` with WebFetch to see whether a newer
  version exists.
- **Card database:** the lookup header shows when it was built. A card that prints
  `NOT_IN_BUNDLE` because it is newer than that is normal in the days around a set
  release: fetch it from the web as described above and carry on.
