// Read an answer out of the URL fragment. Two formats, both defined in
// plugins/mtg-rules-judge/skills/mtg-rules-judge/references/share-payload.md and produced by scripts/share.py:
//   "#1.<base64url(zlib(json))>"   compressed (encode_fragment / decode_compressed)
//   "#2.<lang>=t<title>=q…=z<check>" readable  (encode_readable / decode_readable)

export const ENCODING_VERSION = "1";
export const READABLE_VERSION = "2";

export class LinkError extends Error {
  constructor(kind, detail) {
    super(detail || kind);
    this.kind = kind; // "badLink" | "tooNew" | "oldBrowser"
  }
}

function base64urlToBytes(s) {
  const b64 = s.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((s.length + 3) % 4);
  const bin = atob(b64); // throws on bad input
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

async function inflate(bytes) {
  // "deflate" in the Compression Streams API is zlib-wrapped data, which is what
  // Python's zlib.compress writes; its Adler-32 checksum catches damaged links.
  if (typeof DecompressionStream === "undefined") throw new LinkError("oldBrowser");
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("deflate"));
  return new Response(stream).text();
}

// ---------------------------------------------------------------- readable format

const CODES = { // the character after "!" -> what it stands for (share.py _CODES)
  r: "[[rule:", c: "[[card:", g: "[[ruling:", l: "[[link:", z: "]]", y: "[[",
  b: "**", i: "*", p: "(", P: ")", a: "'", A: "’", q: '"',
  m: "{", M: "}", t: "+", e: "=", x: "!", w: "?", N: "\n",
  s: " ", S: " ", d: "«", D: "»", k: "—", K: "–", E: "…",
};
const CONF_LISTS = { r: "reasons", u: "assumptions", n: "notRetrieved" };
const slug = (s) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");

function unesc(s) {
  let out = "";
  for (let i = 0; i < s.length;) {
    const ch = s[i];
    if (ch === "+") { out += " "; i += 1; continue; }
    if (ch !== "!") { out += ch; i += 1; continue; }
    const code = s[i + 1];
    if (code === "u") {
      const j = s.indexOf(";", i + 2);
      const cp = j < 0 ? NaN : parseInt(s.slice(i + 2, j), 16);
      if (!(cp >= 0 && cp <= 0x10ffff)) throw new Error("bad !u code");
      out += String.fromCodePoint(cp);
      i = j + 1;
    } else {
      if (!Object.hasOwn(CODES, code)) throw new Error("unknown code !" + code);
      out += CODES[code];
      i += 2;
    }
  }
  return out;
}

function crc32(bytes) {
  let c = ~0;
  for (const b of bytes) {
    c ^= b;
    for (let k = 0; k < 8; k++) c = (c >>> 1) ^ (0xedb88320 & -(c & 1));
  }
  return ~c >>> 0;
}

/** 4 hex digits over everything before "=z" (share.py _check). */
export function checksum(head) {
  return (crc32(new TextEncoder().encode(head.normalize("NFC"))) & 0xffff).toString(16).padStart(4, "0");
}

