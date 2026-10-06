#!/usr/bin/env python3
"""Make the shareable link for an answer: the hosted viewer renders it from the URL alone.

  share.py resolved.json [--base URL] [--payload OUT.json] [--fragment OUT.txt]

build.py prints the link (and puts it in the page's share bar), so normally you never
run this.
The link carries the "share payload": the prose Claude wrote plus identifiers (card
oracle ids, rule numbers, ruling ids with a hash of their text). It is written as
<site>#2.<readable text>, which Claude can type quickly, or, for a payload that form
can't carry, as <site>#1.<base64url(zlib(json))>. The site fetches the rule text from the plugin's own data feed
(docs/data) and card text, images and rulings from Scryfall. Cards that came from the
web fallback (no oracleId) travel in full. See references/share-payload.md.

Nothing is sent anywhere: the fragment never leaves the browser, so this works from a
sandbox with no network. Standard library only.
"""
import argparse
import base64
import hashlib
import json
import os
import re
import sys
import unicodedata
import zlib

DEFAULT_SITE_URL = "https://simonboudreault.github.io/mtg-rules-judge/"  # $MTG_JUDGE_SITE overrides; empty = print no link
ENCODING_VERSION = "1"   # compressed: base64url(zlib(json)); short, but slow for Claude to type
READABLE_VERSION = "2"   # readable: the prose as words; longer, typed about five times faster
PAYLOAD_VERSION = 1
LINK_MAX_CHARS = 3000      # cap for a compressed link (about a minute of typing)
READABLE_MAX_CHARS = 8000  # cap for a readable link (about half a minute)


def site_url():
    url = (os.environ.get("MTG_JUDGE_SITE") or DEFAULT_SITE_URL).strip()
    return url.rstrip("/") + "/" if url else ""


def link_max(default=LINK_MAX_CHARS):
    try:
        return int(os.environ.get("MTG_JUDGE_LINK_MAX") or default)
    except ValueError:
        return default


# ---------- hashes (the viewer computes the same; see share-payload.md) ----------

def _h8(text):
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]


def card_canon(card):
    faces = card.get("faces")
    if faces:
        return "\n//\n".join(f.get("oracleText") or "" for f in faces)
    return card.get("oracleText") or ""


def card_hash(card):
    return _h8(card_canon(card))


def ruling_hash(text):
    return _h8(text or "")


# ---------- payload ----------

def is_default_reddit(r):
    return bool(r) and r.get("searched") is False and not r.get("threads") and not r.get("opinions")


def to_share_payload(resolved):
    """Resolved answer data (build.py output) -> share payload (ids instead of text)."""
    p = {"v": PAYLOAD_VERSION, "lang": resolved.get("lang") or "en"}
    for k in ("title", "question", "shortAnswer", "confidence", "steps"):
        if resolved.get(k) is not None:
            p[k] = resolved[k]
    if "reddit" not in resolved:
        p["reddit"] = False           # the section was hidden
    elif not is_default_reddit(resolved["reddit"]):
        p["reddit"] = resolved["reddit"]  # a real search; the default block is rebuilt by the site
    p["cr"] = resolved.get("crEffectiveDate")
    p["at"] = resolved.get("generatedAt")
    p["db"] = resolved.get("cardDataDate")

    cards, external = [], set()
    for c in resolved.get("cards") or []:
        if c.get("oracleId"):
            s = {"id": c["id"], "name": c["name"], "oid": c["oracleId"], "h": card_hash(c)}
            if c.get("note"):
                s["note"] = c["note"]
            cards.append(s)
        else:  # web fallback: the viewer can't look it up, so it travels in full
            external.add(c["id"])
            cards.append({k: v for k, v in c.items() if k not in ("imageUrl", "scryfallUri", "imageDataUri")})
    p["cards"] = cards
    p["rules"] = [r["id"] for r in resolved.get("rules") or []]

    rulings = []
    for r in resolved.get("rulings") or []:
        if r.get("custom") or r.get("card") in external:
            rulings.append({k: r[k] for k in ("id", "card", "date", "source", "text") if k in r})
        else:
            rulings.append({"id": r["id"], "card": r.get("card"), "d": r.get("date"), "h": ruling_hash(r.get("text"))})
    p["rulings"] = rulings
    return p


# ---------- encoding ----------

