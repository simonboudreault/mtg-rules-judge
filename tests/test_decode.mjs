// The viewer's decoder (docs/decode.js) must read both link formats exactly as share.py wrote them.
// Run by tests/test_share.py when node is installed, or directly:  node tests/test_decode.mjs
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const fix = path.join(here, "fixtures");
// docs/ has no package.json, so older node versions would load decode.js as CommonJS: import a .mjs copy.
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "mtgj-"));
fs.copyFileSync(path.join(here, "..", "docs", "decode.js"), path.join(tmp, "decode.mjs"));
const { parseFragment, LinkError } = await import(pathToFileURL(path.join(tmp, "decode.mjs")).href);

const read = (name) => fs.readFileSync(path.join(fix, name), "utf8").trim();
const names = fs.readdirSync(fix).filter((f) => f.endsWith(".share.json")).map((f) => f.slice(0, -11));
assert.ok(names.length >= 3);

for (const name of names) {
  const want = JSON.parse(read(name + ".share.json"));
  const readable = read(name + ".readable.txt");
  assert.deepEqual(await parseFragment("#" + read(name + ".fragment.txt")), want, name + " compressed");
  assert.deepEqual(await parseFragment("#" + readable), want, name + " readable");
  // what a browser hands back: accented letters and some punctuation percent-encoded
  assert.deepEqual(await parseFragment("#" + encodeURIComponent(readable)), want, name + " percent-encoded");

  // one changed letter: the page still shows, flagged as altered
  const i = readable.indexOf("=t") + 3;
  const altered = await parseFragment("#" + readable.slice(0, i) + (readable[i] === "x" ? "y" : "x") + readable.slice(i + 1));
  assert.equal(altered._damaged, true, name + " altered");
  // cut short (no checksum): same
  assert.equal((await parseFragment("#" + readable.slice(0, readable.lastIndexOf("=z"))))._damaged, true, name + " cut");
}

for (const bad of ["#3.abc", "#nope", "#2.en=tA!", "#2.en=g1-1,2020-01-01,abcd1234", "#1.!!!"]) {
  await assert.rejects(parseFragment(bad), LinkError, bad);
}
assert.equal(await parseFragment(""), null);
fs.rmSync(tmp, { recursive: true, force: true });
console.log(`decode.js: ${names.length} fixtures, both formats`);
