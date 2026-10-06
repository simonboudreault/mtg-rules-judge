#!/usr/bin/env python3
"""Make the shareable link for an answer: the hosted viewer renders it from the URL alone.

  share.py resolved.json [--base URL] [--payload OUT.json] [--fragment OUT.txt]

build.py prints the link (and puts it in the page's share bar), so normally you never
run this.
The link is  <site>#1.<base64url(zlib(json))>  where the JSON is the "share payload":
the prose Claude wrote plus identifiers (card oracle ids, rule numbers, ruling ids with
a hash of their text). The site fetches the rule text from the plugin's own data feed
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
import sys
import zlib

DEFAULT_SITE_URL = "https://simonboudreault.github.io/mtg-rules-judge/"  # $MTG_JUDGE_SITE overrides; empty = print no link
ENCODING_VERSION = "1"
PAYLOAD_VERSION = 1
LINK_MAX_CHARS = 3000   # cap for a link printed for Claude to type into the reply (slow, error-prone)
EMBED_MAX_CHARS = 8000  # cap for the link placed in the page: nobody types it, it only has to survive a paste


def site_url():
    url = (os.environ.get("MTG_JUDGE_SITE") or DEFAULT_SITE_URL).strip()
    return url.rstrip("/") + "/" if url else ""


def link_max():
    try:
        return int(os.environ.get("MTG_JUDGE_LINK_MAX") or LINK_MAX_CHARS)
    except ValueError:
        return LINK_MAX_CHARS


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


def decode_fragment(fragment):
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


def make_link(payload, base=None, max_chars=None):
    """(url or None when over the cap, length). base defaults to site_url()."""
    base = base if base is not None else site_url()
    if not base:
        return None, 0
    url = base.rstrip("/") + "/#" + encode_fragment(payload)
    limit = max_chars if max_chars is not None else link_max()
    return (url if len(url) <= limit else None), len(url)


def link_line(resolved, base=None):
    """The line this script prints. Empty when no viewer URL is configured."""
    base = base if base is not None else site_url()
    if not base:
        return ""
    url, n = make_link(to_share_payload(resolved), base)
    if url:
        return f"Link: {url}"
    return f"Link: omitted — URL would be {n} chars (cap {link_max()}); say so in the reply."


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("resolved", help="resolved answer data (build.py --json)")
    ap.add_argument("--base", help="viewer URL (default: $MTG_JUDGE_SITE or the built-in one)")
    ap.add_argument("--payload", help="also write the share payload JSON here")
    ap.add_argument("--fragment", help="also write the bare fragment ('1.…') here")
    a = ap.parse_args()
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
