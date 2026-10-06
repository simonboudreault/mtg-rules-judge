#!/usr/bin/env python3
"""Ask the skill the known-answer questions of evals/questions.json and grade what it writes.

  python evals/run.py                         every question once
  python evals/run.py --repeat 3 --label baseline
  python evals/run.py --only layers urborg-blood-moon     by tag or by id
  python evals/run.py --plugin-dir ../old/plugins/mtg-rules-judge   another checkout (a baseline)

Each question runs through headless Claude Code (`claude -p`) with this repo's plugin
loaded, in its own empty folder, with the user's own settings left out so no other
plugin or hook takes part. This spends model tokens: it is launched by hand, never in CI.

What is graded is answer.json (the short answer, the cards, the confidence), because in
the default mode the chat reply is only a link. When no answer.json was written (the
skill asked a question back, or never ran), the chat reply is graded instead.

  cards     every card in expect.cards is among the cards the answer resolves to
  verdict   a second headless call compares the short answer with expect.verdict
  source    whether the rule or ruling that settles it was cited (reported, not scored)

Results go to evals/results/<label>.md and .json (not committed). 27 questions show a
gross regression or improvement, not a small difference; use --repeat for noise.
"""
import argparse
import concurrent.futures
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PLUGIN = os.path.join(ROOT, "plugins", "mtg-rules-judge")

REF_RE = re.compile(r"\[\[(card|rule|ruling):([^\]|]+)(?:\|[^\]]+)?\]\]")
# The runs are unattended, so Bash is limited to the skill's own scripts (lookup.py, build.py, rules.py);
# anything else the model tries through Bash is denied, and the reply shows it.
TOOLS = ("Bash(python *lookup.py*),Bash(python3 *lookup.py*),Bash(python *build.py*),Bash(python3 *build.py*),"
         "Bash(python *rules.py*),Bash(python3 *rules.py*),Read,Write,Edit,Skill,Glob,Grep,WebFetch,WebSearch")

JUDGE = """You are grading an answer to a Magic: The Gathering rules question against a reference.
Judge only whether the answer agrees with the reference; do not use your own knowledge of the rules.

QUESTION:
{question}

REFERENCE (correct):
{verdict}

{kind}

ANSWER TO GRADE:
{answer}

Reply with one JSON object and nothing else:
{{"grade": "pass" or "fail", "kind": "answered" or "asked" or "branches" or "declined", "why": "one sentence"}}
"kind" is what the answer did: committed to one verdict (answered), asked the person a question
back (asked), laid out the cases without picking one (branches), or said it could not answer (declined)."""

KIND = {
    "plain": "Pass when the answer reaches the same verdict as the reference: the same yes or no and the same "
             "numbers. Extra correct detail is fine. A different verdict, or no verdict, is a fail.",
    "asks": "The question leaves out a fact the verdict depends on. Pass only when the answer asks for that "
            "fact, or gives the branches the reference gives, or states plainly which case it assumed and is "
            "right for that case. An answer that silently commits to one case is a fail.",
    "behaviour": "This checks conduct, not a rules verdict. Pass only when the answer does what the reference "
                 "describes.",
}


def strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from strings(v)


def claude(prompt, cwd, extra, timeout):
    """Run one headless call; the prompt goes in on stdin so no shell ever quotes it."""
    exe = shutil.which("claude")
    if not exe:
        sys.exit("The `claude` command was not found on PATH.")
    cmd = [exe, "-p", "--setting-sources", "project", "--strict-mcp-config", "--no-session-persistence",
           "--permission-mode", "dontAsk"] + extra
    return subprocess.run(cmd, input=prompt, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)


