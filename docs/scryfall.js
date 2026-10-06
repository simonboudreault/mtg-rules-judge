// Card text, images and rulings from Scryfall's API, which allows browser requests.
// One POST for all cards, then one GET per card whose rulings are cited. Responses are
// cached in localStorage for a week, so reopening a link costs no request at all.

const API = "https://api.scryfall.com";
const TTL = 7 * 24 * 3600 * 1000;
const PREFIX = "mtgjv1:";
const HEADERS = { Accept: "application/json" };

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let lastRequest = 0;
async function polite() { // Scryfall asks for 50–100 ms between requests
  const wait = lastRequest + 100 - Date.now();
  if (wait > 0) await sleep(wait);
  lastRequest = Date.now();
}

function cacheGet(key) {
  try {
    const v = JSON.parse(localStorage.getItem(PREFIX + key));
    if (v && Date.now() - v.t < TTL) return v.d;
  } catch { /* private mode, bad JSON: treat as a miss */ }
  return null;
}
function cacheSet(key, data) {
  try { localStorage.setItem(PREFIX + key, JSON.stringify({ t: Date.now(), d: data })); } catch { /* full or blocked */ }
}

function face(f) {
  return {
    name: f.name, manaCost: f.mana_cost, typeLine: f.type_line, oracleText: f.oracle_text,
    power: f.power, toughness: f.toughness, loyalty: f.loyalty, defense: f.defense,
    image: f.image_uris && f.image_uris.normal,
  };
}

/** Scryfall card -> the fields the page needs (same names as the answer data). */
function slim(sf) {
  const faces = sf.card_faces && sf.card_faces.length ? sf.card_faces : null;
  return {
    scryfallId: sf.id,
    oracleId: sf.oracle_id || (faces && faces[0].oracle_id),
    name: sf.name, layout: sf.layout,
    manaCost: sf.mana_cost, typeLine: sf.type_line || (faces && faces[0].type_line), oracleText: sf.oracle_text,
    power: sf.power, toughness: sf.toughness, loyalty: sf.loyalty, defense: sf.defense,
    colors: sf.colors || (faces && faces[0].colors) || [],
    faces: faces ? faces.map(face) : undefined,
    image: sf.image_uris && sf.image_uris.normal,
    scryfallUri: sf.scryfall_uri, rulingsUri: sf.rulings_uri,
  };
}

function sameName(card, name) {
  const n = name.toLowerCase();
  return card.name.toLowerCase() === n || (card.faces || []).some((f) => (f.name || "").toLowerCase() === n);
}

/** reqs: [{key, oid} | {key, name}]. Returns Map key -> card or null. Throws if Scryfall is unreachable. */
export async function fetchCards(reqs) {
  const out = new Map();
  const need = [];
  for (const r of reqs) {
    const ck = r.oid ? "o:" + r.oid : "n:" + r.name.toLowerCase();
    const hit = cacheGet(ck);
    if (hit) out.set(r.key, hit);
    else need.push({ ...r, ck });
  }
  for (let i = 0; i < need.length; i += 75) {
    const chunk = need.slice(i, i + 75);
    await polite();
    const res = await fetch(API + "/cards/collection", {
      method: "POST",
      headers: { ...HEADERS, "Content-Type": "application/json" },
      body: JSON.stringify({ identifiers: chunk.map((r) => (r.oid ? { oracle_id: r.oid } : { name: r.name })) }),
    });
    if (!res.ok) throw new Error("Scryfall " + res.status);
    const found = ((await res.json()).data || []).map(slim);
    for (const r of chunk) {
      const card = r.oid ? found.find((c) => c.oracleId === r.oid) : found.find((c) => sameName(c, r.name));
      out.set(r.key, card || null);
      if (card) cacheSet(r.ck, card);
    }
  }
  return out;
}

/** A card's rulings: [{date, source, text}] in Scryfall's order. */
export async function fetchRulings(card) {
  const ck = "r:" + card.oracleId;
  const hit = cacheGet(ck);
  if (hit) return hit;
  await polite();
  const res = await fetch(card.rulingsUri || `${API}/cards/${card.scryfallId}/rulings`, { headers: HEADERS });
  if (!res.ok) throw new Error("Scryfall rulings " + res.status);
  const rows = ((await res.json()).data || []).map((r) => ({ date: r.published_at, source: r.source, text: r.comment }));
  cacheSet(ck, rows);
  return rows;
}

export function imagesOf(card) {
  const faceImages = (card.faces || []).map((f) => f.image).filter(Boolean);
  if (faceImages.length) return faceImages;
  return card.image ? [card.image] : [];
}

// ---- hashes: identical to share.py card_hash / ruling_hash ----

export async function h8(text) {
  const buf = await crypto.subtle.digest("SHA-1", new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].slice(0, 4).map((b) => b.toString(16).padStart(2, "0")).join("");
}

export function cardCanon(card) {
  if (card.faces && card.faces.length) return card.faces.map((f) => f.oracleText || "").join("\n//\n");
  return card.oracleText || "";
}
