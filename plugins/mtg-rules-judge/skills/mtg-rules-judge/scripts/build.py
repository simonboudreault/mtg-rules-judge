#!/usr/bin/env python3
"""Turn a compact answer JSON (prose + ids) into the finished answer page.

  build.py answer.json [-o answer.html] [--json answer.data.json] [--force]

You write only the prose and the ids; this script fills in, verbatim:
  - card Oracle text, mana cost, type, P/T, colours, Scryfall link and image (from the card DB)
  - Comprehensive Rules text for every rule id (from references/MagicCompRules.txt)
  - ruling text for every ruling id (from the card DB)
  - crEffectiveDate, generatedAt, allCardsLink, the default Reddit link block
Anything referenced inline ([[card:..]], [[rule:..]], [[ruling:..]]) is added automatically,
so the "cards", "rules" and "rulings" lists only need extras you want shown.
The page is rendered to static HTML here (scripts/render.py), so it shows as soon as it
loads; the resolved data is also embedded in it as JSON (id="answer-data"), and --json
writes the same data to a file, for any other renderer such as a hosted viewer.
Every reference is checked; if one can't be resolved the script lists them all
and writes nothing (use --force to write anyway). See references/answer-schema.md.
"""
import argparse
import datetime
import json
import os
import re
import sys
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rules as cr  # noqa: E402
from carddb import CardDB, slug, to_template_card  # noqa: E402
from render import render_page  # noqa: E402
import share  # noqa: E402

TEMPLATE = os.path.join(HERE, "..", "assets", "answer-template.html")
REF_RE = re.compile(r"\[\[(card|rule|ruling):([^\]|]+)(?:\|[^\]]+)?\]\]")
TEXT = {
    "en": "Not searched for this answer — the official sources settle it. Community threads, if you want them:",
    "fr": "Pas cherché pour cette réponse — les sources officielles tranchent. Les fils de la communauté, si vous voulez :",
}


def strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from strings(v)


