#!/usr/bin/env python3
"""Regenerate the test fixtures from tests/fixtures/*.in.json.

For each <name>.in.json (an answer.json as Claude writes it) this writes:
  <name>.resolved.json   build.py output (full text, what the artifact embeds)
  <name>.share.json      the share payload (ids only, what the link carries)
  <name>.fragment.txt    the bare compressed fragment "1.…" so a link can be built for any base URL
  <name>.readable.txt    the bare readable fragment "2.…", the form Claude types
and copies the share payloads to docs/fixtures/ so the viewer can load them with
?fixture=<name> while developing.

  python3 tests/make_fixtures.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIX = os.path.join(HERE, "fixtures")
SCRIPTS = os.path.join(ROOT, "plugins", "mtg-rules-judge", "skills", "mtg-rules-judge", "scripts")
DOCS_FIX = os.path.join(ROOT, "docs", "fixtures")
sys.path.insert(0, SCRIPTS)
import share  # noqa: E402


def main():
    os.makedirs(DOCS_FIX, exist_ok=True)
    names = sorted(f[:-8] for f in os.listdir(FIX) if f.endswith(".in.json"))
    with tempfile.TemporaryDirectory() as tmp:
        for name in names:
            resolved = os.path.join(FIX, name + ".resolved.json")
            subprocess.run([sys.executable, os.path.join(SCRIPTS, "build.py"), os.path.join(FIX, name + ".in.json"),
                            "-o", os.path.join(tmp, name + ".html"), "--json", resolved, "--no-link"],
                           check=True, stdout=subprocess.DEVNULL)
            with open(resolved, encoding="utf-8") as f:
                payload = share.to_share_payload(json.load(f))
            with open(os.path.join(FIX, name + ".share.json"), "w", encoding="utf-8", newline="\n") as f:
                json.dump(payload, f, ensure_ascii=False, indent=1)
                f.write("\n")
            frag = share.encode_fragment(payload)
            with open(os.path.join(FIX, name + ".fragment.txt"), "w", encoding="utf-8", newline="\n") as f:
                f.write(frag + "\n")
            readable = share.encode_readable(payload)
            if readable is None:
                sys.exit(f"{name}: the readable link format can't carry this payload")
            with open(os.path.join(FIX, name + ".readable.txt"), "w", encoding="utf-8", newline="\n") as f:
                f.write(readable + "\n")
            shutil.copy(os.path.join(FIX, name + ".share.json"), os.path.join(DOCS_FIX, name + ".json"))
            print(f"{name}: compressed {len(frag)} chars, readable {len(readable)} chars")


if __name__ == "__main__":
    main()
