// Read an answer out of the URL fragment: "#1.<base64url(zlib(json))>".
// The format is defined in plugins/mtg-rules-judge/skills/mtg-rules-judge/references/share-payload.md
// and produced by scripts/share.py (encode_fragment / decode_fragment).

export const ENCODING_VERSION = "1";

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
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("deflate"));
  return new Response(stream).text();
}

/** Returns null for an empty fragment, the payload object otherwise. Throws LinkError. */
export async function parseFragment(hash) {
  const frag = decodeURIComponent(String(hash || "").replace(/^#/, "")).trim();
  if (!frag) return null;
  const m = /^(\d+)\.([A-Za-z0-9_-]+)$/.exec(frag);
  if (!m) throw new LinkError("badLink", "not an answer link");
  if (m[1] !== ENCODING_VERSION) throw new LinkError("tooNew", "link format " + m[1]);
  if (typeof DecompressionStream === "undefined") throw new LinkError("oldBrowser");
  let payload;
  try {
    payload = JSON.parse(await inflate(base64urlToBytes(m[2])));
  } catch (e) {
    throw new LinkError("badLink", String(e));
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) throw new LinkError("badLink", "not an object");
  return payload;
}
