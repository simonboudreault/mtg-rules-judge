#!/usr/bin/env python3
"""Build the offline card database this skill reads (data/cards.json.gz).

Normally run by tools/update.py from the GitHub Actions workflow, which rebuilds it
after each new set. You can also run it yourself (it needs internet access to
Scryfall). Python 3.8+, standard library only.

  python3 scripts/build_card_db.py              Oracle text + rulings
  python3 scripts/build_card_db.py --french     also French card names (adds the much
                                                bigger "all cards" download)
  python3 scripts/build_card_db.py --from-dir DIR
        use bulk files you already downloaded from https://scryfall.com/docs/api/bulk-data
        (oracle-cards-*, rulings-*, optionally all-cards-*; .json or .jsonl.gz)

"""
import argparse
import datetime
import glob
import gzip
import json
import os
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "cards.json.gz")
sys.path.insert(0, HERE)
from carddb import compact_card, norm  # noqa: E402

API = "https://api.scryfall.com/bulk-data"
HEADERS = {"User-Agent": "mtg-rules-judge-skill/2.0", "Accept": "application/json;q=0.9,*/*;q=0.8"}
SKIP_LAYOUTS = {"art_series"}


def http_open(url):
    req = urllib.request.Request(url, headers=dict(HEADERS, **{"Accept-Encoding": "gzip"}))
    r = urllib.request.urlopen(req, timeout=60)
    if r.headers.get("Content-Encoding") == "gzip":
        return gzip.GzipFile(fileobj=r), r
    return r, r


def download(url, label):
    """Stream a bulk file to a temp file, with a progress line. Returns the path."""
    fh, resp = http_open(url)
    total = int(resp.headers.get("Content-Length") or 0)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
    got, t0 = 0, time.time()
    while True:
        chunk = fh.read(1 << 20)
        if not chunk:
            break
        tmp.write(chunk)
        got += len(chunk)
        pct = f" / {total / 1e6:.0f} MB" if total else ""
        print(f"\r  {label}: {got / 1e6:.0f} MB{pct}  ({time.time() - t0:.0f}s)", end="", flush=True)
    tmp.close()
    print()
    return tmp.name


def open_any(path):
    with open(path, "rb") as f:
        magic = f.read(2)
    return gzip.open(path, "rt", encoding="utf-8") if magic == b"\x1f\x8b" else open(path, "r", encoding="utf-8")


def iter_array(path):
    """Yield the objects of a (possibly huge) JSON array or JSON Lines file, gzipped or not,
    without loading it all. Scryfall switched its bulk files from JSON arrays to gzipped
    JSON Lines in 2026; both formats work here."""
    dec = json.JSONDecoder()
    with open_any(path) as f:
        state = {"buf": "", "pos": 0, "eof": False}

        def refill():
            more = f.read(1 << 22)
            if not more:
                state["eof"] = True
            state["buf"] = state["buf"][state["pos"]:] + more
            state["pos"] = 0

        started = False
        while True:
            while True:  # skip separators, refilling as needed
                buf, pos = state["buf"], state["pos"]
                while pos < len(buf) and buf[pos] in " \t\r\n,":
                    pos += 1
                state["pos"] = pos
                if pos < len(buf) or state["eof"]:
                    break
                refill()
            buf, pos = state["buf"], state["pos"]
            if pos >= len(buf):
                return
            if not started:
                started = True
                if buf[pos] == "[":       # JSON array
                    state["pos"] = pos + 1
                    continue
                if buf[pos] != "{":       # JSON Lines starts straight with an object
                    raise ValueError(f"{path} is neither a JSON array nor JSON Lines")
            if buf[pos] == "]":
                return
            try:
                obj, end = dec.raw_decode(buf, pos)
            except json.JSONDecodeError:
                if state["eof"]:
                    raise
                refill()
                continue
            state["pos"] = end
            yield obj