def rule_key(rid):
    m = re.match(r"(\d+)(?:\.(\d+)([a-z]*))?", rid)
    return (int(m.group(1)), int(m.group(2) or 0), m.group(3) or "") if m else (9999, 0, rid)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("answer")
    ap.add_argument("-o", "--out", default="answer.html")
    ap.add_argument("--json", help="also write the resolved answer data to this file")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-link", action="store_true", help="no hosted-viewer link: neither printed nor in the page")
    a = ap.parse_args()

    src = json.load(open(a.answer, encoding="utf-8"))
    errors, warnings = [], []
    db = CardDB()
    db_source = f"Scryfall bulk data, {db.meta.get('built')}" if db.loaded else "Scryfall API"

    lines = cr.load(os.environ.get("MTG_CR_PATH", cr.DEFAULT_PATH))
    header, body, _ = cr.split_parts(lines)
    rule_text = {n: t for n, t in cr.parse_rules(body)}
    eff = next((l.strip() for l in header[:40] if "effective" in l.lower()), "")
    eff = re.sub(r"(?i).*effective as of\s*", "", eff).rstrip(".") or "?"

    prose = {k: v for k, v in src.items() if k not in ("cards", "rules", "rulings")}
    refs = {"card": [], "rule": [], "ruling": []}
    for s in strings(prose):
        for kind, key in REF_RE.findall(s):
            if key.strip() not in refs[kind]:
                refs[kind].append(key.strip())

    # ---- cards ----
    cards, seen = [], set()

    def add_card(entry):
        full = isinstance(entry, dict) and (entry.get("oracleText") is not None or entry.get("faces"))
        if full:
            c = dict(entry)  # full object (web fallback): pass through
            c.setdefault("id", slug(c["name"]))
            c.setdefault("source", "web (see confidence notes)")
        else:
            name = entry if isinstance(entry, str) else entry.get("name", "")
            rec, how, alts = db.find(name)
            if rec is None:
                errors.append(f"card '{name}' not in the card DB" + (f" (close: {', '.join(alts)})" if alts else "")
                              + " — look it up by its exact name, or pass a full card object")
                return None
            if how not in ("exact", "face name"):
                warnings.append(f"card '{name}' resolved to '{rec['n']}' ({how})")
            c = to_template_card(rec, db_source)
            if isinstance(entry, dict):
                c.update({k: v for k, v in entry.items() if k != "name"})
            c["_rec"] = rec
        if c["id"] not in seen:
            seen.add(c["id"])
            cards.append(c)
        return c

    for entry in src.get("cards", []):
        add_card(entry)
    by_key, renames = {}, {}
    for c in cards:
        by_key[c["id"]] = by_key[slug(c["name"])] = c
    for key in refs["card"]:
        if key in by_key or slug(key) in by_key:
            continue
        c = add_card(key)
        if c:
            by_key[c["id"]] = by_key[slug(c["name"])] = by_key[slug(key)] = c
            if slug(key) != c["id"]:  # French or face name: point the inline ref at the real card
                renames[key] = c["name"]

    # ---- rulings ----
    available = {}
    for c in cards:
        if "_rec" in c:
            for r in db.rulings_for(c["_rec"]):
                available[r["id"]] = r
    wanted, rulings = [], []
    for entry in list(src.get("rulings", [])) + refs["ruling"]:
        if isinstance(entry, dict):
            rulings.append(dict(entry, custom=True))  # hand-written: travels in full in the share link
            continue
        if entry.endswith("-*") or entry.endswith(":all"):
            base = entry[:-2] if entry.endswith("-*") else slug(entry[:-4])
            ids = [rid for rid in available if rid.rsplit("-", 1)[0] == base]
            if not ids:
                errors.append(f"no rulings found for '{entry}'")
            wanted += [i for i in ids if i not in wanted]
        elif entry in available:
            if entry not in wanted:
                wanted.append(entry)
        elif not any(isinstance(r, dict) and r.get("id") == entry for r in src.get("rulings", [])):
            errors.append(f"ruling id '{entry}' not found (ids come from lookup.py output, e.g. ruby-medallion-1)")
    order = list(available)
    rulings = sorted((available[i] for i in wanted), key=lambda r: order.index(r["id"])) + rulings

    # ---- rules ----
    rule_ids = []
    for rid in list(src.get("rules", [])) + refs["rule"]:
        rid = (rid["id"] if isinstance(rid, dict) else rid).rstrip(".")
        if rid not in rule_ids:
            rule_ids.append(rid)
    rules_out = []
    for rid in sorted(rule_ids, key=rule_key):
        if rid in rule_text:
            rules_out.append({"id": rid, "text": rule_text[rid]})
        else:
            errors.append(f"rule '{rid}' not in the bundled Comprehensive Rules (use exact subrule numbers)")

    # ---- assemble ----
    for c in cards:
        c.pop("_rec", None)
    names = [c["name"] for c in cards]
    def rewrite(obj):
        if isinstance(obj, str):
            return REF_RE.sub(lambda m: m.group(0).replace(m.group(2), renames.get(m.group(2).strip(), m.group(2)), 1), obj)
        if isinstance(obj, dict):
            return {k: rewrite(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [rewrite(v) for v in obj]
        return obj

    out = rewrite(prose) if renames else dict(prose)
    out.setdefault("lang", "en")
    out["schemaVersion"] = 1
    out.setdefault("generatedAt", datetime.date.today().isoformat())
    out["crEffectiveDate"] = eff
    if db.loaded:
        out["cardDataDate"] = db.meta.get("built")
    out["cards"], out["rules"], out["rulings"] = cards, rules_out, rulings
    if names:
        q = " or ".join(f'!"{n}"' for n in names)
        out["allCardsLink"] = "https://scryfall.com/search?q=" + urllib.parse.quote_plus(q) + "&unique=cards"
    if "reddit" not in src:
        q = " ".join(f'"{n}"' for n in names[:3])
        out["reddit"] = {"searched": False, "threads": [], "overview": TEXT.get(out["lang"], TEXT["en"]),
                         "agreesWithOfficial": "unknown",
                         "searchUrl": "https://www.reddit.com/r/mtgrules/search/?q=" + urllib.parse.quote_plus(q)}
    elif src["reddit"] is False:
        out.pop("reddit")

    for w in warnings:
        print("warning:", w)
    if errors:
        print("\n".join("ERROR: " + e for e in errors))
        if not a.force:
            sys.exit("Nothing written. Fix the ids above (or --force to write with missing references).")

    if a.json:  # the same resolved data, on its own (e.g. for a hosted viewer)
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
    url, url_len = (None, 0) if a.no_link else share.make_link(share.to_share_payload(out),
                                                                max_chars=share.EMBED_MAX_CHARS)
    page = render_page(out, open(TEMPLATE, encoding="utf-8").read(), share_url=url)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"Wrote {a.out} ({len(page.encode()) // 1024} KB): {len(cards)} card(s), {len(rules_out)} rule(s), "
          f"{len(rulings)} ruling(s), CR {eff}." + (f" Data: {a.json}." if a.json else "")
          + " Don't publish or paste it; the link below is what the person gets.")
    if url_len:  # 0 = no viewer URL configured, or --no-link
        print(f"Link: {url}" if url and url_len <= share.link_max() else
              f"Link: omitted, URL would be {url_len} chars (cap {share.link_max()}); say so in the reply.")

if __name__ == "__main__":
    main()