def encode_fragment(payload):
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    b64 = base64.urlsafe_b64encode(zlib.compress(raw, 9)).decode("ascii").rstrip("=")
    return f"{ENCODING_VERSION}.{b64}"


def decode_compressed(fragment):
    """Inverse of encode_fragment; raises ValueError on a damaged or unknown fragment."""
    frag = fragment.lstrip("#")
    version, _, b64 = frag.partition(".")
    if version != ENCODING_VERSION or not b64:
        raise ValueError(f"unknown link format '{version}'")
    try:
        raw = zlib.decompress(base64.urlsafe_b64decode(b64 + "=" * (-len(b64) % 4)))
        return json.loads(raw.decode("utf-8"))
    except Exception as e:  # binascii.Error, zlib.error, UnicodeDecodeError, json errors
        raise ValueError(f"damaged link: {e}") from e


def decode_fragment(fragment):
    """Payload from either link format; raises ValueError on a damaged or unknown fragment."""
    frag = fragment.lstrip("#")
    if frag.startswith(READABLE_VERSION + "."):
        return decode_readable(frag)
    return decode_compressed(frag)


# ---------- readable encoding (format 2) ----------
# Claude types the link into the reply by hand. Compressed text is random characters, which
# it copies at about 50 characters a second; ordinary words go about five times faster. So
# the link Claude types carries the prose as words: "+" for a space, "!x" codes for anything
# a chat app could mangle inside a URL, "=<letter>" in front of each field. See share-payload.md.

_CODES = [  # literal -> the character after "!"; multi-character literals first
    ("[[rule:", "r"), ("[[card:", "c"), ("[[ruling:", "g"), ("[[link:", "l"), ("]]", "z"), ("[[", "y"),
    ("**", "b"), ("*", "i"), ("(", "p"), (")", "P"), ("'", "a"), ("’", "A"), ('"', "q"),
    ("{", "m"), ("}", "M"), ("+", "t"), ("=", "e"), ("!", "x"), ("?", "w"), ("\n", "N"),
    (" ", "s"), (" ", "S"), ("«", "d"), ("»", "D"), ("—", "k"), ("–", "K"),
    ("…", "E"),
]
_DECODE = {code: lit for lit, code in _CODES}
_RAW = set("-.,:;/")
_SLIM_CARD = {"id", "name", "oid", "h", "note"}
_RULING_REF = {"id", "card", "d", "h"}
_CONF_LISTS = (("reasons", "r"), ("assumptions", "u"), ("notRetrieved", "n"))
_PLAIN = re.compile(r"[A-Za-z0-9.-]*\Z")  # ids, dates and hashes: written as they are


def _esc(text):
    out, i, n = [], 0, len(text)
    while i < n:
        for lit, code in _CODES:
            if text.startswith(lit, i):
                out.append("!" + code)
                i += len(lit)
                break
        else:
            ch = text[i]
            i += 1
            if ch == " ":
                out.append("+")
            elif ch == "." and text.startswith(".", i):  # ".." ends a link in some chat apps
                out.append("!u2e;")
            elif ch.isalnum() or ch in _RAW:  # letters and digits of any language stay as they are
                out.append(ch)
            else:
                out.append(f"!u{ord(ch):x};")
    return "".join(out)


def _unesc(s):
    out, i, n = [], 0, len(s)
    while i < n:
        ch = s[i]
        if ch == "+":
            out.append(" ")
            i += 1
        elif ch != "!":
            out.append(ch)
            i += 1
        elif s.startswith("u", i + 1):
            j = s.index(";", i + 2)  # ValueError when missing
            out.append(chr(int(s[i + 2:j], 16)))
            i = j + 1
        else:
            code = s[i + 1:i + 2]
            if code not in _DECODE:
                raise ValueError(f"unknown code '!{code}'")
            out.append(_DECODE[code])
            i += 2
    return "".join(out)


def _check(head):
    """4 hex digits over everything before "=z": tells the viewer when a character was changed."""
    return format(zlib.crc32(unicodedata.normalize("NFC", head).encode("utf-8")) & 0xFFFF, "04x")


def _blob(obj):
    raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(zlib.compress(raw, 9)).decode("ascii").rstrip("=").replace("_", ".")


def _unblob(s):
    b64 = s.replace(".", "_")
    return json.loads(zlib.decompress(base64.urlsafe_b64decode(b64 + "=" * (-len(b64) % 4))).decode("utf-8"))


