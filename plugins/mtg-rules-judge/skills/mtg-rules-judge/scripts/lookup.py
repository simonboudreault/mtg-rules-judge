#!/usr/bin/env python3
"""All the evidence for a rules question in ONE call: cards, rulings, CR rules,
glossary entries and rule searches.

  lookup.py --card "Ruby Medallion" --card "Fireball" \\
            --rule 601.2b 601.2f 118.7a --glossary "mana value" --search generic reduce

  --card NAME       repeatable; English or French name, a face name, or close spelling.
                    Prints Oracle text and every ruling with its id (e.g. ruby-medallion-1).
  --rule ID ...     exact rules; a rule without a letter (601.2) includes its subrules,
                    a section (613) prints the whole section (capped by --max).
  --glossary TERM   repeatable.
  --search WORDS    repeatable; rules containing ALL the words ("generic reduce").
  --max N           cap per --rule / --search query (default 40 / 15).

Cards come from the bundled database (data/cards.json). A card missing from it
is fetched from the Scryfall API when the sandbox allows it; otherwise the output
says NOT_IN_BUNDLE and lists close names.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rules as cr  # noqa: E402
from carddb import CardDB, card_text  # noqa: E402


def cr_data():
    lines = cr.load(os.environ.get("MTG_CR_PATH", cr.DEFAULT_PATH))
    header, body, gloss = cr.split_parts(lines)
    date = next((l.strip() for l in header[:40] if "effective" in l.lower()), "effective date unknown")
    date = "effective " + date.split("effective as of", 1)[1].strip().rstrip(".") if "effective as of" in date else date
    return date, cr.parse_rules(body), cr.parse_glossary(gloss)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--card", action="append", default=[])
    ap.add_argument("--rule", nargs="+", action="extend", default=[])
    ap.add_argument("--glossary", action="append", nargs="+", default=[])
    ap.add_argument("--search", action="append", nargs="+", default=[])
    ap.add_argument("--max", type=int, default=None)
    a = ap.parse_args()
    a.glossary = [" ".join(g) for g in a.glossary]
    a.search = [" ".join(q) for q in a.search]

    db = CardDB() if a.card else None
    date, rules, gloss = cr_data()
    if db is not None:
        if db.loaded:
            m = db.meta
            print(f"# Card DB built {m.get('built')} from {m.get('source')} ({m.get('cards')} cards"
                  f"{', French names' if m.get('french_names') else ''}) · CR {date}")
        else:
            print(f"# Card DB NOT INSTALLED (run scripts/build_card_db.py on a computer with internet) · CR {date}")
    else:
        print(f"# CR {date}")

    shown = set()
    for q in a.card:
        rec, how, alts = db.find(q)
        if rec is not None and rec["n"] in shown:
            print(f"\n## CARD {q}: same card as {rec['n']} above")
            continue
        if rec is None:
            try:
                rec, how = db.fetch_remote(q), "fetched from the Scryfall API (not in the bundle)"
            except Exception as e:  # network blocked, unknown card...
                code = getattr(e, "code", None)
                why = f"Scryfall has no card '{q}'" if code == 404 else "Scryfall API unreachable from this sandbox"
                print(f"\n## NOT_IN_BUNDLE: {q}")
                print(f"  {why}." + (f" Close names in the bundle: {', '.join(alts)} (if it's one of those,"
                                     " look it up again by that name)." if alts else ""))
                print("  -> Card newer than the bundle, or a misspelling? Use the web fallback in SKILL.md"
                      " and pass the card to build.py as a full object.")
                continue
        shown.add(rec["n"])
        rs = db.rulings_for(rec)
        tag = "" if how == "exact" else f"  ({how})"
        print(f"\n## CARD {rec['n']}{tag}" + ("  [token]" if rec.get("tok") else ""))
        print(card_text(rec))
        if alts:
            print(f"  (other close names: {', '.join(alts)})")
        print(f"  Rulings ({len(rs)}):" if rs else "  No rulings.")
        for r in rs:
            src = "" if r["source"] == "wotc" else " [Scryfall note, not official]"
            print(f"   [{r['id']}] {r['date']}{src} {r['text']}")

    for q in a.rule:
        q = q.rstrip(".")
        hits = [(n, t) for n, t in rules if cr.in_scope(n, q)]
        cap = a.max or 40
        print(f"\n## RULE {q}")
        if not hits:
            print(f"  [no rule {q} in the bundled Comprehensive Rules]")
        for n, t in hits[:cap]:
            print(cr.fmt(n, t))
        if len(hits) > cap:
            print(f"  [... {len(hits) - cap} more; ask for narrower numbers]")

    for q in a.glossary:
        ql = q.lower()
        exact = [e for e in gloss if e[0].lower() == ql]
        hits = exact or [e for e in gloss if ql in e[0].lower()]
        print(f"\n## GLOSSARY {q}")
        for term, defn in hits[:10]:
            print(f"{term}\n{defn}")
        if not hits:
            print(f"  [no glossary term matching '{q}']")

    for q in a.search:
        words = q.lower().split()
        hits = [(n, t) for n, t in rules if all(w in t.lower() for w in words)]
        cap = a.max or 15
        print(f"\n## SEARCH \"{q}\" ({len(hits)} match(es){', first ' + str(cap) if len(hits) > cap else ''})")
        for n, t in hits[:cap]:
            first = t.split("\n")[0]
            print(cr.fmt(n, first if len(first) < 300 else first[:300] + " [...]"))

    # The model reads this right before it decides what to do next (see SKILL.md, step 4).
    print("\n## NEXT\n"
          "Once your reasoning is settled, the message in which you write answer.json has two blocks, in\n"
          "this order: (1) a TEXT block with the short answer for the person (1-3 sentences with the key\n"
          "rule number, confidence, assumptions), (2) the tool call. Your thinking is hidden from them:\n"
          "an answer you only reasoned out has not been said. They are waiting for it now; the link takes\n"
          "another minute.")


if __name__ == "__main__":
    main()
