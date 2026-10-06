#!/usr/bin/env python3
"""Publish the Comprehensive Rules as small JSON files for the hosted viewer.

The viewer (docs/, served by GitHub Pages) renders answers whose link carries only
rule *numbers*; it fetches the rule text from here. The workflow runs this right after
tools/update.py changed anything, so the site's rules are always the plugin's rules.

  python3 tools/build_site_data.py           write docs/data/meta.json and docs/data/rules/<SSS>.json

Output is deterministic (sorted keys, no timestamps): unchanged data produces no diff.
Standard library only.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SKILL = os.path.join(ROOT, "plugins", "mtg-rules-judge", "skills", "mtg-rules-judge")
RULES_TXT = os.path.join(SKILL, "references", "MagicCompRules.txt")
DATA_DIR = os.path.join(ROOT, "docs", "data")

sys.path.insert(0, os.path.join(SKILL, "scripts"))
sys.path.insert(0, HERE)
import rules as cr  # noqa: E402
from update import bundled_cards_meta, parse_effective  # noqa: E402

SECTION_RE = re.compile(r"^\d{3}$")
RULE_RE = re.compile(r"^(\d{3})\.\d+[a-z]*$")


def build_sections(rule_entries):
    """[(number, text)] from rules.parse_rules -> {"702": {"id", "title", "rules": {num: text}}}"""
    sections = {}

    def sec(num):
        return sections.setdefault(num, {"id": num, "title": "", "rules": {}})

    for num, text in rule_entries:
        if SECTION_RE.match(num):
            sec(num)["title"] = text
        else:
            m = RULE_RE.match(num)
            if m:
                sec(m.group(1))["rules"][num] = text
    return sections


def effective(header_lines):
    line = next((l.strip() for l in header_lines[:40] if "effective" in l.lower()), "")
    text = re.sub(r"(?i).*effective as of\s*", "", line).rstrip(".")
    date = parse_effective(line)
    return text, (date.isoformat() if date else None)


def dump(path, obj):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        f.write("\n")


def main():
    lines = cr.load(RULES_TXT)
    header, body, _ = cr.split_parts(lines)
    entries = cr.parse_rules(body)
    sections = build_sections(entries)
    chapters = {num: text for num, text in entries if re.fullmatch(r"\d", num)}
    cr_text, cr_iso = effective(header)

    rules_dir = os.path.join(DATA_DIR, "rules")
    os.makedirs(rules_dir, exist_ok=True)
    for name in os.listdir(rules_dir):  # drop sections that no longer exist
        if name.endswith(".json") and name[:-5] not in sections:
            os.remove(os.path.join(rules_dir, name))
    for num, s in sections.items():
        dump(os.path.join(rules_dir, num + ".json"), s)

    meta = {
        "crEffectiveDate": cr_text,
        "crEffectiveIso": cr_iso,
        "cardDataDate": bundled_cards_meta().get("built"),
        "chapters": chapters,
        "sections": sorted(sections),
        "ruleCount": sum(len(s["rules"]) for s in sections.values()),
    }
    dump(os.path.join(DATA_DIR, "meta.json"), meta)
    print(f"docs/data: {len(sections)} sections, {meta['ruleCount']} rules, CR {cr_text}, cards {meta['cardDataDate']}")


if __name__ == "__main__":
    main()
