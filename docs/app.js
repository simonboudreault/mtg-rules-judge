// Boot: read the answer from the link, draw it at once from the link alone, then fill
// in rules (from this site's data) and cards and rulings (from Scryfall) as they arrive.

import { parseFragment, LinkError } from "./decode.js";
import { Page, esc, slug, searchLink } from "./render.js";
import { SITE, REDDIT_DEFAULT } from "./labels.js";
import { loadMeta, loadRules } from "./rules.js";
import { fetchCards, fetchRulings, imagesOf, h8, cardCanon } from "./scryfall.js";
import { fetchThreads } from "./reddit.js";

const SUPPORTED = [1];
const app = document.getElementById("app");
const pop = document.getElementById("pop");
const pops = document.getElementById("pops");
let vm = null;
let generation = 0; // a new link (hashchange) makes older async work stop drawing

const uiLang = () => (/^fr\b/i.test(navigator.language || "") ? "fr" : "en");
const quotePlus = (s) => encodeURIComponent(s).replace(/%20/g, "+");

// ---------------------------------------------------------------- view model

function viewModel(p) {
  const lang = p.lang === "fr" ? "fr" : "en";
  const cards = (Array.isArray(p.cards) ? p.cards : []).filter((c) => c && c.name).map((c) => (c.oid
    ? { id: c.id || slug(c.name), name: c.name, note: c.note, oracleId: c.oid, _h: c.h, _state: "loading",
        scryfallUri: searchLink(c.name) }
    : { ...c, id: c.id || slug(c.name), _state: "external" }));
  const names = cards.map((c) => c.name);
  let reddit = p.reddit;
  if (reddit === undefined) { // the default block, as build.py makes it
    reddit = {
      searched: false, threads: [], overview: REDDIT_DEFAULT[lang], agreesWithOfficial: "unknown",
      searchUrl: "https://www.reddit.com/r/mtgrules/search/?q=" + quotePlus(names.slice(0, 3).map((n) => `"${n}"`).join(" ")),
    };
  }
  if (reddit && typeof reddit === "object") { // no thread came with the answer: the page looks for some itself
    reddit = { ...reddit, _live: !(reddit.threads || []).length && names.length ? "loading" : undefined };
  }
  return {
    lang, title: p.title, question: p.question, shortAnswer: p.shortAnswer,
    confidence: p.confidence, steps: Array.isArray(p.steps) ? p.steps : [], reddit: reddit || null,
    crEffectiveDate: p.cr, generatedAt: p.at, cardDataDate: p.db,
    cards,
    rules: (Array.isArray(p.rules) ? p.rules : []).map((id) => ({ id: String(id), text: undefined })),
    rulings: (Array.isArray(p.rulings) ? p.rulings : []).filter((r) => r && r.id).map((r) => (r.text != null
      ? { ...r, _state: "ok", _web: true } // came with its own text: copied from the web, not from Scryfall
      : { id: r.id, card: r.card, date: r.d, _h: r.h, _state: "loading" })),
    allCardsLink: names.length
      ? "https://scryfall.com/search?q=" + quotePlus(names.map((n) => `!"${n}"`).join(" or ")) + "&unique=cards" : null,
    _notices: p._damaged ? [SITE[lang].damagedLink] : [],
  };
}

// ---------------------------------------------------------------- drawing

function draw() {
  const page = new Page(vm);
  const { app: html, pops: templates } = page.render();
  closePop();
  app.innerHTML = html;
  pops.innerHTML = templates;
  document.documentElement.lang = vm.lang;
  document.title = vm.title || "MTG rules answer";
  pop.dataset.pinHint = page.L.pinHint;
  setupNav();
}

// Threads arrive seconds after the rest: redraw their section alone, so an open popover stays open.
function drawCommunity() {
  const el = document.getElementById("community");
  if (!el) return;
  const t = document.createElement("template");
  t.innerHTML = new Page(vm).communitySection();
  if (t.content.firstElementChild) el.innerHTML = t.content.firstElementChild.innerHTML;
}

function message(kind) {
  const S = SITE[uiLang()];
  document.documentElement.lang = uiLang();
  document.title = S[kind + "Title"];
  app.innerHTML = `<header class="landing"><div class="eyebrow">MTG Rules Judge</div><h1>${esc(S[kind + "Title"])}</h1>` +
    `<div class="landing-body">${S[kind + "Html"]}</div></header>` +
    `<footer><p class="attrib">${esc(S.attribution)}</p></footer>`;
  pops.innerHTML = "";
}

// ---------------------------------------------------------------- data

async function hydrateRules(gen) {
  let meta = null;
  try { meta = await loadMeta(); } catch { /* rules show as unavailable */ }
  if (gen !== generation) return;
  if (meta && vm.crEffectiveDate && meta.crEffectiveDate && meta.crEffectiveDate !== vm.crEffectiveDate) {
    vm._crNow = meta.crEffectiveDate;
    vm._notices.push(SITE[vm.lang].rulesUpdated.replace("{now}", meta.crEffectiveDate));
  }
  const texts = await loadRules(vm.rules.map((r) => r.id), meta);
  if (gen !== generation) return;
  for (const r of vm.rules) r.text = texts.get(r.id) ?? null;
  draw();
}

