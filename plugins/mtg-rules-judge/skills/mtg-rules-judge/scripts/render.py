"""Render the resolved answer data (what build.py assembles) into static HTML.

The page used to be drawn in the browser from the embedded JSON; drawing it here
means it shows as soon as the HTML arrives. The JSON is still embedded in the page
(id="answer-data") so any other renderer, such as a hosted viewer, can reuse it.

render_page(data, template_text) -> full page text.
"""
import json
import re

LABELS = {
    "en": {
        "nav": {"answer": "Answer", "cards": "Cards", "rules": "Rules", "rulings": "Rulings",
                "walkthrough": "Walkthrough", "confidence": "Confidence", "community": "Reddit"},
        "kicker": "Rules question", "shortAnswer": "Short answer", "cards": "Cards", "rules": "Relevant rules",
        "rulings": "Official rulings", "walkthrough": "How it plays out", "confidence": "Confidence",
        "community": "Reddit discussions", "communityKicker": "Unofficial · community opinions",
        "crVersion": "Comprehensive Rules effective", "generated": "Researched", "allCards": "All cards on Scryfall",
        "card": "Card", "rule": "Rule", "ruling": "Ruling", "official": "Official", "scryfallNote": "Scryfall note",
        "openOn": "Open on", "why": "Why", "assumptions": "Assumptions", "notRetrieved": "Not retrieved",
        "high": "High", "medium": "Medium", "low": "Low", "agrees": "Matches the official sources:",
        "yes": "Yes", "partly": "Partly", "no": "No", "unknown": "Unknown",
        "noThreads": "No Reddit thread could be retrieved for this question.",
        "searchReddit": "Search r/mtgrules yourself", "opinions": "Main opinions",
        "pinHint": "Click to pin · Esc to close", "comments": "comments",
        "missingRef": "referenced but not present in the data",
        "shareOpen": "Open the shareable page", "shareCopy": "Copy link", "shareCopied": "Copied",
        "shareManual": "Copy this link:",
        "footer": "Rules text and card data are quoted verbatim from the sources named above. Community opinions "
                  "are summarised, not verified. Check with a judge for tournament play.",
    },
    "fr": {
        "nav": {"answer": "Réponse", "cards": "Cartes", "rules": "Règles", "rulings": "Rulings",
                "walkthrough": "Déroulement", "confidence": "Confiance", "community": "Reddit"},
        "kicker": "Question de règles", "shortAnswer": "Réponse courte", "cards": "Cartes",
        "rules": "Règles pertinentes", "rulings": "Rulings officiels", "walkthrough": "Déroulement",
        "confidence": "Confiance", "community": "Discussions Reddit",
        "communityKicker": "Non officiel · opinions de la communauté",
        "crVersion": "Règles complètes en vigueur le", "generated": "Recherche effectuée le",
        "allCards": "Toutes les cartes sur Scryfall", "card": "Carte", "rule": "Règle", "ruling": "Ruling",
        "official": "Officiel", "scryfallNote": "Note Scryfall", "openOn": "Ouvrir sur", "why": "Pourquoi",
        "assumptions": "Hypothèses", "notRetrieved": "Non récupéré", "high": "Élevée", "medium": "Moyenne",
        "low": "Faible", "agrees": "Concorde avec les sources officielles :", "yes": "Oui", "partly": "En partie",
        "no": "Non", "unknown": "Inconnu", "noThreads": "Aucun fil Reddit n'a pu être récupéré pour cette question.",
        "searchReddit": "Chercher vous-même sur r/mtgrules", "opinions": "Principales opinions",
        "pinHint": "Toucher pour épingler · Échap pour fermer", "comments": "commentaires",
        "missingRef": "référencé mais absent des données",
        "shareOpen": "Ouvrir la page à partager", "shareCopy": "Copier le lien", "shareCopied": "Copié",
        "shareManual": "Copiez ce lien :",
        "footer": "Le texte des règles et des cartes est cité mot pour mot depuis les sources nommées ci-dessus. "
                  "Les opinions de la communauté sont résumées, pas vérifiées. Consultez un arbitre en tournoi.",
    },
}

RULE_LINK = "https://magic.wizards.com/en/rules"
HYBRID = {"W": "#F8F6D8", "U": "#C1D7E9", "B": "#BAB1AB", "R": "#E49977", "G": "#A3C095"}
EXT = ' target="_blank" rel="noopener"'


def esc(s):
    s = "" if s is None else str(s)
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&#39;"))


