#!/usr/bin/env python3
"""Look up the Magic: The Gathering Comprehensive Rules bundled with this skill.

Usage:
  rules.py info                     effective date of the bundled rules
  rules.py rule 702.19              a rule with all its subrules (702.19, 702.19a, ...)
  rules.py rule 702.19c             a single subrule
  rules.py rule 613 --max 120       a whole section (capped at --max lines)
  rules.py search trample damage    rules containing ALL the words (case-insensitive)
  rules.py search "dies" --regex    regex search
  rules.py glossary trample         glossary entries whose term matches
  rules.py toc                      list of sections

Output is the verbatim rule text so it can be quoted directly.
"""
import argparse
import signal
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PATH = os.path.join(HERE, "..", "references", "MagicCompRules.txt")

RULE_RE = re.compile(r"^(\d{3}\.\d+[a-z]*)\.?\s+(.*)$")
SECTION_RE = re.compile(r"^(\d{3})\.\s+(.+)$")
CHAPTER_RE = re.compile(r"^(\d)\.\s+(.+)$")


def _repair_mojibake(text):
    """Wizards' TXT often arrives double-encoded (UTF-8 bytes read as cp1252, then
    saved as UTF-8 again), showing up as â€™ for ’ and Â\xa0 for a non-breaking
    space. Reverse that when the symptoms are present."""
    if "â€" not in text and "Â\xa0" not in text and "Â " not in text:
        return text
    # a mojibaked non-breaking space is "Â" + (nbsp or plain space); make it a plain space
    text = text.replace("Â\xa0", " ").replace("Â ", " ")
    out = bytearray()
    for ch in text:
        try:
            out += ch.encode("cp1252")
        except UnicodeEncodeError:
            o = ord(ch)
            out += bytes([o]) if o < 256 else ch.encode("utf-8")
    try:
        return out.decode("utf-8")
    except UnicodeDecodeError:
        return out.decode("utf-8", errors="replace")


def load(path):
    raw = open(path, "rb").read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")
    text = _repair_mojibake(text)
    # Wizards indents example paragraphs with non-breaking spaces; make them plain spaces
    text = text.replace("\xa0", " ")
    # U+2028 (line separator) is used inside glossary entries; treat it as a newline
    text = text.replace(" ", "\n").replace("\r\n", "\n").replace("\r", "\n")
    return [l.rstrip() for l in text.split("\n")]


def split_parts(lines):
    """Return (header_lines, rule_lines, glossary_lines).

    The file opens with a table of contents that repeats the chapter titles,
    "Glossary" and "Credits", so the real body starts at the LAST occurrence
    of the first chapter title before the glossary.
    """
    glossary_idx = [i for i, l in enumerate(lines) if l.strip() == "Glossary"]
    credits_idx = [i for i, l in enumerate(lines) if l.strip() == "Credits"]
    g_start = glossary_idx[-1] if glossary_idx else len(lines)
    c_start = credits_idx[-1] if credits_idx and credits_idx[-1] > g_start else len(lines)
    first_chapter = [i for i, l in enumerate(lines[:g_start]) if CHAPTER_RE.match(l.strip()) and l.strip().startswith("1.")]
    body_start = first_chapter[-1] if first_chapter else 0
    return lines[:body_start], lines[body_start:g_start], lines[g_start + 1:c_start]


def parse_rules(rule_lines):
    """Ordered list of (number, text) where text includes following Example lines."""
    rules = []
    for raw in rule_lines:
        line = raw.strip()
        if not line:
            continue
        m = RULE_RE.match(line)
        if m:
            rules.append([m.group(1), m.group(2)])
            continue
        s = SECTION_RE.match(line)
        if s:
            rules.append([s.group(1), s.group(2)])
            continue
        if CHAPTER_RE.match(line):
            rules.append([line.split(".")[0], line.split(".", 1)[1].strip()])
            continue
        if rules:  # Example: lines and continuations
            rules[-1][1] += "\n    " + line
    return rules


def parse_glossary(g_lines):
    entries, cur = [], []
    for raw in g_lines + [""]:
        if raw.strip():
            cur.append(raw.strip())
        elif cur:
            entries.append((cur[0], "\n".join(cur[1:])))
            cur = []
    return entries


def fmt(num, text):
    return f"{num}{'.' if re.fullmatch(r'[0-9.]*[0-9]', num) else ''} {text}"


def in_scope(num, query):
    if num == query:
        return True
    if re.fullmatch(r"\d{3}", query):          # section: 702 -> 702.x
        return num.startswith(query + ".")
    if re.fullmatch(r"\d{3}\.\d+", query):     # rule: 702.19 -> 702.19a, not 702.190
        return re.fullmatch(re.escape(query) + r"[a-z]+", num) is not None
    return False


def main():
    try:
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["info", "rule", "search", "glossary", "toc"])
    ap.add_argument("terms", nargs="*")
    ap.add_argument("--file", default=os.environ.get("MTG_CR_PATH", DEFAULT_PATH))
    ap.add_argument("--max", type=int, default=80, help="max rules to print")
    ap.add_argument("--regex", action="store_true")
    a = ap.parse_args()

    if not os.path.exists(a.file):
        sys.exit(f"Comprehensive Rules file not found at {a.file}")
    lines = load(a.file)
    header, body, gloss = split_parts(lines)
    rules = parse_rules(body)

    if a.command == "info":
        for l in header[:40]:
            if "effective" in l.lower():
                print(l.strip())
                break
        print(f"{len(rules)} rule entries, {len(parse_glossary(gloss))} glossary entries")
        return

    if a.command == "toc":
        for num, text in rules:
            if re.fullmatch(r"\d|\d{3}", num):
                print(("" if len(num) == 1 else "  ") + f"{num}. {text}")
        return

    if a.command == "rule":
        if not a.terms:
            sys.exit("give one or more rule numbers, e.g. rule 702.19")
        for q in a.terms:
            q = q.rstrip(".")
            hits = [(n, t) for n, t in rules if in_scope(n, q)]
            if not hits:
                print(f"[no rule {q} in the bundled Comprehensive Rules]")
            for n, t in hits[: a.max]:
                print(fmt(n, t))
            if len(hits) > a.max:
                print(f"[... {len(hits) - a.max} more; narrow the number or raise --max]")
            print()
        return

    if a.command == "search":
        if not a.terms:
            sys.exit("give search words")
        if a.regex:
            pat = re.compile(" ".join(a.terms), re.I)
            match = lambda t: pat.search(t)
        else:
            words = [w.lower() for w in a.terms]
            match = lambda t: all(w in t.lower() for w in words)
        hits = [(n, t) for n, t in rules if match(t)]
        for n, t in hits[: a.max]:
            first = t.split("\n")[0]
            print(fmt(n, first if len(first) < 300 else first[:300] + " [...]"))
        print(f"[{len(hits)} match(es){'; showing ' + str(a.max) if len(hits) > a.max else ''}]")
        return

    if a.command == "glossary":
        q = " ".join(a.terms).lower()
        entries = parse_glossary(gloss)
        exact = [e for e in entries if e[0].lower() == q]
        hits = exact or [e for e in entries if q in e[0].lower()]
        for term, defn in hits[: a.max]:
            print(f"{term}\n{defn}\n")
        if not hits:
            print(f"[no glossary term matching '{q}']")


if __name__ == "__main__":
    main()
