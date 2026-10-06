// Port of scripts/render.py: same sections, inline markup, popovers and slug(), so a
// link and the artifact page look alike. Differences, all because data arrives later
// here: cards, rules and rulings carry a _state ("loading", "ok", "maybe",
// "unavailable", "external"), cards can show Scryfall images, and every href goes
// through safeUrl() because anyone can craft a link.

import { LABELS, SITE } from "./labels.js";

export const RULE_LINK = "https://magic.wizards.com/en/rules";
const HYBRID = { W: "#F8F6D8", U: "#C1D7E9", B: "#BAB1AB", R: "#E49977", G: "#A3C095" };
const EXT = ' target="_blank" rel="noopener"';

export function esc(s) {
  s = s == null ? "" : String(s);
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function unesc(s) {
  return s.replace(/&#39;/g, "'").replace(/&quot;/g, '"').replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">").replace(/&amp;/g, "&");
}

/** Same as carddb.py / render.py slug(). */
export function slug(s) {
  return String(s).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
}

/** Only http(s) links leave this page; anything else becomes a dead link. */
export function safeUrl(u) {
  try {
    const url = new URL(String(u), "https://example.invalid/");
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : "#";
  } catch {
    return "#";
  }
}

export function searchLink(name) {
  return "https://scryfall.com/search?q=" + encodeURIComponent('!"' + name + '"');
}

export class Page {
  constructor(d) {
    this.d = d;
    this.L = LABELS[d.lang] || LABELS.en;
    this.S = SITE[d.lang] || SITE.en;
    this.cards = new Map();
    for (const c of d.cards || []) {
      this.cards.set(c.id, c);
      if (!this.cards.has(slug(c.name))) this.cards.set(slug(c.name), c);
    }
    this.rules = new Map((d.rules || []).map((r) => [r.id, r]));
    this.rulings = new Map((d.rulings || []).map((r) => [r.id, r]));
    this.used = []; // "kind:key" of every inline ref drawn, for the popover templates
  }

  // ---------- text ----------
  mana(h) {
    return h.replace(/\{([^}]{1,4})\}/g, (m0, g) => {
      const s = g.toUpperCase();
      const i = s.indexOf("/");
      if (i >= 0) {
        const a = s.slice(0, i), b = s.slice(i + 1);
        return `<span class="ms ms-hybrid" style="--h1:${HYBRID[a] || "#CAC5C0"};--h2:${HYBRID[b] || "#CAC5C0"}" ` +
          `title="${esc(m0)}">${esc(a)}/${esc(b)}</span>`;
      }
      const cls = /^[WUBRGC]$/.test(s) ? "ms-" + s : s === "T" ? "ms-T" : "";
      return `<span class="ms ${cls}" title="${esc(m0)}">${esc(s === "T" ? "⟳" : s)}</span>`;
    });
  }

  inline(text) {
    const L = this.L;
    let h = esc(text);
    h = h.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
    h = h.replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<i>$2</i>");
    h = h.replace(/`([^`]+)`/g, "<code>$1</code>");
    h = h.replace(/\[\[(card|rule|ruling|link):([^\]|]+)(?:\|([^\]]+))?\]\]/g, (m0, kind, rawKey, rawLabel) => {
      let key = unesc(rawKey.trim());
      const label = rawLabel ? unesc(rawLabel) : null;
      if (kind === "link") return `<a href="${esc(safeUrl(label || key))}"${EXT}>${esc(key)}</a>`;
      const missing = (t) => `<span class="ref ref-missing" title="${esc(L.missingRef)}">${esc(t)}</span>`;
      let shown;
      if (kind === "card") {
        const c = this.cards.get(key) || this.cards.get(slug(key));
        if (!c) return missing(label || key);
        key = c.id;
        shown = label || c.name;
      } else if (kind === "rule") {
        if (!this.rules.has(key)) return missing(label || "CR " + key);
        shown = label || "CR " + key;
      } else {
        const r = this.rulings.get(key);
        if (!r) return missing(label || key);
        const c = this.cards.get(r.card);
        shown = label || `${L.ruling.toLowerCase()} ${c ? c.name + ", " : ""}${r.date || ""}`;
      }
      const k = kind + ":" + key;
      if (!this.used.includes(k)) this.used.push(k);
      // A span, not a <button>: buttons can't wrap across lines, so long refs broke out of the text on phones.
      return `<span role="button" tabindex="0" class="ref ref-${kind}" data-pop="${esc(k)}" aria-expanded="false">${esc(shown)}</span>`;
    });
    return this.mana(h);
  }

  paras(text) {
    return String(text == null ? "" : text).split(/\n{2,}/)
      .map((p) => `<p>${this.inline(p).replace(/\n/g, "<br>")}</p>`).join("");
  }

  ruleBody(r) {
    if (r.text === undefined) return `<span class="muted">${esc(this.S.ruleLoading)}</span>`;
    if (r.text === null) {
      return `<span class="muted">${esc(this.S.ruleMissing)} <a href="${RULE_LINK}"${EXT}>magic.wizards.com</a></span>`;
    }
    return String(r.text).split("\n")
      .map((line) => (/^\s*Example:/i.test(line) ? `<span class="ex">${this.inline(line)}</span>` : this.inline(line)))
      .join("<br>");
  }

  // ---------- pieces ----------
  static frameClass(c) {
    const cols = c.colors || [], t = (c.typeLine || "").toLowerCase();
    if (cols.length > 1) return "frame-M";
    // colors can come from the link (web-fallback cards): only known letters reach the markup
    if (cols.length === 1) return "frame-" + (/^[WUBRG]$/.test(cols[0]) ? cols[0] : "C");
    return t.includes("land") ? "frame-L" : t.includes("artifact") ? "frame-A" : "frame-C";
  }

  /** The text "proxy" frame; it is covered by the Scryfall image when there is one. */
  cardFrame(c, withImage) {
    const S = this.S;
    const faces = c.faces && c.faces.length ? c.faces : [c];
    const f = faces[0];
    const pt = f.power != null ? `${esc(f.power)}/${esc(f.toughness)}`
      : f.loyalty != null ? esc(f.loyalty) : f.defense != null ? esc(f.defense) : "";
    let box;
    if (c._state === "loading") box = `<p class="muted">${esc(S.loading)}</p>`;
    else if (c._state === "unavailable") box = `<p class="muted">${esc(S.unavailable)}</p>`;
    else {
      const extra = faces.slice(1).map((x) =>
        `<hr class="face-sep"><b>${esc(x.name)}</b> ${this.mana(esc(x.manaCost || ""))}` +
        `<br><i>${esc(x.typeLine || "")}</i>${this.paras(x.oracleText)}`).join("");
      box = this.paras(f.oracleText || c.oracleText) + extra + (pt ? `<div class="pt">${pt}</div>` : "");
    }
    const images = withImage ? c._images || [] : [];
    const img = images.length
      ? `<img class="art" alt="${esc(c.name)}" src="${esc(images[0])}" data-images="${esc(JSON.stringify(images))}" ` +
        `data-i="0" loading="lazy" decoding="async">`
      : "";
    const tag = c.note ? `<span class="tag">${esc(c.note)}</span>` : "";
    const href = safeUrl(c.scryfallUri || searchLink(c.name));
    const cls = Page.frameClass(c) + (img ? " has-image" : "");
    return `<a class="cardframe ${esc(cls)}" href="${esc(href)}"${EXT} title="${esc(this.L.openOn)} Scryfall">${tag}${img}` +
      `<div class="inner"><div class="bar"><span class="name">${esc(f.name || c.name)}</span>` +
      `<span class="cost">${this.mana(esc(f.manaCost || c.manaCost || ""))}</span></div>` +
      `<div class="bar type"><span>${esc(f.typeLine || c.typeLine || "")}</span></div>` +
      `<div class="box">${box}</div></div></a>`;
  }

  cardSlot(c, withNote = true) {
    const flip = (c._images || []).length > 1
      ? `<button type="button" class="flip" data-flip>${esc(this.S.flip)}</button>` : "";
    const note = withNote && c._changed ? `<p class="card-note">${esc(this.S.textChanged)}</p>` : "";
    return `<div class="cardslot">${this.cardFrame(c, true)}${flip}${note}</div>`;
  }

  rulingSrc(r) {
    if (r.source === "wotc") return `<span class="src">${esc(this.L.official)}</span>`;
    return `<span class="src scryfall">${esc(r.sourceLabel || this.L.scryfallNote)}</span>`;
  }

  rulingBody(r) {
    if (r._state === "loading") return `<p class="muted">${esc(this.S.rulingLoading)}</p>`;
    if (r._state === "unavailable") return `<p class="muted">${esc(this.S.rulingMissing)}</p>`;
    const maybe = r._state === "maybe" ? `<p class="card-note">${esc(this.S.rulingMaybe)}</p>` : "";
    return this.paras(r.text) + maybe;
  }

  static links(items) {
    return (items || []).map((l) => `<a href="${esc(safeUrl(l.url))}"${EXT}>${esc(l.label)} →</a>`).join("");
  }

  // ---------- sections ----------
  header() {
    const d = this.d, L = this.L;
    const q = d.question ? `<div class="question">${this.paras(d.question)}</div>` : "";
    const notices = (d._notices || []).map((n) => `<div class="notice">${esc(n)}</div>`).join("");
    return `<header><div class="eyebrow">${esc(L.kicker)}</div><h1>${esc(d.title)}</h1>${q}` +
      `<div class="meta"><span>${esc(L.crVersion)} <b>${esc(d.crEffectiveDate || "?")}</b></span>` +
      `<span>${esc(L.generated)} <b>${esc(d.generatedAt || "")}</b></span></div>${notices}</header>`;
  }

  nav(present) {
    const N = this.L.nav;
    const items = present.map((k) =>
      `<li><a href="#${k}"${k === "community" ? ' class="unofficial-link"' : ""}>${esc(N[k])}</a></li>`).join("");
    return `<nav class="sections"><ul>${items}</ul></nav>`;
  }

  answer() {
    const lvl = (this.d.confidence || {}).level || "medium";
    return `<section id="answer"><h2>${esc(this.L.shortAnswer)}</h2><div class="verdict">` +
      `<div class="text">${this.paras(this.d.shortAnswer)}</div>` +
      `<span class="pill ${esc(lvl)}">${esc(this.L.confidence)}: ${esc(this.L[lvl] || lvl)}</span></div></section>`;
  }

  cardsSection() {
    const cards = this.d.cards || [];
    if (!cards.length) return "";
    const foot = this.d.allCardsLink
      ? `<p class="cards-foot"><a href="${esc(safeUrl(this.d.allCardsLink))}"${EXT}>${esc(this.L.allCards)} →</a></p>` : "";
    return `<section id="cards"><h2>${esc(this.L.cards)} <span class="count">${cards.length}</span></h2>` +
      `<div class="cards-grid">${cards.map((c) => this.cardSlot(c)).join("")}</div>${foot}</section>`;
  }

  rulesSection() {
    const rules = this.d.rules || [];
    if (!rules.length) return "";
    const rows = rules.map((r) =>
      `<div class="quote" id="rule-${esc(slug(r.id))}"><div class="key"><a href="${RULE_LINK}"${EXT}>${esc(r.id)}</a>` +
      `</div><div class="body">${this.ruleBody(r)}</div></div>`).join("");
    return `<section id="rules"><h2>${esc(this.L.rules)} <span class="count">${rules.length}</span></h2>${rows}</section>`;
  }

  rulingsSection() {
    const rulings = this.d.rulings || [];
    if (!rulings.length) return "";
    const groups = new Map();
    for (const r of rulings) {
      if (!groups.has(r.card)) groups.set(r.card, []);
      groups.get(r.card).push(r);
    }
    const out = [];
    for (const [cid, rs] of groups) {
      const c = this.cards.get(cid);
      const rows = rs.map((r) => {
        const links = r.links ? `<div class="pop-links">${Page.links(r.links)}</div>` : "";
        return `<div class="quote ruling" id="ruling-${esc(slug(r.id))}"><div class="key">` +
          `<span>${esc(r.date || "")}</span>${r.source ? this.rulingSrc(r) : ""}</div>` +
          `<div class="body">${this.rulingBody(r)}${links}</div></div>`;
      }).join("");
      out.push(`<div class="ruling-group"><h3>${esc(c ? c.name : cid)}</h3>${rows}</div>`);
    }
    return `<section id="rulings"><h2>${esc(this.L.rulings)} <span class="count">${rulings.length}</span></h2>${out.join("")}</section>`;
  }

  stepsSection() {
    const steps = this.d.steps || [];
    if (!steps.length) return "";
    const items = steps.map((s) => {
      const note = s.note ? `<div class="note">${this.inline(s.note)}</div>` : "";
      return `<li><div class="step">${this.paras(s.text)}${note}</div></li>`;
    }).join("");
    return `<section id="walkthrough"><h2>${esc(this.L.walkthrough)}</h2><ol class="steps">${items}</ol></section>`;
  }

  confidenceSection() {
    const c = this.d.confidence;
    if (!c) return "";
    const L = this.L;
    const panel = (title, items) => (items && items.length
      ? `<div class="panel"><h3>${esc(title)}</h3><ul>${items.map((i) => `<li>${this.inline(i)}</li>`).join("")}</ul></div>`
      : "");
    const lvl = c.level || "medium";
    return `<section id="confidence"><h2>${esc(L.confidence)} <span class="pill ${esc(lvl)}">${esc(L[lvl] || lvl)}</span></h2>` +
      `<div class="confidence">${panel(L.why, c.reasons)}${panel(L.assumptions, c.assumptions)}` +
      `${panel(L.notRetrieved, c.notRetrieved)}</div></section>`;
  }

  communitySection() {
    const r = this.d.reddit, L = this.L;
    if (!r) return "";
    const [cls, txt] = ({ yes: ["high", L.yes], partly: ["medium", L.partly], no: ["low", L.no] })[r.agreesWithOfficial]
      || ["", L.unknown];
    const threads = r.threads || [];
    let th;
    if (threads.length) {
      const lis = threads.map((t) => {
        const head = `<a href="${esc(safeUrl(t.url))}"${EXT}>${esc(t.title)}</a><span>${esc(t.subreddit || "")}</span>` +
          `<span>${esc(t.date || "")}</span>` +
          (t.comments != null ? `<span>${esc(t.comments)} ${esc(L.comments)}</span>` : "") +
          (t.judgeFlair ? '<span class="src">judge</span>' : "");
        const summ = t.summary ? `<div class="t-sum">${this.inline(t.summary)}</div>` : "";
        return `<li><div class="t-head">${head}</div>${summ}</li>`;
      });
      th = `<ul class="threads">${lis.join("")}</ul>`;
    } else {
      th = r.searched === false ? "" : `<p class="muted">${esc(L.noThreads)}</p>`;
    }
    const agree = threads.length ? `<div class="agree">${esc(L.agrees)} <span class="pill ${cls}">${esc(txt)}</span></div>` : "";
    const ops = r.opinions || [];
    const opsH = ops.length ? `<div class="eyebrow opinions-head">${esc(L.opinions)}</div><ul class="opinions">` +
      `${ops.map((o) => `<li>${this.inline(o)}</li>`).join("")}</ul>` : "";
    const notes = r.notes ? `<p class="muted notes">${this.inline(r.notes)}</p>` : "";
    const search = r.searchUrl ? `<p><a href="${esc(safeUrl(r.searchUrl))}"${EXT}>${esc(L.searchReddit)} →</a></p>` : "";
    return `<section id="community" class="community"><div class="eyebrow">${esc(L.communityKicker)}</div>` +
      `<h2>${esc(L.community)}</h2>${agree}${r.overview ? this.paras(r.overview) : ""}${opsH}${th}${notes}${search}</section>`;
  }

  footer() {
    const srcs = [this.S.sources];
    for (const c of this.d.cards || []) {
      if (c._state === "external" && c.source && !srcs.includes(c.source)) srcs.push(c.source);
    }
    return `<footer>${esc(this.L.footer)} <span class="mono">${esc(srcs.join(" · "))}</span>` +
      `<p class="attrib">${esc(this.S.attribution)}</p></footer>`;
  }

  // ---------- popovers (pre-rendered, inert until opened) ----------
  popover(kind, key) {
    const L = this.L, d = this.d;
    if (kind === "card") {
      const c = this.cards.get(key);
      const links = `<a href="${esc(safeUrl(c.scryfallUri || searchLink(c.name)))}"${EXT}>${esc(L.openOn)} Scryfall →</a>`;
      return `<div class="pop-head"><span class="pop-title">${esc(c.name)}</span><span class="pop-kind">${esc(L.card)}</span></div>` +
        `${this.cardSlot(c, false)}<div class="pop-links">${links}${Page.links(c.links)}</div>`;
    }
    if (kind === "rule") {
      const r = this.rules.get(key);
      return `<div class="pop-head"><span class="pop-title mono">${esc(r.id)}</span><span class="pop-kind">` +
        `${esc(L.rule)} · CR ${esc(d._crNow || d.crEffectiveDate || "")}</span></div>` +
        `<div class="pop-body">${this.ruleBody(r)}</div><div class="pop-links">` +
        `<a href="#rule-${esc(slug(r.id))}">↓ ${esc(L.rules)}</a><a href="${RULE_LINK}"${EXT}>magic.wizards.com →</a></div>`;
    }
    const r = this.rulings.get(key);
    const c = this.cards.get(r.card);
    const sc = c && c.scryfallUri ? `<a href="${esc(safeUrl(c.scryfallUri))}"${EXT}>Scryfall →</a>` : "";
    return `<div class="pop-head"><span class="pop-title">${esc(c ? c.name : r.card)}</span>` +
      `<span class="pop-kind">${esc(L.ruling)} · ${esc(r.date || "")}</span></div>${r.source ? this.rulingSrc(r) : ""}` +
      `<div class="pop-body pop-ruling">${this.rulingBody(r)}</div><div class="pop-links">` +
      `<a href="#ruling-${esc(slug(r.id))}">↓ ${esc(L.rulings)}</a>${Page.links(r.links)}${sc}</div>`;
  }

  render() {
    const sections = [
      ["answer", this.answer()], ["cards", this.cardsSection()], ["rules", this.rulesSection()],
      ["rulings", this.rulingsSection()], ["walkthrough", this.stepsSection()],
      ["confidence", this.confidenceSection()], ["community", this.communitySection()],
    ];
    const present = sections.filter(([, h]) => h).map(([k]) => k);
    const app = this.header() + this.nav(present) + sections.map(([, h]) => h).join("") + this.footer();
    const pops = this.used.map((k) => {
      const i = k.indexOf(":");
      return `<template data-pop="${esc(k)}">${this.popover(k.slice(0, i), k.slice(i + 1))}</template>`;
    }).join("");
    return { app, pops };
  }
}
