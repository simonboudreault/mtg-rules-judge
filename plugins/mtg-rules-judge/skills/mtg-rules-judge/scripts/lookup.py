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
  --max N           cap per --rule / --search query (default 60 / 15).

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
from carddb import CardDB, card_text, kind, norm, type_line  # noqa: E402

FULL = 3  # up to this many cards sharing a short name are printed whole; more are listed


def print_card(db, rec, note="", close=()):
    rs = db.rulings_for(rec)
    k = kind(rec)
    print(f"\n## CARD {rec['n']}{note}" + ("" if k == "card" else f"  [{k}]"))
    print(card_text(rec))
    if close:
        print(f"  (other close names: {', '.join(close)})")
    print(f"  Rulings ({len(rs)}):" if rs else "  No rulings.")
    for r in rs:
        src = "" if r["source"] == "wotc" else " [Scryfall note, not official]"
        print(f"   [{r['id']}] {r['date']}{src} {r['text']}")


def print_names(db, names, cap=20):
    for n in names[:cap]:
        print(f"   - {n} · {type_line(db.by_name[norm(n)])}")
    if len(names) > cap:
        print(f"   ... and {len(names) - cap} more")


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
    if hasattr(sys.stdout, "reconfigure"):  # card text holds "−" and "—"; a Windows pipe can't encode them
        sys.stdout.reconfigure(encoding="utf-8")
    a.glossary = [" ".join(g) for g in a.glossary]
    a.search = [" ".join(q) for q in a.search]

    db = CardDB() if a.card else None
    date, rules, gloss = cr_data()
    # First line: where the skill lives, so later commands don't have to guess the path.
    print("# Skill dir: " + os.path.dirname(HERE).replace("\\", "/"))
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
        if how == "ambiguous":  # several cards are named "<q>, ...", and none is named just <q>
            other = db.by_name.get(norm(q))
            print(f"\n## AMBIGUOUS: {q}")
            print(f"  {len(alts)} cards are named \"{q}, ...\"" + (f", and \"{q}\" alone is a {kind(other)}" if other else "")
                  + ". Use the one the person means, under its full name; if the question doesn't say which, ask.")
            if len(alts) <= FULL:
                for n in alts:
                    if n not in shown:
                        shown.add(n)
                        print_card(db, db.by_name[norm(n)], f"  (one of the cards named \"{q}, ...\")")
            else:
                print_names(db, alts)
                print("  -> Look up the right one by its full name.")
            if other is not None:
                print(f"\n  \"{q}\" alone  [{kind(other)}]\n{card_text(other)}")
            continue
        if rec is not None and rec["n"] in shown:
            print(f"\n## CARD {q}: same card as {rec['n']} above")
            continue
        if rec is None:
            try:
                rec, how = db.fetch_remote(q), "fetched from the Scryfall API (not in the bundle)"
                alts = []  # they were guesses for a name the bundle doesn't have
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
        close = alts if how.startswith("fuzzy") else []      # near spellings of a misspelt name
        same = [] if how.startswith("fuzzy") else alts       # cards named "<q>, ..."
        if same:
            print(f"\n## NOTE: \"{q}\" is also the start of {len(same)} other card name(s), "
                  + ("printed" if len(same) <= FULL else "listed") + " after it. Make sure which card the person means,"
                  " and write its full name in answer.json.")
        print_card(db, rec, "" if how == "exact" else f"  ({how})", close)
        if len(same) <= FULL:
            for n in same:
                if n not in shown:
                    shown.add(n)
                    print_card(db, db.by_name[norm(n)], f"  (also matches \"{q}\")")
        else:
            print(f"\n  Other cards named \"{q}, ...\":")
            print_names(db, same)

    for q in a.rule:
        q = q.rstrip(".")
        hits = [(n, t) for n, t in rules if cr.in_scope(n, q)]
        cap = a.max or 60
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

    # The model reads this right before it decides what to do next (see SKILL.md, steps 5-7).
    print("\n## NEXT\n"
          "Write answer.json, then reply with the short answer and the confidence level, and end your turn.\n"
          "Don't run build.py and don't build a page or an artifact: the link comes only if the person\n"
          "then asks for it.")


if __name__ == "__main__":
    main()
