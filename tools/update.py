#!/usr/bin/env python3
"""Keep the plugin's rules and card database current.

Run by .github/workflows/update.yml on a schedule; works from any computer with
internet too. Python 3.8+, standard library only.

  python3 tools/update.py --check            report what is stale, change nothing
  python3 tools/update.py                    update whatever is stale, bump the version
  python3 tools/update.py --force-cards      rebuild the card database regardless
  python3 tools/update.py --force-rules      re-download the Comprehensive Rules regardless

What counts as stale:

  Rules   The "effective as of" date on https://magic.wizards.com/en/rules is later
          than the one in the bundled MagicCompRules.txt.
  Cards   A real set (not tokens, promos or memorabilia) has a release date after the
          day the bundled database was built, up to today, or the database is more
          than MAX_DB_AGE_DAYS old (rulings and Oracle errata arrive between sets too).

The plugin version only changes when a file changed, because that is what tells
Claude to fetch the new copy for everyone who installed the plugin.
"""
import argparse
import datetime
import gzip
import html
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(ROOT, "plugins", "mtg-rules-judge")
SKILL = os.path.join(PLUGIN, "skills", "mtg-rules-judge")
RULES_TXT = os.path.join(SKILL, "references", "MagicCompRules.txt")
CARDS_GZ = os.path.join(SKILL, "data", "cards.json.gz")
PLUGIN_JSON = os.path.join(PLUGIN, ".claude-plugin", "plugin.json")
BUILD_CARD_DB = os.path.join(SKILL, "scripts", "build_card_db.py")

RULES_PAGE = "https://magic.wizards.com/en/rules"
SCRYFALL_SETS = "https://api.scryfall.com/sets"
HEADERS = {"User-Agent": "mtg-rules-judge-updater/1.0 (github.com/simonboudreault/mtg-rules-judge)",
           "Accept": "*/*"}
MAX_DB_AGE_DAYS = 90
# Scryfall set types that never carry new Oracle text or rulings of their own
IGNORED_SET_TYPES = {"token", "promo", "memorabilia", "minigame"}

MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], 1)}
EFFECTIVE_RE = re.compile(r"effective as of\s+([A-Z][a-z]+)\s+(\d{1,2}),\s+(\d{4})")


def fetch(url, timeout=60):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def parse_effective(text):
    """'These rules are effective as of September 25, 2026.' -> date(2026, 9, 25)"""
    m = EFFECTIVE_RE.search(text)
    if not m:
        return None
    return datetime.date(int(m.group(3)), MONTHS[m.group(1)], int(m.group(2)))


def read_text_any(raw):
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


# ---------------------------------------------------------------- rules

def bundled_rules_date():
    if not os.path.exists(RULES_TXT):
        return None
    with open(RULES_TXT, "rb") as f:
        return parse_effective(read_text_any(f.read(4000)))


def current_rules():
    """Return (effective_date, txt_url) for the rules Wizards currently publishes."""
    page = read_text_any(fetch(RULES_PAGE))
    links = re.findall(r'href="([^"]*MagicCompRules[^"]*\.txt)"', page, flags=re.I)
    if not links:
        raise RuntimeError("no MagicCompRules .txt link found on " + RULES_PAGE)
    url = html.unescape(links[0])
    url = urllib.parse.quote(url, safe=":/%?=&")  # the file name contains a space
    raw = fetch(url)
    date = parse_effective(read_text_any(raw[:4000]))
    if not date:
        raise RuntimeError("downloaded rules file has no 'effective as of' line: " + url)
    return date, url, raw


def check_rules():
    have = bundled_rules_date()
    want, url, raw = current_rules()
    stale = have is None or want > have
    return {"have": have.isoformat() if have else None, "want": want.isoformat(),
            "url": url, "stale": stale}, raw


def apply_rules(raw):
    os.makedirs(os.path.dirname(RULES_TXT), exist_ok=True)
    with open(RULES_TXT, "wb") as f:
        f.write(raw)


# ---------------------------------------------------------------- cards

def bundled_cards_meta():
    if not os.path.exists(CARDS_GZ):
        return {}
    with gzip.open(CARDS_GZ, "rt", encoding="utf-8") as f:
        # the file starts with {"meta":{...},"cards":[ — read just enough for the meta
        head = f.read(2000)
    m = re.search(r'"meta":(\{.*?\}),"cards"', head)
    return json.loads(m.group(1)) if m else {}