def find_local(d, pattern):
    hits = sorted(glob.glob(os.path.join(d, pattern)))
    return hits[-1] if hits else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--french", action="store_true", help="also index French printed names (big download)")
    ap.add_argument("--from-dir", help="folder holding already-downloaded Scryfall bulk files")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()

    meta = {"built": datetime.date.today().isoformat(), "source": "Scryfall bulk data"}
    paths, temps = {}, []
    if a.from_dir:
        paths["oracle"] = find_local(a.from_dir, "oracle-cards*.json*")
        paths["rulings"] = find_local(a.from_dir, "rulings*.json*")
        paths["all"] = find_local(a.from_dir, "all-cards*.json*") if a.french else None
        if not paths["oracle"] or not paths["rulings"]:
            sys.exit("Need oracle-cards-* and rulings-* bulk files (.json or .jsonl.gz) in " + a.from_dir)
    else:
        print("Asking Scryfall for the current bulk files...")
        with urllib.request.urlopen(urllib.request.Request(API, headers=HEADERS), timeout=30) as r:
            bulk = {b["type"]: b for b in json.load(r)["data"]}
        wanted = [("oracle", "oracle_cards"), ("rulings", "rulings")] + ([("all", "all_cards")] if a.french else [])
        for key, typ in wanted:
            b = bulk[typ]
            meta[key + "_updated_at"] = b.get("updated_at")
            url = b.get("jsonl_download_uri") or b.get("download_uri")
            if not url:
                sys.exit(f"Scryfall's bulk list has no download link for {typ}; fields seen: {', '.join(sorted(b))}")
            paths[key] = download(url, typ)
            temps.append(paths[key])
            time.sleep(0.2)

    try:
        print("Indexing Oracle cards...")
        cards = []
        for c in iter_array(paths["oracle"]):
            if c.get("layout") in SKIP_LAYOUTS:
                continue
            cards.append(compact_card(c))
        cards.sort(key=lambda r: (r.get("tok", 0), r["n"]))  # real cards before tokens of the same name

        print("Indexing rulings...")
        rulings = {}
        for r in iter_array(paths["rulings"]):
            src = "w" if r.get("source") == "wotc" else "s"
            rulings.setdefault(r["oracle_id"], []).append([r.get("published_at", ""), src, r.get("comment", "")])
        known = {c["id"] for c in cards}
        rulings = {k: sorted(v, key=lambda x: x[0]) for k, v in rulings.items() if k in known}

        fr = {}
        if paths.get("all"):
            print("Indexing French names (this one is long)...")
            oid_name = {c["id"]: c["n"] for c in cards}
            for c in iter_array(paths["all"]):
                if c.get("lang") != "fr":
                    continue
                faces = c.get("card_faces") or []
                oid = c.get("oracle_id") or (faces[0].get("oracle_id") if faces else None)
                en = oid_name.get(oid)
                if not en:
                    continue
                for nm in [c.get("printed_name")] + [f.get("printed_name") for f in faces]:
                    if nm:
                        fr.setdefault(norm(nm), en)
                        if " // " in nm:
                            for part in nm.split(" // "):
                                fr.setdefault(norm(part), en)
            meta["french_names"] = len(fr)

        meta["cards"], meta["cards_with_rulings"] = len(cards), len(rulings)
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with gzip.open(a.out, "wt", encoding="utf-8", compresslevel=9) as f:
            json.dump({"meta": meta, "cards": cards, "rulings": rulings, "fr": fr}, f, ensure_ascii=False, separators=(",", ":"))
    finally:
        for t in temps:
            try:
                os.remove(t)
            except OSError:
                pass

    size = os.path.getsize(a.out) / 1e6
    print(f"\nWrote {os.path.relpath(a.out)}: {size:.1f} MB")
    print(f"  {meta['cards']} cards, {meta['cards_with_rulings']} with rulings" + (f", {len(fr)} French names" if fr else ""))


if __name__ == "__main__":
    main()
