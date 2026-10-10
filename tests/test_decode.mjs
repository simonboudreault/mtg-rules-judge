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
const { parseFragment, LinkError, checksum } = await import(pathToFileURL(path.join(tmp, "decode.mjs")).href);

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
  assert.equal(altered._truncated, undefined, name + " altered is not cut");
  // cut short, as when the link is clicked while the reply is still streaming: the page shows what it has
  // and says the link isn't complete, wherever the cut lands (inside a "!" code, a ruling field, the checksum)
  const cuts = [readable.lastIndexOf("=z"), readable.length - 2, readable.indexOf("!") + 1,
                readable.indexOf("=g") + 4, readable.indexOf("=t") + 3].filter((at) => at > 4);
  assert.ok(cuts.length >= 4, name + " has enough cut points");
  for (const at of cuts) {
    const cut = await parseFragment("#" + readable.slice(0, at));
    assert.equal(cut._truncated, true, `${name} cut at ${at}`);
    assert.equal(cut._damaged, undefined, `${name} cut at ${at} is not altered`);
    assert.equal(cut.lang, want.lang, `${name} cut at ${at} keeps the language`);
  }
  const whole = await parseFragment("#" + readable.slice(0, readable.lastIndexOf("=z")));
  assert.equal(whole.title, want.title, name + " cut before the checksum keeps every field");
  assert.equal(whole.steps.length, want.steps.length, name + " cut before the checksum keeps every field");
}
// a cut inside a field drops that field, nothing else
assert.deepEqual(await parseFragment("#2.en=tA!"), { v: 1, lang: "en", steps: [], cards: [], rules: [], rulings: [], _truncated: true });
assert.equal((await parseFragment("#2.en=tAb=qCd!")).title, "Ab");

const badRuling = "2.en=g1-1,2020-01-01,abcd1234";
for (const bad of ["#3.abc", "#nope", "#2.e", "#" + badRuling + "=z" + checksum(badRuling), "#1.!!!"]) {
  await assert.rejects(parseFragment(bad), LinkError, bad);
}
assert.equal(await parseFragment(""), null);
fs.rmSync(tmp, { recursive: true, force: true });
console.log(`decode.js: ${names.length} fixtures, both formats`);