async function parseReadable(frag) {
  // "=z" + 4 hex digits end a complete link. Without them the link was cut short (clicked while the
  // reply was still streaming, or copied in part): the last, partial field is dropped and the page
  // shows the rest, saying so. With them but wrong, a character was changed: the page says that instead.
  const end = /=z([0-9a-f]{4})$/.exec(frag);
  let head, damaged = false, truncated = false;
  if (end) {
    head = frag.slice(0, end.index);
    damaged = end[1] !== checksum(head);
  } else {
    truncated = true;
    const last = frag.lastIndexOf("=");
    head = last < 0 ? frag : frag.slice(0, last);
  }
  const [lang, ...parts] = head.slice(READABLE_VERSION.length + 1).split("=");
  if (truncated && !/^[a-z]{2}$/.test(lang)) throw new Error("cut before the language");
  const p = { v: 1, lang: unesc(lang), steps: [], cards: [], rules: [], rulings: [] };
  const conf = () => (p.confidence ||= { reasons: [], assumptions: [], notRetrieved: [] });
  const last = (list) => {
    if (!list.length) throw new Error("field out of place");
    return list[list.length - 1];
  };
  const refs = [];
  let extra = {};
  for (const part of parts) {
    const tag = part[0], v = part.slice(1);
    if (tag === "t") p.title = unesc(v);
    else if (tag === "q") p.question = unesc(v);
    else if (tag === "a") p.shortAnswer = unesc(v);
    else if (tag === "c") conf().level = unesc(v);
    else if (Object.hasOwn(CONF_LISTS, tag)) conf()[CONF_LISTS[tag]].push(unesc(v));
    else if (tag === "s") p.steps.push({ text: unesc(v) });
    else if (tag === "o") last(p.steps).note = unesc(v);
    else if (tag === "k") p.cards.push({ id: slug(unesc(v)), name: unesc(v) });
    else if (tag === "i") last(p.cards).oid = v;
    else if (tag === "h") last(p.cards).h = v;
    else if (tag === "m") last(p.cards).note = unesc(v);
    else if (tag === "j") last(p.cards).id = unesc(v);
    else if (tag === "l") p.rules = v ? v.split(",").map(unesc) : [];
    else if (tag === "g") refs.push(v.split(","));
    else if (tag === "d") p.cr = unesc(v);
    else if (tag === "e") p.at = unesc(v);
    else if (tag === "f") p.db = unesc(v);
    else if (tag === "y") p.reddit = false;
    else if (tag === "x") extra = JSON.parse(await inflate(base64urlToBytes(v.replace(/\./g, "_"))));
    // any other tag: written by a newer version of the plugin, ignored
  }
  const ids = p.cards.map((c) => c.id);
  let lastDate = null;
  for (const f of refs) {
    if (f.length < 3) throw new Error("bad ruling reference");
    const d = f[1] || lastDate;
    lastDate = d;
    const short = /^(\d+)-(\d+)$/.exec(f[0]);
    if (short && !ids[short[1] - 1]) throw new Error("ruling for a missing card");
    const card = short ? ids[short[1] - 1] : (f[3] || f[0].replace(/-[^-]*$/, ""));
    p.rulings.push({ id: short ? `${card}-${short[2]}` : f[0], card, d, h: f[2] });
  }
  for (const key of ["cards", "rulings"]) {
    for (const [i, obj] of extra[key] || []) p[key].splice(i, 0, obj);
  }
  if ("reddit" in extra) p.reddit = extra.reddit;
  if (damaged) p._damaged = true;
  if (truncated) p._truncated = true;
  return p;
}

// ---------------------------------------------------------------- entry point

/** Returns null for an empty fragment, the payload object otherwise. Throws LinkError. */
export async function parseFragment(hash) {
  let frag;
  try {
    frag = decodeURIComponent(String(hash || "").replace(/^#/, "")).trim();
  } catch (e) {
    throw new LinkError("badLink", String(e));
  }
  if (!frag) return null;
  const m = /^(\d+)\.(.+)$/s.exec(frag);
  if (!m) throw new LinkError("badLink", "not an answer link");
  let payload;
  try {
    if (m[1] === READABLE_VERSION) {
      payload = await parseReadable(frag);
    } else if (m[1] === ENCODING_VERSION) {
      if (!/^[A-Za-z0-9_-]+$/.test(m[2])) throw new LinkError("badLink", "not an answer link");
      payload = JSON.parse(await inflate(base64urlToBytes(m[2])));
    } else {
      throw new LinkError("tooNew", "link format " + m[1]);
    }
  } catch (e) {
    throw e instanceof LinkError ? e : new LinkError("badLink", String(e));
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) throw new LinkError("badLink", "not an object");
  return payload;
}