def canon(payload):
    """A payload with its optional parts normalised, so two payloads that draw the same page compare equal."""
    p = {k: v for k, v in payload.items() if v is not None}
    for key in ("steps", "cards", "rules", "rulings"):
        p.setdefault(key, [])
    if isinstance(p.get("confidence"), dict):
        p["confidence"] = dict(p["confidence"], **{k: p["confidence"].get(k) or [] for k, _ in _CONF_LISTS})
    if isinstance(p.get("steps"), list):
        p["steps"] = [{k: v for k, v in s.items() if k != "note" or v} if isinstance(s, dict) else s
                      for s in p["steps"]]
    return p


def _readable(payload):
    el = []  # (tag, already-escaped value)

    def text(tag, v):
        el.append((tag, _esc(v)))

    for key, tag in (("title", "t"), ("question", "q"), ("shortAnswer", "a")):
        if payload.get(key) is not None:
            text(tag, payload[key])
    conf = payload.get("confidence")
    if conf is not None:
        if conf.get("level") is not None:
            text("c", conf["level"])
        for key, tag in _CONF_LISTS:
            for item in conf.get(key) or []:
                text(tag, item)
    for step in payload.get("steps") or []:
        text("s", step.get("text") or "")
        if step.get("note"):
            text("o", step["note"])

    extra = {}  # what has no readable form: travels compressed in "=x"
    cards = payload.get("cards") or []
    for i, c in enumerate(cards):
        if c.get("oid") and c.get("h") and set(c) <= _SLIM_CARD and _PLAIN.match(c["oid"] + c["h"]):
            text("k", c["name"])
            el.append(("i", c["oid"]))
            el.append(("h", c["h"]))
            if c.get("note"):
                text("m", c["note"])
            if c.get("id") != _slug(c["name"]):
                text("j", c["id"])
        else:
            extra.setdefault("cards", []).append([i, c])
    if payload.get("rules"):
        el.append(("l", ",".join(_esc(r) for r in payload["rules"])))
    slim_ids = [c["id"] for c in cards if not any(c is x for _, x in extra.get("cards", []))]
    last_date = None
    for i, r in enumerate(payload.get("rulings") or []):
        fields = [r.get("id"), r.get("d"), r.get("h")]
        if set(r) == _RULING_REF and all(isinstance(f, str) and f and _PLAIN.match(f) for f in fields + [r["card"]]):
            base, _, num = r["id"].rpartition("-")
            if r["card"] != base:
                fields.append(r["card"])
            elif num.isdigit() and base in slim_ids:
                fields[0] = f"{slim_ids.index(base) + 1}-{num}"  # "<card position>-<n>" for the full id
            if fields[1] == last_date:
                fields[1] = ""  # same date as the ruling before
            last_date = r["d"]
            el.append(("g", ",".join(fields)))
        else:
            extra.setdefault("rulings", []).append([i, r])
    for key, tag in (("cr", "d"), ("at", "e"), ("db", "f")):
        if payload.get(key) is not None:
            text(tag, payload[key])
    if payload.get("reddit") is False:
        el.append(("y", "0"))
    elif "reddit" in payload:
        extra["reddit"] = payload["reddit"]
    if extra:
        el.append(("x", _blob(extra)))
    head = READABLE_VERSION + "." + _esc(payload.get("lang") or "en") + "".join(f"={t}{v}" for t, v in el)
    return head + "=z" + _check(head)


def _slug(s):  # carddb.slug, repeated here so this file stays standard-library only
    return re.sub(r"(^-|-$)", "", re.sub(r"[^a-z0-9]+", "-", str(s).lower()))


def encode_readable(payload):
    """The "2.…" fragment, or None when this payload can't be carried exactly in that form."""
    try:
        frag = _readable(payload)
        return frag if canon(decode_readable(frag)) == canon(payload) else None
    except Exception:  # an unexpected shape (a number where text belongs...): the compressed form takes it
        return None


