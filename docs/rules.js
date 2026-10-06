// Comprehensive Rules text, published by tools/build_site_data.py in the same commit
// as every plugin data update: data/meta.json and data/rules/<SSS>.json.

let metaPromise = null;

export function loadMeta() {
  if (!metaPromise) {
    metaPromise = fetch("data/meta.json", { cache: "no-cache" }).then((r) => {
      if (!r.ok) throw new Error("meta.json " + r.status);
      return r.json();
    });
    metaPromise.catch(() => { metaPromise = null; }); // retry next time
  }
  return metaPromise;
}

/** ids: rule numbers ("601.2f", "613", "6"). Returns Map id -> text, or null when unavailable. */
export async function loadRules(ids, meta) {
  const v = encodeURIComponent((meta && meta.crEffectiveIso) || "");
  const sections = [...new Set(ids.filter((id) => /^\d{3}/.test(id)).map((id) => id.slice(0, 3)))];
  const files = await Promise.all(sections.map((s) =>
    fetch(`data/rules/${s}.json?v=${v}`).then((r) => (r.ok ? r.json() : null)).catch(() => null)));
  const bySection = Object.fromEntries(sections.map((s, i) => [s, files[i]]));
  const out = new Map();
  for (const id of ids) {
    if (/^\d$/.test(id)) {
      out.set(id, (meta && meta.chapters && meta.chapters[id]) || null);
      continue;
    }
    const file = bySection[id.slice(0, 3)];
    if (!file) out.set(id, null);
    else if (/^\d{3}$/.test(id)) out.set(id, file.title || null);
    else out.set(id, (file.rules && file.rules[id]) || null);
  }
  return out;
}