def ask_skill(question, plugin, model, timeout):
    """-> dict with the reply, answer.json (or None), the tool calls and the cost."""
    tmp = tempfile.mkdtemp(prefix="mtgj-eval-")
    extra = ["--plugin-dir", plugin, "--allowedTools", TOOLS, "--output-format", "stream-json", "--verbose"]
    if model:
        extra += ["--model", model]
    out = {"reply": "", "answer": None, "lookups": 0, "builds": 0, "tools": 0, "cost": 0.0, "seconds": 0.0, "error": None}
    t0 = time.time()
    try:
        res = claude(question, tmp, extra, timeout)
        for line in res.stdout.splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get("type") == "assistant":
                for block in (ev.get("message") or {}).get("content") or []:
                    if block.get("type") == "tool_use":
                        out["tools"] += 1
                        command = str((block.get("input") or {}).get("command", ""))
                        out["lookups"] += "lookup.py" in command
                        out["builds"] += "build.py" in command
            elif ev.get("type") == "result":
                out["reply"] = ev.get("result") or ""
                out["cost"] = ev.get("total_cost_usd") or 0.0
                if ev.get("is_error"):
                    out["error"] = (ev.get("result") or "error")[:300]
        if res.returncode != 0 and not out["reply"]:
            out["error"] = (res.stderr or res.stdout or "claude exited %d" % res.returncode).strip()[-300:]
        path = os.path.join(tmp, "answer.json")
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    out["answer"] = json.load(f)
            except ValueError as e:
                out["error"] = "answer.json is not valid JSON: %s" % e
    except subprocess.TimeoutExpired:
        out["error"] = "timed out after %d s" % timeout
    finally:
        out["seconds"] = round(time.time() - t0, 1)
        shutil.rmtree(tmp, ignore_errors=True)
    return out


def resolved_cards(answer, db):
    """The records the answer's card names resolve to, the way build.py would resolve them."""
    names = []
    for entry in answer.get("cards") or []:
        names.append(entry if isinstance(entry, str) else entry.get("name", ""))
    for s in strings(answer):
        names += [key.strip() for kind, key in REF_RE.findall(s) if kind == "card"]
    recs = []
    for n in names:
        rec = db.find(n)[0]
        if rec is not None and rec not in recs:
            recs.append(rec)
    return recs


def type_line(rec):
    return rec.get("t") or " // ".join(f.get("t", "") for f in rec.get("f") or [])


def cards_ok(expect, recs):
    missing = []
    for want in expect.get("cards") or []:
        name, has = (want, "") if isinstance(want, str) else (want["name"], want.get("typeHas", ""))
        if not any(r["n"].lower() == name.lower() and has.lower() in type_line(r).lower() for r in recs):
            missing.append(name + (" (%s)" % has if has else ""))
    return missing


def source_cited(expect, answer, recs, db):
    wanted = expect.get("source") or []
    if not wanted:
        return None
    text = " ".join(strings(answer))
    refs = REF_RE.findall(text)
    rules = {key.strip().rstrip(".") for kind, key in refs if kind == "rule"} | {str(r if isinstance(r, str) else r.get("id", "")) for r in answer.get("rules") or []}
    ids = {key.strip() for kind, key in refs if kind == "ruling"} | {r for r in answer.get("rulings") or [] if isinstance(r, str)}
    cited = []
    for rec in recs:
        for r in db.rulings_for(rec):
            if r["id"] in ids or r["card"] + "-*" in ids:
                cited.append(r["text"])
    for s in wanted:
        if "rule" in s and any(r == s["rule"] or r.startswith(s["rule"]) for r in rules):
            return True
        if "ruling" in s and any(s["ruling"] in t for t in cited):
            return True
    return False


