"""Shared helpers for the offline card database (data/cards.json).

Used by lookup.py, build.py and build_card_db.py. Standard library only.
"""
import gzip
import json
import os
import re
import unicodedata
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("MTG_CARD_DB", os.path.join(HERE, "..", "data", "cards.json"))
if not os.path.exists(DB_PATH) and os.path.exists(DB_PATH + ".gz"):
    DB_PATH += ".gz"  # the manual-upload zip ships it gzipped
CACHE_PATH = os.environ.get("MTG_CARD_CACHE", os.path.join(os.getcwd(), "mtg_cards_cache.json"))
API = "https://api.scryfall.com"
HEADERS = {"User-Agent": "mtg-rules-judge-skill/2.0", "Accept": "application/json"}


def norm(s):
    """Matching key: lowercase, no accents, letters and digits only."""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", s)


def slug(s):
    """Same as the answer template's slug(), so ids line up."""
    return re.sub(r"(^-|-$)", "", re.sub(r"[^a-z0-9]+", "-", str(s).lower()))


# ---------- compact records (shared with build_card_db.py) ----------

def face_fields(f):
    out = {}
    for src, dst in (("name", "n"), ("mana_cost", "m"), ("type_line", "t"), ("oracle_text", "o"),
                     ("power", "p"), ("toughness", "th"), ("loyalty", "l"), ("defense", "d")):
        if f.get(src) not in (None, ""):
            out[dst] = f[src]
    if f.get("colors"):
        out["c"] = "".join(f["colors"])
    return out


def compact_card(c):
    faces = c.get("card_faces") or []
    oid = c.get("oracle_id") or (faces[0].get("oracle_id") if faces else None)
    rec = face_fields(c)
    rec["id"] = oid
    rec["lay"] = c.get("layout")
    if not rec.get("c") and faces and faces[0].get("colors"):
        rec["c"] = "".join(faces[0]["colors"])
    if faces:
        rec["f"] = [face_fields(f) for f in faces]
    if c.get("keywords"):
        rec["k"] = c["keywords"]
    # image and page links are derived from the name at build time (smaller database)
    if c.get("set_type") == "token" or "Token" in (c.get("type_line") or ""):
        rec["tok"] = 1
    return rec


# ---------- database ----------

class CardDB:
    def __init__(self):
        self.meta, self.cards, self.rulings, self.fr = {}, [], {}, {}
        self.loaded = False
        if os.path.exists(DB_PATH):
            opener = gzip.open if DB_PATH.endswith(".gz") else open
            with opener(DB_PATH, "rt", encoding="utf-8") as f:
                d = json.load(f)
            self.meta, self.cards, self.rulings, self.fr = d["meta"], d["cards"], d["rulings"], d.get("fr", {})
            self.loaded = True
        self.cache = {"cards": [], "rulings": {}}
        if os.path.exists(CACHE_PATH):
            try:
                with open(CACHE_PATH, encoding="utf-8") as f:
                    self.cache = json.load(f)
            except (OSError, ValueError):
                pass
        self._index()

    def _index(self):
        self.by_name, self.by_face = {}, {}
        for rec in self.cache["cards"] + self.cards:  # cache first: freshest text wins
            self.by_name.setdefault(norm(rec["n"]), rec)
            for f in rec.get("f", []):
                if f.get("n"):
                    self.by_face.setdefault(norm(f["n"]), rec)
        self.rulings_all = dict(self.rulings, **self.cache.get("rulings", {}))

    # -- lookup --
    def find(self, query):
        """Return (record or None, how, suggestions)."""
        k = norm(query)
        if not k:
            return None, "empty", []
        if k in self.by_name:
            return self.by_name[k], "exact", []
        if k in self.by_face:
            return self.by_face[k], "face name", []
        if k in self.fr and norm(self.fr[k]) in self.by_name:
            return self.by_name[norm(self.fr[k])], "French name", []
        starts = [n for n in self.by_name if n.startswith(k)]
        if len(starts) == 1:
            return self.by_name[starts[0]], "prefix", []
        import difflib
        pool = list(self.by_name) + list(self.fr)
        close = difflib.get_close_matches(k, pool, n=5, cutoff=0.8)
        names = []
        for c in close:
            rec = self.by_name.get(c) or self.by_name.get(norm(self.fr.get(c, "")))
            if rec and rec["n"] not in names:
                names.append(rec["n"])
        if len(names) == 1 or (names and difflib.SequenceMatcher(None, k, norm(names[0])).ratio() > 0.92):
            return self.by_name[norm(names[0])], f"fuzzy match for '{query}'", names[1:]
        return None, "not found", names or [self.by_name[s]["n"] for s in starts[:5]]

    def rulings_for(self, rec):
        rows = self.rulings_all.get(rec.get("id"), [])
        base = slug(rec["n"])
        return [{"id": f"{base}-{i}", "card": base, "date": d, "source": "wotc" if s == "w" else "scryfall", "text": t}
                for i, (d, s, t) in enumerate(rows, 1)]

    # -- network fallback (works only where the sandbox can reach Scryfall) --
    def fetch_remote(self, query, timeout=6):
        def get(url):
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=timeout) as r:
                return json.load(r)
        c = get(f"{API}/cards/named?fuzzy={urllib.parse.quote(query)}")
        rec = compact_card(c)
        rows = []
        if c.get("rulings_uri"):
            for r in get(c["rulings_uri"]).get("data", []):
                rows.append([r.get("published_at", ""), "w" if r.get("source") == "wotc" else "s", r.get("comment", "")])
        self.cache["cards"] = [x for x in self.cache["cards"] if x["n"] != rec["n"]] + [rec]
        self.cache.setdefault("rulings", {})[rec["id"]] = rows
        try:
            with open(CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False)
        except OSError:
            pass
        self._index()
        return rec


