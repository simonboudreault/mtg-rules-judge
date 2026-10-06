// Threads from r/mtgrules that name the answer's cards, for the community section.
// Reddit refuses requests from other sites, so they come from PullPush, a public archive
// of Reddit that allows browser requests. One GET per answer (two when three cards
// match nothing), cached in localStorage for a day.

const API = "https://api.pullpush.io/reddit/search/submission/";
const TTL = 24 * 3600 * 1000;
const PREFIX = "mtgjv1:rd:";
const TIMEOUT_MS = 15000; // PullPush often takes 4-5 s
const MAX = 6;

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

/** The search text: every card name as an exact phrase (the front face of a two-faced card). */
export function threadQuery(names) {
  return names.map((n) => `"${String(n).split(" // ")[0].replace(/"/g, "")}"`).join(" ");
}

const ENTITIES = { amp: "&", lt: "<", gt: ">", quot: '"', "#39": "'" };
const plain = (s) => String(s).replace(/&(amp|lt|gt|quot|#39);/g, (m, k) => ENTITIES[k]);

/** PullPush reply -> threads shaped like the answer's own (references/answer-schema.md), newest first. */
export function threadsFrom(json) {
  const rows = Array.isArray(json && json.data) ? json.data : [];
  return rows
    .filter((r) => r && r.title && /^\/r\/[^/]+\/comments\//.test(r.permalink || "") && !r.removed_by_category)
    .sort((a, b) => (b.created_utc || 0) - (a.created_utc || 0))
    .slice(0, MAX)
    .map((r) => ({
      title: plain(r.title),
      url: "https://www.reddit.com" + r.permalink,
      subreddit: "r/" + (r.subreddit || "mtgrules"),
      date: r.created_utc ? new Date(r.created_utc * 1000).toISOString().slice(0, 10) : "",
      // no comment count: the archive keeps the one from the day the thread was posted
    }));
}

async function search(q) {
  const hit = cacheGet(q.toLowerCase());
  if (hit) return hit;
  const url = `${API}?subreddit=mtgrules&size=25&q=${encodeURIComponent(q)}`;
  const res = await fetch(url, { signal: AbortSignal.timeout(TIMEOUT_MS) });
  if (!res.ok) throw new Error("PullPush " + res.status);
  const threads = threadsFrom(await res.json());
  cacheSet(q.toLowerCase(), threads);
  return threads;
}

/** Threads naming the first three cards, or the first two when no thread names all three. Throws if PullPush is unreachable. */
export async function fetchThreads(names) {
  const tries = [names.slice(0, 3)];
  if (names.length > 2) tries.push(names.slice(0, 2));
  for (const group of tries) {
    const threads = await search(threadQuery(group));
    if (threads.length) return threads;
  }
  return [];
}