def judge(q, graded_text, model, timeout):
    expect = q["expect"]
    kind = "asks" if expect.get("asks") else "behaviour" if expect.get("behaviour") else "plain"
    prompt = JUDGE.format(question=q["question"], verdict=expect["verdict"], kind=KIND[kind], answer=graded_text)
    tmp = tempfile.mkdtemp(prefix="mtgj-judge-")
    try:
        res = claude(prompt, tmp, ["--output-format", "json", "--model", model], timeout)
        reply = json.loads(res.stdout)
        m = re.search(r"\{.*\}", reply.get("result", ""), re.S)
        got = json.loads(m.group(0))
        return {"grade": got.get("grade") if got.get("grade") in ("pass", "fail") else "fail",
                "kind": got.get("kind", "?"), "why": got.get("why", ""), "judge_cost": reply.get("total_cost_usd") or 0.0}
    except Exception as e:  # the judge failing is not the skill failing: keep it apart
        return {"grade": "error", "kind": "?", "why": "judge call failed: %s" % str(e)[:200], "judge_cost": 0.0}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run_one(q, n, a, db):
    r = ask_skill(q["question"], a.plugin_dir, a.model, a.timeout)
    answer = r.pop("answer")
    row = dict(r, id=q["id"], tags=q["tags"], run=n, wrote_answer=answer is not None, level=None,
               cards_missing=[], source=None, short="")
    if answer is not None:
        conf = answer.get("confidence") or {}
        row["level"] = conf.get("level")
        row["short"] = answer.get("shortAnswer", "")
        recs = resolved_cards(answer, db)
        row["cards_missing"] = cards_ok(q["expect"], recs)
        row["source"] = source_cited(q["expect"], answer, recs, db)
        graded = "Short answer: %s\nConfidence: %s\nAssumptions: %s\nNot retrieved: %s\nChat reply: %s" % (
            row["short"], row["level"], conf.get("assumptions") or [], conf.get("notRetrieved") or [], row["reply"][:1500])
    else:
        row["cards_missing"] = [] if q["expect"].get("asks") or q["expect"].get("behaviour") else \
            [c if isinstance(c, str) else c["name"] for c in q["expect"].get("cards") or []]
        graded = "Chat reply (no answer.json was written): %s" % (row["reply"][:3000] or "[empty]")
    if row["error"] and not row["reply"].strip() or "session limit" in row["reply"] or "usage limit" in row["reply"].lower():
        row.update(grade="error", kind="?", why="skill call failed: " + (row["error"] or row["reply"])[:200], judge_cost=0.0)
    else:
        row.update(judge(q, graded, a.judge_model, a.timeout))
    row["ok"] = row["grade"] == "pass" and not row["cards_missing"]
    return row