def to_template_card(rec, source):
    """Record -> card object for the answer template."""
    faces = rec.get("f") or []
    card = {"id": slug(rec["n"]), "name": rec["n"], "oracleId": rec.get("id")}
    if faces:  # double-faced, split, adventure...: the template draws each face
        card["faces"] = [{k2: f[k1] for k1, k2 in (("n", "name"), ("m", "manaCost"), ("t", "typeLine"), ("o", "oracleText"),
                                                      ("p", "power"), ("th", "toughness"), ("l", "loyalty"), ("d", "defense")) if k1 in f}
                         for f in faces]
    for src, dst in (("m", "manaCost"), ("t", "typeLine"), ("o", "oracleText"), ("p", "power"), ("th", "toughness"),
                     ("l", "loyalty"), ("d", "defense")):
        if src in rec:
            card[dst] = rec[src]
    if faces and "typeLine" not in card:
        card["typeLine"] = faces[0].get("t", "")
    card["colors"] = list(rec.get("c", ""))
    if rec.get("tok"):
        card["note"] = "token"
    exact = urllib.parse.quote(rec["n"])
    card["scryfallUri"] = rec.get("u") or "https://scryfall.com/search?q=" + urllib.parse.quote(f'!"{rec["n"]}"')
    card["imageUrl"] = rec.get("img") or f"https://api.scryfall.com/cards/named?exact={exact}&format=image&version=normal"
    card["source"] = source
    return card


def card_text(rec):
    """Plain-text card block for lookup.py output."""
    out = []
    faces = rec.get("f") or []
    if faces:
        for f in faces:
            line = f"  [{f.get('n')}] {f.get('m', '')} · {f.get('t', '')}"
            out.append(line)
            if f.get("o"):
                out += ["    " + l for l in f["o"].split("\n")]
            if "p" in f:
                out.append(f"    {f['p']}/{f['th']}")
            if "l" in f:
                out.append(f"    Loyalty {f['l']}")
            if "d" in f:
                out.append(f"    Defense {f['d']}")
    else:
        out.append(f"  {rec.get('m', '')} · {rec.get('t', '')}".replace("  · ", "  "))
        if rec.get("o"):
            out += ["  " + l for l in rec["o"].split("\n")]
        if "p" in rec:
            out.append(f"  {rec['p']}/{rec['th']}")
        if "l" in rec:
            out.append(f"  Loyalty {rec['l']}")
        if "d" in rec:
            out.append(f"  Defense {rec['d']}")
    return "\n".join(out)
