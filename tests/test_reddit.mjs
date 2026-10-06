// The viewer's thread finder (docs/reddit.js): the search text it sends and how it reads the reply.
// No network here. Run by tests/test_share.py when node is installed, or directly:  node tests/test_reddit.mjs
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
// docs/ has no package.json, so older node versions would load reddit.js as CommonJS: import a .mjs copy.
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "mtgj-"));
fs.copyFileSync(path.join(here, "..", "docs", "reddit.js"), path.join(tmp, "reddit.mjs"));
const { threadQuery, threadsFrom, fetchThreads } = await import(pathToFileURL(path.join(tmp, "reddit.mjs")).href);

// each name an exact phrase; a two-faced card is searched by its front face
assert.equal(threadQuery(["Blood Moon", "Urza's Saga"]), `"Blood Moon" "Urza's Saga"`);
assert.equal(threadQuery(["Fable of the Mirror-Breaker // Reflection of Kiki-Jiki"]), `"Fable of the Mirror-Breaker"`);
assert.equal(threadQuery(['Say "hi"']), `"Say hi"`);

const post = (over) => ({
  title: "Urza&#39;s Saga &amp; Blood Moon", permalink: "/r/mtgrules/comments/1mncgks/urzas_saga_and_blood_moon/",
  subreddit: "mtgrules", created_utc: 1754870400, num_comments: 3, removed_by_category: null, ...over,
});
const reply = { data: [
  post({ title: "Older", created_utc: 1689379200, permalink: "/r/mtgrules/comments/150vtbg/older/" }),
  post(),
  post({ title: "Removed by a moderator", removed_by_category: "moderator" }),
  post({ title: "Link that leaves Reddit", permalink: "https://evil.example/r/x/comments/1/" }),
  post({ title: "" }),
  null,
] };
assert.deepEqual(threadsFrom(reply), [
  { title: "Urza's Saga & Blood Moon", url: "https://www.reddit.com/r/mtgrules/comments/1mncgks/urzas_saga_and_blood_moon/",
    subreddit: "r/mtgrules", date: "2025-08-11" },
  { title: "Older", url: "https://www.reddit.com/r/mtgrules/comments/150vtbg/older/", subreddit: "r/mtgrules", date: "2023-07-15" },
]);
assert.deepEqual(threadsFrom({ data: null }), []);
assert.deepEqual(threadsFrom(null), []);
assert.equal(threadsFrom({ data: Array.from({ length: 20 }, (_, i) => post({ created_utc: 1700000000 + i })) }).length, 6);

// three cards and no thread naming them all: ask again with the first two
const asked = [];
const realFetch = globalThis.fetch;
globalThis.fetch = async (url) => {
  const q = new URL(url).searchParams.get("q");
  asked.push(q);
  return { ok: true, json: async () => (q === `"A" "B"` ? { data: [post()] } : { data: [] }) };
};
try {
  assert.equal((await fetchThreads(["A", "B", "C", "D"])).length, 1);
  assert.deepEqual(asked, [`"A" "B" "C"`, `"A" "B"`]);
  assert.deepEqual(await fetchThreads(["X", "Y"]), []);
  assert.deepEqual(asked.slice(2), [`"X" "Y"`]);
  globalThis.fetch = async () => ({ ok: false, status: 502 });
  await assert.rejects(fetchThreads(["A", "B"]));
} finally {
  globalThis.fetch = realFetch;
}
fs.rmSync(tmp, { recursive: true, force: true });