def sets_released_between(after, upto):
    """Real sets with after < released_at <= upto, newest first."""
    data = json.loads(fetch(SCRYFALL_SETS, timeout=30))["data"]
    out = []
    for s in data:
        rel = s.get("released_at")
        if not rel or s.get("set_type") in IGNORED_SET_TYPES or not s.get("card_count"):
            continue
        d = datetime.date.fromisoformat(rel)
        if after < d <= upto:
            out.append({"code": s["code"], "name": s["name"], "released_at": rel,
                        "set_type": s["set_type"], "cards": s["card_count"]})
    out.sort(key=lambda s: s["released_at"], reverse=True)
    return out


def check_cards(today):
    meta = bundled_cards_meta()
    built = datetime.date.fromisoformat(meta["built"]) if meta.get("built") else None
    info = {"built": built.isoformat() if built else None, "cards": meta.get("cards"),
            "new_sets": [], "age_days": (today - built).days if built else None, "stale": False, "why": None}
    if built is None:
        info.update(stale=True, why="no card database bundled")
        return info
    # On release day Scryfall usually finishes importing in the morning (UTC); the
    # workflow runs in the afternoon, so same-day releases are safe to include.
    info["new_sets"] = sets_released_between(built, today)
    if info["new_sets"]:
        info.update(stale=True, why="new set(s): " + ", ".join(f"{s['name']} ({s['code'].upper()})" for s in info["new_sets"]))
    elif info["age_days"] > MAX_DB_AGE_DAYS:
        info.update(stale=True, why=f"database is {info['age_days']} days old (limit {MAX_DB_AGE_DAYS})")
    return info


def apply_cards(french=True):
    cmd = [sys.executable, BUILD_CARD_DB, "--out", CARDS_GZ] + (["--french"] if french else [])
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


# ---------------------------------------------------------------- version

def next_version(current, today):
    """Date-based semver: 2026.1005.0, then 2026.1005.1 for a second release the same day.
    Months aren't zero-padded (semver forbids leading zeros): Jan 5 is 2026.105.0."""
    major, minor = today.year, int(f"{today.month}{today.day:02d}")
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", current or "")
    if m and int(m.group(1)) == major and int(m.group(2)) == minor:
        return f"{major}.{minor}.{int(m.group(3)) + 1}"
    return f"{major}.{minor}.0"


def bump_plugin(today, rules_date):
    with open(PLUGIN_JSON, encoding="utf-8") as f:
        pj = json.load(f)
    pj["version"] = next_version(pj.get("version"), today)
    pj["description"] = re.sub(r"\(effective [^)]*\)",
                               f"(effective {rules_date.strftime('%B')} {rules_date.day}, {rules_date.year})",
                               pj.get("description", ""))
    with open(PLUGIN_JSON, "w", encoding="utf-8") as f:
        json.dump(pj, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return pj["version"]


def github_output(**kv):
    """Expose results to later workflow steps, when running under GitHub Actions."""
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as f:
        for k, v in kv.items():
            f.write(f"{k}={v}\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="report only, change nothing")
    ap.add_argument("--force-rules", action="store_true")
    ap.add_argument("--force-cards", action="store_true")
    ap.add_argument("--no-french", action="store_true", help="skip French names (much faster build)")
    a = ap.parse_args()
    today = datetime.datetime.now(datetime.timezone.utc).date()

    rules, rules_raw = check_rules()
    cards = check_cards(today)
    print(f"Rules: bundled {rules['have']}, published {rules['want']}"
          + (" -> UPDATE" if rules["stale"] else " -> current"))
    print(f"Cards: built {cards['built']} ({cards['cards']} cards, {cards['age_days']} days old)"
          + (f" -> REBUILD: {cards['why']}" if cards["stale"] else " -> current"))

    do_rules = rules["stale"] or a.force_rules
    do_cards = cards["stale"] or a.force_cards
    if a.check:
        print(json.dumps({"rules": rules, "cards": cards}, indent=2))
        return 0
    if not (do_rules or do_cards):
        github_output(changed="false")
        return 0

    changes = []
    if do_rules:
        apply_rules(rules_raw)
        changes.append(f"Comprehensive Rules effective {rules['want']}")
    if do_cards:
        apply_cards(french=not a.no_french)
        new_meta = bundled_cards_meta()
        changes.append(f"card database rebuilt {new_meta.get('built')} ({new_meta.get('cards')} cards"
                       + (f"; {cards['why']}" if cards["why"] else "") + ")")

    version = bump_plugin(today, datetime.date.fromisoformat(rules["want"]))
    summary = "; ".join(changes)
    print(f"\nVersion {version}: {summary}")
    github_output(changed="true", version=version, summary=summary,
                  rules_date=rules["want"], cards_rebuilt=str(do_cards).lower())
    return 0


if __name__ == "__main__":
    sys.exit(main())