async function safeHash(text) {
  try { return await h8(text); } catch { return null; } // crypto.subtle needs https or localhost
}

async function hydrateCards(gen) {
  if (!vm.cards.length) return;
  let found = null;
  try {
    found = await fetchCards(vm.cards.map((c) => (c.oracleId ? { key: c.id, oid: c.oracleId } : { key: c.id, name: c.name })));
  } catch { /* Scryfall unreachable */ }
  if (gen !== generation) return;
  if (!found) {
    for (const c of vm.cards) if (c._state === "loading") c._state = "unavailable";
    for (const r of vm.rulings) if (r._state === "loading") r._state = "unavailable";
    vm._notices.push(SITE[vm.lang].scryfallDown);
    draw();
    return;
  }
  for (const c of vm.cards) {
    const sf = found.get(c.id);
    if (!sf) {
      if (c._state === "loading") c._state = "unavailable";
      continue;
    }
    c._images = imagesOf(sf);
    c.scryfallUri = sf.scryfallUri;
    if (c._state === "external") continue; // its text came with the answer; Scryfall only adds the picture
    Object.assign(c, {
      manaCost: sf.manaCost, typeLine: sf.typeLine, oracleText: sf.oracleText, power: sf.power,
      toughness: sf.toughness, loyalty: sf.loyalty, defense: sf.defense, colors: sf.colors, faces: sf.faces,
      _sf: sf, _state: "ok",
    });
    if (c._h) {
      const now = await safeHash(cardCanon(c));
      c._changed = now !== null && now !== c._h;
    }
  }
  if (gen !== generation) return;
  draw();
  await hydrateRulings(gen);
}

async function hydrateRulings(gen) {
  const byCard = new Map();
  for (const r of vm.rulings) {
    if (r._state !== "loading") continue;
    if (!byCard.has(r.card)) byCard.set(r.card, []);
    byCard.get(r.card).push(r);
  }
  for (const [cid, refs] of byCard) {
    const card = vm.cards.find((c) => c.id === cid);
    let rows = null;
    if (card && card._sf) {
      try { rows = await fetchRulings(card._sf); } catch { /* left unavailable */ }
    }
    if (gen !== generation) return;
    if (!rows) {
      refs.forEach((r) => { r._state = "unavailable"; });
      continue;
    }
    const hashes = await Promise.all(rows.map((x) => safeHash(x.text || "")));
    for (const r of refs) {
      const exact = rows.find((x, i) => hashes[i] && hashes[i] === r._h);
      if (exact) {
        Object.assign(r, { text: exact.text, source: exact.source, date: exact.date, _state: "ok" });
        continue;
      }
      // Fall back on position, then date: ids are "<card>-<n>" in date order
      const n = Number((/-(\d+)$/.exec(r.id) || [])[1] || 0);
      const sameDate = rows.filter((x) => x.date === r.date);
      const pick = (rows[n - 1] && rows[n - 1].date === r.date ? rows[n - 1] : null) || (sameDate.length === 1 ? sameDate[0] : null);
      if (pick) Object.assign(r, { text: pick.text, source: pick.source, _state: "maybe" });
      else r._state = "unavailable";
    }
    draw();
  }
}

async function hydrateThreads(gen) {
  const r = vm.reddit;
  if (!r || r._live !== "loading") return;
  let threads = null;
  try { threads = await fetchThreads(vm.cards.map((c) => c.name)); } catch { /* the search link stays */ }
  if (gen !== generation) return;
  if (threads && threads.length) r.threads = threads;
  r._live = !threads ? "unavailable" : threads.length ? "ok" : "empty";
  drawCommunity();
}

// ---------------------------------------------------------------- boot

async function readPayload() {
  const fixture = new URLSearchParams(location.search).get("fixture");
  if (fixture && !location.hash) {
    const res = await fetch(`fixtures/${encodeURIComponent(fixture)}.json`, { cache: "no-cache" });
    if (!res.ok) throw new LinkError("fixture");
    return res.json();
  }
  return parseFragment(location.hash);
}

async function boot() {
  const gen = ++generation;
  let payload;
  try {
    payload = await readPayload();
  } catch (e) {
    message(e instanceof LinkError ? e.kind : "badLink");
    return;
  }
  if (gen !== generation) return;
  if (!payload) { message("landing"); return; }
  if (!SUPPORTED.includes(payload.v)) { message("tooNew"); return; }
  vm = viewModel(payload);
  draw();
  hydrateRules(gen);
  hydrateCards(gen);
  hydrateThreads(gen);
}