def decode_readable(fragment):
    """Inverse of encode_readable; raises ValueError on a damaged fragment."""
    frag = fragment.lstrip("#")
    head, sep, check = frag.rpartition("=z")
    if not sep or not frag.startswith(READABLE_VERSION + ".") or check != _check(head):
        raise ValueError("damaged link: checksum")
    try:
        lang, *parts = head[len(READABLE_VERSION) + 1:].split("=")
        p = {"v": PAYLOAD_VERSION, "lang": _unesc(lang), "steps": [], "cards": [], "rules": [], "rulings": []}
        lists = {tag: key for key, tag in _CONF_LISTS}

        def conf():
            return p.setdefault("confidence", {k: [] for k, _ in _CONF_LISTS})

        extra = {}
        for part in parts:
            tag, v = part[:1], part[1:]
            if tag in "tqa":
                p[{"t": "title", "q": "question", "a": "shortAnswer"}[tag]] = _unesc(v)
            elif tag == "c":
                conf()["level"] = _unesc(v)
            elif tag in lists:
                conf()[lists[tag]].append(_unesc(v))
            elif tag == "s":
                p["steps"].append({"text": _unesc(v)})
            elif tag == "o":
                p["steps"][-1]["note"] = _unesc(v)
            elif tag == "k":
                name = _unesc(v)
                p["cards"].append({"id": _slug(name), "name": name})
            elif tag in "ihmj":
                p["cards"][-1][{"i": "oid", "h": "h", "m": "note", "j": "id"}[tag]] = v if tag in "ih" else _unesc(v)
            elif tag == "l":
                p["rules"] = [_unesc(x) for x in v.split(",")] if v else []
            elif tag == "g":
                p["rulings"].append(v.split(","))
            elif tag in "def":
                p[{"d": "cr", "e": "at", "f": "db"}[tag]] = _unesc(v)
            elif tag == "y":
                p["reddit"] = False
            elif tag == "x":
                extra = _unblob(v)
            # any other tag: written by a newer version, ignored
        ids = [c["id"] for c in p["cards"]]
        last_date = None
        for n, f in enumerate(p["rulings"]):
            rid, d, h = f[0], f[1] or last_date, f[2]
            last_date = d
            pos, _, num = rid.partition("-")
            if pos.isdigit() and num.isdigit():
                card = ids[int(pos) - 1]
                rid = f"{card}-{num}"
            else:
                card = f[3] if len(f) > 3 else rid.rpartition("-")[0]
            p["rulings"][n] = {"id": rid, "card": card, "d": d, "h": h}
        for key in ("cards", "rulings"):
            for i, obj in extra.get(key) or []:
                p[key].insert(i, obj)
        if "reddit" in extra:
            p["reddit"] = extra["reddit"]
        return p
    except ValueError:
        raise
    except Exception as e:  # IndexError, KeyError, zlib.error...
        raise ValueError(f"damaged link: {e}") from e


def make_link(payload, base=None, max_chars=None):
    """(url or None when over the cap, length). base defaults to site_url().

    The readable form when the payload fits it (it always should), else the compressed one;
    $MTG_JUDGE_LINK_FORMAT=1 forces the compressed one."""
    base = base if base is not None else site_url()
    if not base:
        return None, 0
    frag = None if (os.environ.get("MTG_JUDGE_LINK_FORMAT") or "").strip() == ENCODING_VERSION else encode_readable(payload)
    cap = READABLE_MAX_CHARS if frag else LINK_MAX_CHARS
    url = base.rstrip("/") + "/#" + (frag or encode_fragment(payload))
    limit = max_chars if max_chars is not None else link_max(cap)
    return (url if len(url) <= limit else None), len(url)


def link_line(resolved, base=None):
    """The line this script and build.py print. Empty when no viewer URL is configured."""
    base = base if base is not None else site_url()
    if not base:
        return ""
    url, n = make_link(to_share_payload(resolved), base)
    if url:
        return f"Link: {url}"
    return f"Link: omitted, URL would be {n} chars, too long to type; say so in the reply."


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("resolved", help="resolved answer data (build.py --json)")
    ap.add_argument("--base", help="viewer URL (default: $MTG_JUDGE_SITE or the built-in one)")
    ap.add_argument("--payload", help="also write the share payload JSON here")
    ap.add_argument("--fragment", help="also write the bare compressed fragment ('1.…') here")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    with open(a.resolved, encoding="utf-8") as f:
        resolved = json.load(f)
    payload = to_share_payload(resolved)
    if a.payload:
        with open(a.payload, "w", encoding="utf-8", newline="\n") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
            f.write("\n")
    if a.fragment:
        with open(a.fragment, "w", encoding="utf-8", newline="\n") as f:
            f.write(encode_fragment(payload) + "\n")
    base = a.base if a.base is not None else site_url()
    print(link_line(resolved, base or "https://example.invalid/"))


if __name__ == "__main__":
    sys.exit(main())
