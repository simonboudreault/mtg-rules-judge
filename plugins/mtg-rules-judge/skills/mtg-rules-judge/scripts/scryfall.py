#!/usr/bin/env python3
"""Fetch Oracle data and rulings from the Scryfall API.

Usage:
  scryfall.py card "Card Name"            English name (fuzzy match)
  scryfall.py card "Nom de carte" --lang fr   non-English printed name
  scryfall.py rulings "Card Name"

If this script cannot reach api.scryfall.com (sandbox network policy), it says
so; fall back to WebFetch on the same URLs as described in SKILL.md.
"""
import json
import sys
import time
import urllib.parse
import urllib.request

API = "https://api.scryfall.com"
HEADERS = {"User-Agent": "mtg-rules-judge-skill/1.0", "Accept": "application/json"}


def get(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def find_card(name, lang=None):
    if lang and lang != "en":
        q = f'lang:{lang} "{name}"'
        data = get(f"{API}/cards/search?include_multilingual=true&q={urllib.parse.quote(q)}")
        oracle_id = data["data"][0]["oracle_id"]
        time.sleep(0.1)
        data = get(f"{API}/cards/search?q={urllib.parse.quote('oracleid:' + oracle_id)}")
        return data["data"][0]
    return get(f"{API}/cards/named?fuzzy={urllib.parse.quote(name)}")


def print_card(c):
    faces = c.get("card_faces") or [c]
    print(f"Name: {c['name']}")
    for f in faces:
        if len(faces) > 1:
            print(f"--- Face: {f.get('name')}")
        for key in ("mana_cost", "type_line", "oracle_text", "power", "toughness", "loyalty", "defense"):
            if f.get(key) not in (None, ""):
                print(f"{key}: {f[key]}")
    for key in ("keywords", "produced_mana", "color_identity"):
        if c.get(key):
            print(f"{key}: {c[key]}")
    leg = c.get("legalities", {})
    print("legal in: " + ", ".join(k for k, v in leg.items() if v == "legal"))
    print(f"scryfall_uri: {c.get('scryfall_uri')}")
    print(f"rulings_uri: {c.get('rulings_uri')}")


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    cmd, name = sys.argv[1], sys.argv[2]
    lang = sys.argv[sys.argv.index("--lang") + 1] if "--lang" in sys.argv else None
    try:
        card = find_card(name, lang)
        if cmd == "card":
            print_card(card)
        elif cmd == "rulings":
            time.sleep(0.1)
            rulings = get(card["rulings_uri"])["data"]
            print(f"Rulings for {card['name']} ({len(rulings)}):")
            for r in rulings:
                src = "Official (WotC/Gatherer)" if r["source"] == "wotc" else "Scryfall note"
                print(f"- [{r['published_at']}] [{src}] {r['comment']}")
        else:
            sys.exit(__doc__)
    except urllib.error.HTTPError as e:
        sys.exit(f"Scryfall returned HTTP {e.code} for '{name}' (card not found or ambiguous).")
    except Exception as e:  # network blocked, DNS, proxy...
        sys.exit(f"NETWORK_UNAVAILABLE: {e}. Use WebFetch on the Scryfall API URLs instead (see SKILL.md).")


if __name__ == "__main__":
    main()