// Only answer links reload the page; "#rules" and other in-page anchors just scroll.
window.addEventListener("hashchange", () => { if (/^#\d+\./.test(location.hash) || !location.hash) boot(); });

// ---------------------------------------------------------------- popovers
// Copied from assets/answer-template.html: hover, focus, tap-to-pin, keyboard.
// Each popover's content is pre-rendered in a <template data-pop="kind:key">.

const HOVER_MS = 120, HIDE_MS = 220;
let current = null, pinned = false, showTimer = null, hideTimer = null;

function place(trigger) {
  const r = trigger.getBoundingClientRect();
  const pw = pop.offsetWidth, ph = pop.offsetHeight, vw = window.innerWidth, vh = window.innerHeight;
  let top = r.bottom + 8;
  if (top + ph > vh - 8 && r.top - ph - 8 > 8) top = r.top - ph - 8;
  top = Math.max(8, Math.min(top, vh - ph - 8));
  let left = r.left + r.width / 2 - pw / 2;
  left = Math.max(12, Math.min(left, vw - pw - 12));
  pop.style.top = top + "px";
  pop.style.left = left + "px";
}
function open(trigger) {
  const tpl = pops.querySelector('template[data-pop="' + CSS.escape(trigger.dataset.pop) + '"]');
  if (!tpl) return;
  clearTimeout(hideTimer);
  if (current && current !== trigger) current.setAttribute("aria-expanded", "false");
  current = trigger;
  pop.innerHTML = tpl.innerHTML + '<div class="pin-hint"></div>';
  pop.lastChild.textContent = pop.dataset.pinHint || "";
  pop.classList.add("show");
  trigger.setAttribute("aria-expanded", "true");
  place(trigger);
}
function closePop() {
  clearTimeout(showTimer); clearTimeout(hideTimer);
  pop.classList.remove("show"); pinned = false;
  if (current) current.setAttribute("aria-expanded", "false");
  current = null;
}
function scheduleHide() { if (pinned) return; clearTimeout(hideTimer); hideTimer = setTimeout(closePop, HIDE_MS); }

document.addEventListener("pointerover", (e) => {
  const t = e.target.closest(".ref[data-pop]");
  if (!t || e.pointerType === "touch") return;
  clearTimeout(hideTimer);
  if (pinned && current !== t) return;
  clearTimeout(showTimer);
  showTimer = setTimeout(() => open(t), HOVER_MS);
});
document.addEventListener("pointerout", (e) => {
  const t = e.target.closest(".ref[data-pop]");
  if (t) { clearTimeout(showTimer); if (!pop.contains(e.relatedTarget)) scheduleHide(); }
});
pop.addEventListener("pointerenter", () => clearTimeout(hideTimer));
pop.addEventListener("pointerleave", () => scheduleHide());
document.addEventListener("click", (e) => {
  const flip = e.target.closest("[data-flip]");
  if (flip) { // double-faced card: show the other face's image
    const img = flip.parentElement.querySelector("img.art");
    if (img) {
      const images = JSON.parse(img.dataset.images || "[]");
      const i = (Number(img.dataset.i) + 1) % images.length;
      img.dataset.i = String(i);
      img.src = images[i];
    }
    return;
  }
  const t = e.target.closest(".ref[data-pop]");
  if (t) {
    e.preventDefault();
    if (current === t && pinned) closePop(); else { open(t); pinned = true; }
    return;
  }
  if (!pop.contains(e.target)) closePop();
});
document.addEventListener("focusin", (e) => { const t = e.target.closest(".ref[data-pop]"); if (t && !pinned) open(t); });
document.addEventListener("focusout", (e) => { if (e.target.closest(".ref[data-pop]") && !pinned) scheduleHide(); });
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") { closePop(); return; }
  const t = (e.key === "Enter" || e.key === " ") && e.target.closest && e.target.closest(".ref[data-pop]");
  if (t) { // refs are spans with role="button": give them a button's keys
    e.preventDefault();
    if (current === t && pinned) closePop(); else { open(t); pinned = true; }
  }
});
window.addEventListener("scroll", () => { if (current) place(current); }, { passive: true });
window.addEventListener("resize", () => { if (current) place(current); });
// A card image that fails to load falls back to the text frame underneath.
document.addEventListener("error", (e) => {
  const img = e.target;
  if (img instanceof HTMLImageElement && img.classList.contains("art")) {
    img.closest(".cardframe")?.classList.remove("has-image");
    img.parentElement?.parentElement?.querySelector("[data-flip]")?.remove();
    img.remove();
  }
}, true);

// Highlight the section in view in the sticky nav.
let observer = null;
function setupNav() {
  if (observer) observer.disconnect();
  if (!("IntersectionObserver" in window)) return;
  const links = [...document.querySelectorAll("nav.sections a")];
  const secs = links.map((a) => document.querySelector(a.getAttribute("href"))).filter(Boolean);
  observer = new IntersectionObserver((entries) => {
    entries.forEach((en) => {
      if (en.isIntersecting) links.forEach((a) => a.classList.toggle("active", a.getAttribute("href") === "#" + en.target.id));
    });
  }, { rootMargin: "-20% 0px -70% 0px" });
  secs.forEach((s) => observer.observe(s));
}

boot();