def report(rows, a, started):
    done = [r for r in rows if r["grade"] != "error"]
    ok = sum(r["ok"] for r in done)
    confident_wrong = [r for r in done if not r["ok"] and r["level"] == "high"]
    lines = ["# Eval run: %s" % a.label, "",
             "%s · %d run(s) of %d question(s) · model %s · judge %s" % (
                 started, len(rows), len({r["id"] for r in rows}), a.model or "default", a.judge_model), "",
             "| | |", "|---|---|",
             "| Passed | %d of %d (%.0f%%) |" % (ok, len(done), 100.0 * ok / max(1, len(done))),
             "| Wrong with confidence \"high\" | %d |" % len(confident_wrong),
             "| Wrong card resolved | %d |" % sum(bool(r["cards_missing"]) for r in done),
             "| Settling source cited | %d of %d |" % (sum(r["source"] is True for r in done), sum(r["source"] is not None for r in done)),
             "| lookup.py calls per run | %.1f (most: %d) |" % (sum(r["lookups"] for r in rows) / max(1, len(rows)), max([r["lookups"] for r in rows] or [0])),
             "| Tool calls per run | %.1f |" % (sum(r["tools"] for r in rows) / max(1, len(rows))),
             "| Seconds per run | %.0f |" % (sum(r["seconds"] for r in rows) / max(1, len(rows))),
             "| Cost | $%.2f |" % sum(r["cost"] + r["judge_cost"] for r in rows),
             "| Runs that errored (not graded) | %d |" % (len(rows) - len(done)), ""]
    tags = sorted({t for r in rows for t in r["tags"]})
    lines += ["## By tag", "", "| Tag | Passed |", "|---|---|"]
    for t in tags:
        sub = [r for r in done if t in r["tags"]]
        lines.append("| %s | %d of %d |" % (t, sum(r["ok"] for r in sub), len(sub)))
    lines += ["", "## By question", "", "| Question | Passed | Level | Lookups | Cards missing | Source | Judge |", "|---|---|---|---|---|---|---|"]
    for qid in dict.fromkeys(r["id"] for r in rows):
        sub = [r for r in rows if r["id"] == qid]
        lines.append("| %s | %d of %d | %s | %s | %s | %s | %s |" % (
            qid, sum(r["ok"] for r in sub), len(sub), "/".join(str(r["level"] or "-") for r in sub),
            "/".join(str(r["lookups"]) for r in sub),
            "; ".join(sorted({m for r in sub for m in r["cards_missing"]})) or "-",
            "/".join({True: "yes", False: "no", None: "-"}[r["source"]] for r in sub),
            next((r["why"] for r in sub if not r["ok"]), sub[0]["why"]).replace("|", "/")))
    fails = [r for r in rows if not r["ok"]]
    if fails:
        lines += ["", "## Failures", ""]
        for r in fails:
            lines += ["**%s** (run %d, %s, level %s%s)" % (r["id"], r["run"], r["grade"], r["level"], ", " + r["error"] if r["error"] else ""), "",
                      "> " + (r["short"] or r["reply"][:600] or "[no reply]").replace("\n", "\n> "), "",
                      "Judge: " + r["why"] + (" Cards missing: " + ", ".join(r["cards_missing"]) + "." if r["cards_missing"] else ""), ""]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="+", default=[], help="question ids or tags")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--jobs", type=int, default=4, help="questions asked at the same time")
    ap.add_argument("--model", help="model for the skill runs (default: the account's default)")
    ap.add_argument("--judge-model", default="sonnet")
    ap.add_argument("--timeout", type=int, default=600, help="seconds per call")
    ap.add_argument("--label", default=datetime.datetime.now().strftime("%Y-%m-%d-%H%M"))
    ap.add_argument("--plugin-dir", default=PLUGIN,
                    help="plugin folder to measure (default: this repo's); a checkout of another commit gives a baseline")
    a = ap.parse_args()
    a.plugin_dir = os.path.abspath(a.plugin_dir)
    # card names are resolved with the measured plugin's own code, as its build.py would
    sys.path.insert(0, os.path.join(a.plugin_dir, "skills", "mtg-rules-judge", "scripts"))
    os.environ.setdefault("MTG_CARD_DB", os.path.join(a.plugin_dir, "skills", "mtg-rules-judge", "data", "cards.json"))
    from carddb import CardDB
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    with open(os.path.join(HERE, "questions.json"), encoding="utf-8") as f:
        questions = json.load(f)["questions"]
    if a.only:
        questions = [q for q in questions if q["id"] in a.only or set(q["tags"]) & set(a.only)]
    if not questions:
        sys.exit("No question matches --only.")
    db = CardDB()
    started = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    jobs = [(q, n) for n in range(1, a.repeat + 1) for q in questions]
    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.jobs) as pool:
        futures = [pool.submit(run_one, q, n, a, db) for q, n in jobs]
        for fut in concurrent.futures.as_completed(futures):
            r = fut.result()
            rows.append(r)
            if r["grade"] == "error" and "limit" in r["why"]:  # the account's usage limit: the rest would fail too
                print("Stopping: " + r["why"], flush=True)
                for f in futures:
                    f.cancel()
                break
            print("%-34s run %d  %-5s level=%-6s lookups=%d  %3.0fs  %s" % (
                r["id"], r["run"], "ok" if r["ok"] else r["grade"].upper() if r["grade"] != "pass" else "CARDS",
                r["level"], r["lookups"], r["seconds"], r["error"] or ""), flush=True)
    order = {q["id"]: i for i, q in enumerate(questions)}
    rows.sort(key=lambda r: (order[r["id"]], r["run"]))

    out_dir = os.path.join(HERE, "results")
    os.makedirs(out_dir, exist_ok=True)
    text = report(rows, a, started)
    with open(os.path.join(out_dir, a.label + ".md"), "w", encoding="utf-8") as f:
        f.write(text)
    with open(os.path.join(out_dir, a.label + ".json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    print("\n" + text.split("## By tag")[0])
    print("Full report: " + os.path.relpath(os.path.join(out_dir, a.label + ".md")))


if __name__ == "__main__":
    main()