def unesc(s):
    return (s.replace("&#39;", "'").replace("&quot;", '"').replace("&lt;", "<")
            .replace("&gt;", ">").replace("&amp;", "&"))


def slug(s):
    return re.sub(r"(^-|-$)", "", re.sub(r"[^a-z0-9]+", "-", str(s).lower()))


def search_link(name):
    from urllib.parse import quote
    return "https://scryfall.com/search?q=" + quote('!"' + name + '"', safe="")


class Page:
    def __init__(self, data, share_url=None):
        self.d = data
        self.share_url = share_url  # hosted-viewer link for this answer (scripts/share.py), or None
        self.L = LABELS.get(data.get("lang"), LABELS["en"])
        self.cards = {}
        for c in data.get("cards") or []:
            c.setdefault("id", slug(c["name"]))
            self.cards[c["id"]] = c
            self.cards.setdefault(slug(c["name"]), c)
        self.rules = {r["id"]: r for r in data.get("rules") or []}
        self.rulings = {r["id"]: r for r in data.get("rulings") or []}
        self.used = []  # (kind, key) of every inline ref drawn, for the popover templates

    # ---------- text ----------
    def mana(self, h):
        def sym(m):
            s = m.group(1).upper()
            if "/" in s:
                a, b = s.split("/", 1)
                return (f'<span class="ms ms-hybrid" style="--h1:{HYBRID.get(a, "#CAC5C0")};'
                        f'--h2:{HYBRID.get(b, "#CAC5C0")}" title="{esc(m.group(0))}">{esc(a)}/{esc(b)}</span>')
            cls = "ms-" + s if re.fullmatch(r"[WUBRGC]", s) else ("ms-T" if s == "T" else "")
            return f'<span class="ms {cls}" title="{esc(m.group(0))}">{esc("⟳" if s == "T" else s)}</span>'
        return re.sub(r"\{([^}]{1,4})\}", sym, h)

    def inline(self, text):
        L = self.L
        h = esc(text)
        h = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", h)
        h = re.sub(r"(^|[^*])\*([^*\n]+)\*", r"\1<i>\2</i>", h)
        h = re.sub(r"`([^`]+)`", r"<code>\1</code>", h)

        def ref(m):
            kind, key, label = m.group(1), unesc(m.group(2).strip()), m.group(3)
            label = unesc(label) if label else None
            if kind == "link":
                return f'<a href="{esc(label or key)}"{EXT}>{esc(key)}</a>'
            missing = lambda txt: f'<span class="ref ref-missing" title="{esc(L["missingRef"])}">{esc(txt)}</span>'
            if kind == "card":
                c = self.cards.get(key) or self.cards.get(slug(key))
                if not c:
                    return missing(label or key)
                key, text_ = c["id"], label or c["name"]
            elif kind == "rule":
                if key not in self.rules:
                    return missing(label or "CR " + key)
                text_ = label or "CR " + key
            else:
                r = self.rulings.get(key)
                if not r:
                    return missing(label or key)
                c = self.cards.get(r.get("card"))
                text_ = label or f'{L["ruling"].lower()} {c["name"] + ", " if c else ""}{r.get("date", "")}'
            if (kind, key) not in self.used:
                self.used.append((kind, key))
            return (f'<button type="button" class="ref ref-{kind}" data-pop="{esc(kind)}:{esc(key)}" '
                    f'aria-expanded="false">{esc(text_)}</button>')

        h = re.sub(r"\[\[(card|rule|ruling|link):([^\]|]+)(?:\|([^\]]+))?\]\]", ref, h)
        return self.mana(h)

    def paras(self, text):
        parts = re.split(r"\n{2,}", "" if text is None else str(text))
        return "".join(f"<p>{self.inline(p).replace(chr(10), '<br>')}</p>" for p in parts)

    def rule_body(self, text):
        out = []
        for line in str(text or "").split("\n"):
            out.append(f'<span class="ex">{self.inline(line)}</span>' if re.match(r"\s*Example:", line, re.I)
                       else self.inline(line))
        return "<br>".join(out)

    # ---------- pieces ----------
    @staticmethod
    def frame_class(c):
        cols, t = c.get("colors") or [], (c.get("typeLine") or "").lower()
        if len(cols) > 1:
            return "frame-M"
        if len(cols) == 1:
            return "frame-" + cols[0]
        return "frame-L" if "land" in t else "frame-A" if "artifact" in t else "frame-C"

    def card_frame(self, c):
        faces = c.get("faces") or [c]
        f = faces[0]
        pt = (f"{esc(f['power'])}/{esc(f.get('toughness'))}" if f.get("power") is not None
              else esc(f["loyalty"]) if f.get("loyalty") is not None
              else esc(f["defense"]) if f.get("defense") is not None else "")
        extra = "".join(
            f'<hr class="face-sep"><b>{esc(x.get("name"))}</b> {self.mana(esc(x.get("manaCost") or ""))}'
            f'<br><i>{esc(x.get("typeLine") or "")}</i>{self.paras(x.get("oracleText"))}' for x in faces[1:])
        # Only embedded images: artifact pages can't load images from other sites.
        img = (f'<img class="art" alt="" src="{esc(c["imageDataUri"])}">' if c.get("imageDataUri") else "")
        tag = f'<span class="tag">{esc(c["note"])}</span>' if c.get("note") else ""
        href = c.get("scryfallUri") or search_link(c["name"])
        cls = self.frame_class(c) + (" has-image" if img else "")
        return (f'<a class="cardframe {cls}" href="{esc(href)}"{EXT} title="{esc(self.L["openOn"])} Scryfall">{tag}{img}'
                f'<div class="inner"><div class="bar"><span class="name">{esc(f.get("name") or c["name"])}</span>'
                f'<span class="cost">{self.mana(esc(f.get("manaCost") or c.get("manaCost") or ""))}</span></div>'
                f'<div class="bar type"><span>{esc(f.get("typeLine") or c.get("typeLine") or "")}</span></div>'
                f'<div class="box">{self.paras(f.get("oracleText") or c.get("oracleText"))}{extra}'
                + (f'<div class="pt">{pt}</div>' if pt else "") + '</div></div></a>')

    def ruling_src(self, r):
        if r.get("source") == "wotc":
            return f'<span class="src">{esc(self.L["official"])}</span>'
        return f'<span class="src scryfall">{esc(r.get("sourceLabel") or self.L["scryfallNote"])}</span>'

    @staticmethod
    def links(items):
        return "".join(f'<a href="{esc(l["url"])}"{EXT}>{esc(l["label"])} →</a>' for l in items or [])

    # ---------- sections ----------
    def header(self):
        d, L = self.d, self.L
        q = f'<div class="question">{self.paras(d["question"])}</div>' if d.get("question") else ""
        return (f'<header><div class="eyebrow">{esc(L["kicker"])}</div><h1>{esc(d.get("title"))}</h1>{q}'
                f'<div class="meta"><span>{esc(L["crVersion"])} <b>{esc(d.get("crEffectiveDate") or "?")}</b></span>'
                f'<span>{esc(L["generated"])} <b>{esc(d.get("generatedAt") or "")}</b></span></div>'
                f'{self.share_bar()}</header>')

    def share_bar(self):
        """The share link lives in the page so nobody has to type it: open it, or copy it."""
        if not self.share_url:
            return ""
        L, u = self.L, esc(self.share_url)
        return (f'<div class="share"><a class="share-open" href="{u}"{EXT}>{esc(L["shareOpen"])} →</a>'
                f'<button type="button" class="share-copy" data-url="{u}" data-done="{esc(L["shareCopied"])}">'
                f'{esc(L["shareCopy"])}</button>'
                f'<label class="share-manual hidden">{esc(L["shareManual"])} <input readonly value="{u}"></label></div>')

    def nav(self, present):
        N = self.L["nav"]
        items = "".join(
            '<li><a href="#%s"%s>%s</a></li>' % (k, ' class="unofficial-link"' if k == "community" else "", esc(N[k]))
            for k in present)
        return f'<nav class="sections"><ul>{items}</ul></nav>'

    def answer(self):
        lvl = (self.d.get("confidence") or {}).get("level") or "medium"
        return (f'<section id="answer"><h2>{esc(self.L["shortAnswer"])}</h2><div class="verdict">'
                f'<div class="text">{self.paras(self.d.get("shortAnswer"))}</div>'
                f'<span class="pill {esc(lvl)}">{esc(self.L["confidence"])}: {esc(self.L.get(lvl, lvl))}</span>'
                f'</div></section>')

    def cards_section(self):
        cards = self.d.get("cards") or []
        if not cards:
            return ""
        foot = (f'<p class="cards-foot"><a href="{esc(self.d["allCardsLink"])}"{EXT}>{esc(self.L["allCards"])} →</a></p>'
                if self.d.get("allCardsLink") else "")
        return (f'<section id="cards"><h2>{esc(self.L["cards"])} <span class="count">{len(cards)}</span></h2>'
                f'<div class="cards-grid">{"".join(self.card_frame(c) for c in cards)}</div>{foot}</section>')

    def rules_section(self):
        rules = self.d.get("rules") or []
        if not rules:
            return ""
        rows = "".join(
            f'<div class="quote" id="rule-{esc(slug(r["id"]))}"><div class="key"><a href="{RULE_LINK}"{EXT}>{esc(r["id"])}</a>'
            f'</div><div class="body">{self.rule_body(r.get("text"))}</div></div>' for r in rules)
        return f'<section id="rules"><h2>{esc(self.L["rules"])} <span class="count">{len(rules)}</span></h2>{rows}</section>'

    def rulings_section(self):
        rulings = self.d.get("rulings") or []
        if not rulings:
            return ""
        groups = {}
        for r in rulings:
            groups.setdefault(r.get("card"), []).append(r)
        out = []
        for cid, rs in groups.items():
            c = self.cards.get(cid)
            rows = ""
            for r in rs:
                links = f'<div class="pop-links">{self.links(r["links"])}</div>' if r.get("links") else ""
                rows += (f'<div class="quote ruling" id="ruling-{esc(slug(r["id"]))}"><div class="key">'
                         f'<span>{esc(r.get("date") or "")}</span>{self.ruling_src(r)}</div>'
                         f'<div class="body">{self.paras(r.get("text"))}{links}</div></div>')
            out.append(f'<div class="ruling-group"><h3>{esc(c["name"] if c else cid)}</h3>{rows}</div>')
        return (f'<section id="rulings"><h2>{esc(self.L["rulings"])} <span class="count">{len(rulings)}</span></h2>'
                f'{"".join(out)}</section>')

    def steps_section(self):
        steps = self.d.get("steps") or []
        if not steps:
            return ""
        items = ""
        for s in steps:
            note = f'<div class="note">{self.inline(s["note"])}</div>' if s.get("note") else ""
            items += f'<li><div class="step">{self.paras(s.get("text"))}{note}</div></li>'
        return f'<section id="walkthrough"><h2>{esc(self.L["walkthrough"])}</h2><ol class="steps">{items}</ol></section>'

    def confidence_section(self):
        c = self.d.get("confidence")
        if not c:
            return ""
        L = self.L

        def panel(title, items):
            if not items:
                return ""
            return (f'<div class="panel"><h3>{esc(title)}</h3><ul>'
                    f'{"".join(f"<li>{self.inline(i)}</li>" for i in items)}</ul></div>')
        lvl = c.get("level") or "medium"
        return (f'<section id="confidence"><h2>{esc(L["confidence"])} <span class="pill {esc(lvl)}">{esc(L.get(lvl, lvl))}</span></h2>'
                f'<div class="confidence">{panel(L["why"], c.get("reasons"))}{panel(L["assumptions"], c.get("assumptions"))}'
                f'{panel(L["notRetrieved"], c.get("notRetrieved"))}</div></section>')

    def community_section(self):
        r, L = self.d.get("reddit"), self.L
        if not r:
            return ""
        cls, txt = {"yes": ("high", L["yes"]), "partly": ("medium", L["partly"]),
                    "no": ("low", L["no"])}.get(r.get("agreesWithOfficial"), ("", L["unknown"]))
        threads = r.get("threads") or []
        if threads:
            lis = []
            for t in threads:
                head = (f'<a href="{esc(t.get("url"))}"{EXT}>{esc(t.get("title"))}</a><span>{esc(t.get("subreddit") or "")}</span>'
                        f'<span>{esc(t.get("date") or "")}</span>'
                        + (f'<span>{esc(t["comments"])} {esc(L["comments"])}</span>' if t.get("comments") is not None else "")
                        + ('<span class="src">judge</span>' if t.get("judgeFlair") else ""))
                summ = f'<div class="t-sum">{self.inline(t["summary"])}</div>' if t.get("summary") else ""
                lis.append(f'<li><div class="t-head">{head}</div>{summ}</li>')
            th = f'<ul class="threads">{"".join(lis)}</ul>'
        else:
            th = "" if r.get("searched") is False else f'<p class="muted">{esc(L["noThreads"])}</p>'
        agree = (f'<div class="agree">{esc(L["agrees"])} <span class="pill {cls}">{esc(txt)}</span></div>' if threads else "")
        ops = r.get("opinions") or []
        ops_h = (f'<div class="eyebrow opinions-head">{esc(L["opinions"])}</div><ul class="opinions">'
                 f'{"".join(f"<li>{self.inline(o)}</li>" for o in ops)}</ul>' if ops else "")
        notes = f'<p class="muted notes">{self.inline(r["notes"])}</p>' if r.get("notes") else ""
        search = (f'<p><a href="{esc(r["searchUrl"])}"{EXT}>{esc(L["searchReddit"])} →</a></p>' if r.get("searchUrl") else "")
        return (f'<section id="community" class="community"><div class="eyebrow">{esc(L["communityKicker"])}</div>'
                f'<h2>{esc(L["community"])}</h2>{agree}{self.paras(r["overview"]) if r.get("overview") else ""}'
                f'{ops_h}{th}{notes}{search}</section>')

    def footer(self):
        srcs = []
        for c in self.d.get("cards") or []:
            if c.get("source") and c["source"] not in srcs:
                srcs.append(c["source"])
        tail = f' <span class="mono">{esc(" · ".join(srcs))}</span>' if srcs else ""
        return f'<footer>{esc(self.L["footer"])}{tail}</footer>'

    # ---------- popovers (pre-rendered, inert until opened) ----------
    def popover(self, kind, key):
        L, d = self.L, self.d
        if kind == "card":
            c = self.cards[key]
            links = f'<a href="{esc(c.get("scryfallUri") or search_link(c["name"]))}"{EXT}>{esc(L["openOn"])} Scryfall →</a>'
            return (f'<div class="pop-head"><span class="pop-title">{esc(c["name"])}</span><span class="pop-kind">{esc(L["card"])}</span></div>'
                    f'{self.card_frame(c)}<div class="pop-links">{links}{self.links(c.get("links"))}</div>')
        if kind == "rule":
            r = self.rules[key]
            return (f'<div class="pop-head"><span class="pop-title mono">{esc(r["id"])}</span><span class="pop-kind">'
                    f'{esc(L["rule"])} · CR {esc(d.get("crEffectiveDate") or "")}</span></div>'
                    f'<div class="pop-body">{self.rule_body(r.get("text"))}</div><div class="pop-links">'
                    f'<a href="#rule-{esc(slug(r["id"]))}">↓ {esc(L["rules"])}</a><a href="{RULE_LINK}"{EXT}>magic.wizards.com →</a></div>')
        r = self.rulings[key]
        c = self.cards.get(r.get("card"))
        sc = f'<a href="{esc(c["scryfallUri"])}"{EXT}>Scryfall →</a>' if c and c.get("scryfallUri") else ""
        return (f'<div class="pop-head"><span class="pop-title">{esc(c["name"] if c else r.get("card"))}</span>'
                f'<span class="pop-kind">{esc(L["ruling"])} · {esc(r.get("date") or "")}</span></div>{self.ruling_src(r)}'
                f'<div class="pop-body pop-ruling">{self.paras(r.get("text"))}</div><div class="pop-links">'
                f'<a href="#ruling-{esc(slug(r["id"]))}">↓ {esc(L["rulings"])}</a>{self.links(r.get("links"))}{sc}</div>')

    def render(self):
        sections = [
            ("answer", self.answer()), ("cards", self.cards_section()), ("rules", self.rules_section()),
            ("rulings", self.rulings_section()), ("walkthrough", self.steps_section()),
            ("confidence", self.confidence_section()), ("community", self.community_section()),
        ]
        present = [k for k, h in sections if h]
        app = self.header() + self.nav(present) + "".join(h for _, h in sections) + self.footer()
        # Popovers may reference more items (a ruling inside a popover has no refs, so one pass is enough).
        pops = "".join(f'<template data-pop="{esc(k)}:{esc(v)}">{self.popover(k, v)}</template>' for k, v in self.used)
        return app, pops


def render_page(data, template, share_url=None):
    page = Page(data, share_url)
    app, pops = page.render()
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    fills = {
        "TITLE": esc(data.get("title") or "MTG rules answer"),
        "LANG": esc(data.get("lang") or "en"),
        "PIN_HINT": esc(page.L["pinHint"]),
        "APP": app,
        "POPOVERS": pops,
        "DATA": blob,
    }
    return re.sub(r"<!--@(\w+)@-->", lambda m: fills[m.group(1)], template)
