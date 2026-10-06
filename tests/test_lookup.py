#!/usr/bin/env python3
"""Checks for the evidence scripts: card resolution, rule search, build.py's refusals.

  python3 tests/test_lookup.py              everything
  python3 tests/test_lookup.py Invariants   only what holds whatever today's card list is

Invariants run inside the daily data update, where a failure blocks the release.
Examples name real cards and today's rule numbers; they run on every push (and after
the update, without blocking it), so a card list or rules change that moves them is
seen without stopping the data from shipping.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SKILL = os.path.join(ROOT, "plugins", "mtg-rules-judge", "skills", "mtg-rules-judge")
SCRIPTS = os.path.join(SKILL, "scripts")
sys.path.insert(0, SCRIPTS)
from carddb import NICKNAMES, CardDB, _rank, kind, norm  # noqa: E402
import lookup  # noqa: E402
import rules as cr  # noqa: E402

DB = CardDB()
RULES = dict(cr.parse_rules(cr.split_parts(cr.load(cr.DEFAULT_PATH))[1]))


def run(script, *args, env=None):
    """Run a script as the model does, through a pipe. Returns (exit code, stdout)."""
    e = dict(os.environ, **(env or {}))
    e.pop("PYTHONIOENCODING", None)
    res = subprocess.run([sys.executable, os.path.join(SCRIPTS, script)] + list(args),
                         capture_output=True, env=e, cwd=HERE)
    out = res.stdout.decode("utf-8", "replace") + res.stderr.decode("utf-8", "replace")
    return res.returncode, out.replace("\r\n", "\n")


def build(answer, *flags):
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(answer, f)
    try:
        return run("build.py", path, *flags)
    finally:
        os.remove(path)


GOOD = {
    "lang": "en", "title": "t", "question": "q",
    "shortAnswer": "No ([[rule:305.7]], [[ruling:urborg-tomb-of-yawgmoth-2]]).",
    "confidence": {"level": "high", "reasons": ["A ruling addresses it."], "assumptions": [], "notRetrieved": []},
    "cards": ["Blood Moon", "Urborg, Tomb of Yawgmoth"],
    "steps": [{"text": "Blood Moon sets the type ([[rule:305.7]])."}],
}


class Invariants(unittest.TestCase):
    """True whatever the card list holds."""

    def test_planeswalker_lookup_survives_a_windows_pipe(self):
        # a loyalty cost holds a minus sign that cp1252 can't encode; the output used to die there
        code, out = run("lookup.py", "--card", "Jace, the Mind Sculptor", "--rule", "306.5b",
                        env={"PYTHONLEGACYWINDOWSSTDIO": "1", "PYTHONUTF8": "0"})
        self.assertEqual(code, 0, out[-500:])
        self.assertNotIn("Traceback", out)
        self.assertIn("306.5b", out)

    def test_a_card_or_token_beats_a_theme_card_of_the_same_name(self):
        by = {}
        for rec in DB.cards:
            by.setdefault(norm(rec["n"]), []).append(rec)
        shared = {k: v for k, v in by.items() if len(v) > 1}
        self.assertTrue(shared, "the data has no shared names; the test is vacuous")
        for k, recs in shared.items():
            self.assertEqual(_rank(DB.by_name[k]), min(_rank(r) for r in recs), k)

    def test_nickname_targets_exist_and_are_not_printed_names(self):
        for nick, name in NICKNAMES.items():
            self.assertIn(norm(name), DB.by_name, f"{nick} -> {name}")
            self.assertNotIn(nick, DB.by_name, f"'{nick}' is a printed name; the nickname would never apply")

    def test_concept_and_hint_rules_exist(self):
        for name, _, ids in lookup.CONCEPTS:
            for n in ids:
                self.assertIn(n, RULES, f"{name}: {n}")
        for name, _, ids, _ in lookup.CARD_HINTS:
            for n in ids:
                self.assertIn(n, RULES, f"{name}: {n}")

    def test_build_refuses_an_invented_official_ruling(self):
        fake = dict(GOOD, shortAnswer="Yes ([[rule:100.1]], [[ruling:blood-moon-fake]]).",
                    rulings=[{"id": "blood-moon-fake", "card": "blood-moon", "date": "2024-01-01", "source": "wotc",
                              "text": "Urborg still makes every land a Swamp under Blood Moon."}])
        code, out = build(fake, "--check")
        self.assertNotEqual(code, 0)
        self.assertIn("written by hand", out)
        self.assertIn("would be in the DB", out)
        self.assertIn("can't be \"high\"", out)
        self.assertNotIn("Link:", out)

    def test_build_refuses_high_confidence_on_unretrieved_or_web_text(self):
        code, out = build(dict(GOOD, confidence=dict(GOOD["confidence"], notRetrieved=["Card X: from mtg.wtf"])), "--check")
        self.assertNotEqual(code, 0)
        self.assertIn("notRetrieved", out)
        web = dict(GOOD, cards=GOOD["cards"] + [{"name": "Zorvax, the Unprinted", "manaCost": "{1}", "typeLine": "Artifact",
                                                 "oracleText": "Nothing.", "colors": [], "url": "https://example.test/zorvax"}])
        code, out = build(web, "--check")
        self.assertNotEqual(code, 0)
        self.assertIn("came from the web", out)
        code, out = build(dict(web, confidence=dict(GOOD["confidence"], level="medium")), "--check")
        self.assertEqual(code, 0, out)

    def test_build_refuses_a_web_card_or_ruling_without_its_url(self):
        web = dict(GOOD, confidence=dict(GOOD["confidence"], level="low"),
                   cards=GOOD["cards"] + [{"name": "Zorvax, the Unprinted", "typeLine": "Artifact", "oracleText": "Nothing.", "colors": []}])
        code, out = build(web, "--check")
        self.assertNotEqual(code, 0)
        self.assertIn('"url"', out)

    def test_build_check_prints_the_quotes_behind_the_short_answer(self):
        code, out = build(GOOD, "--check")
        self.assertEqual(code, 0, out)
        self.assertIn("RE-READ", out)
        self.assertIn("305.7:", out)
        self.assertIn("urborg-tomb-of-yawgmoth-2:", out)
        self.assertIn("Cards: Blood Moon (Enchantment); Urborg, Tomb of Yawgmoth (Legendary Land)", out)
        self.assertNotIn("Link:", out)

    def test_build_asks_for_a_caveat_line_when_one_is_owed(self):
        code, out = build(GOOD, "--link-only")
        self.assertEqual(code, 0, out)
        self.assertIn("nothing else", out)
        code, out = build(dict(GOOD, confidence=dict(GOOD["confidence"], assumptions=["The Forest is basic."])), "--link-only")
        self.assertEqual(code, 0, out)
        self.assertIn("ONE line stating the assumption", out)

    def test_web_ruling_is_labelled_unverified_on_the_page(self):
        web = dict(GOOD, confidence=dict(GOOD["confidence"], level="medium"),
                   rulings=[{"id": "blood-moon-99", "card": "blood-moon", "date": "2099-01-01", "source": "wotc",
                             "text": "A ruling from the future.", "url": "https://example.test/ruling"}])
        out_html = os.path.join(tempfile.mkdtemp(), "a.html")
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(web, f)
        code, out = run("build.py", path, "-o", out_html, "--no-link")
        os.remove(path)
        self.assertEqual(code, 0, out)
        with open(out_html, encoding="utf-8") as f:
            page = f.read()
        self.assertIn("From the web, not verified", page)

    def test_lookup_closing_text_names_build(self):
        code, out = run("lookup.py", "--rule", "100.1")
        self.assertIn("build.py", out.split("## NEXT")[1])
        self.assertNotIn("Don't run build.py", out)


class Examples(unittest.TestCase):
    """Real cards and today's rule numbers. Loosely written, but a data change can move them."""

    def resolve(self, q):
        rec, how, alts = DB.find(q)
        return (rec["n"] if rec else None), how, alts

    def test_short_names_print_the_cards_they_can_mean(self):
        code, out = run("lookup.py", "--card", "Urborg", "--card", "Elesh Norn", "--card", "Ragavan")
        self.assertEqual(code, 0, out[-300:])
        for name in ("## CARD Urborg\n", "Urborg, Tomb of Yawgmoth", "Elesh Norn, Grand Cenobite",
                     "Elesh Norn, Mother of Machines", "Ragavan, Nimble Pilferer", "## NOTE"):
            self.assertIn(name, out)
        self.assertIn("[token]", out.split("## CARD Ragavan\n")[1].split("\n")[0] if "## CARD Ragavan\n" in out else out)

    def test_vanguard_and_theme_names_are_ambiguous(self):
        for q in ("Urza", "Karn", "Teferi"):
            name, how, alts = self.resolve(q)
            self.assertIsNone(name, q)
            self.assertEqual(how, "ambiguous", q)
            self.assertTrue(all(a.startswith(q + ",") for a in alts), alts)
        code, out = run("lookup.py", "--card", "Teferi")
        self.assertIn("## AMBIGUOUS: Teferi", out)
        self.assertIn("Teferi, Time Raveler", out)

    def test_tokens_and_colliding_names_resolve_to_the_game_object(self):
        self.assertEqual(kind(DB.find("Treasure")[0]), "token")
        self.assertEqual(kind(DB.find("Food")[0]), "token")
        self.assertEqual(kind(DB.find("The Ring")[0]), "token")
        self.assertEqual(DB.find("Inferno")[0].get("t"), "Instant")
        self.assertEqual(self.resolve("Llanowar")[0], "Llanowar")

    def test_nicknames_french_names_and_faces(self):
        self.assertEqual(self.resolve("Bob")[0], "Dark Confidant")
        self.assertEqual(self.resolve("Goyf")[0], "Tarmogoyf")
        self.assertEqual(self.resolve("Lune de sang")[0], "Blood Moon")
        self.assertEqual(self.resolve("Insectile Aberration")[0], "Delver of Secrets // Insectile Aberration")
        self.assertEqual(self.resolve("Fire")[0], "Fire // Ice")
        self.assertEqual(self.resolve("Stomp")[0], "Bonecrusher Giant // Stomp")
        self.assertEqual(self.resolve("Lightning Bolt")[1], "exact")
        self.assertEqual(self.resolve("Uro")[0], "Uro, Titan of Nature's Wrath")

    def test_not_found_suggests_the_likely_cards_first(self):
        name, how, alts = self.resolve("Emrakul")
        self.assertEqual(how, "ambiguous")
        self.assertTrue(alts and all(a.startswith("Emrakul, ") for a in alts), alts)
        name, how, alts = self.resolve("Zorvax, the Unprinted")
        self.assertIsNone(name)
        self.assertEqual(how, "not found")

    def test_search_reaches_the_rule_that_lacks_the_words(self):
        code, out = run("lookup.py", "--search", "lose all abilities", "--search", "copy")
        self.assertIn("613.1f", out.split('## SEARCH "lose all abilities"')[1].split("## SEARCH")[0])
        self.assertIn("707 Copying Objects", out.split('## SEARCH "copy"')[1])

    def test_card_text_brings_in_the_rules_nobody_asked_for(self):
        code, out = run("lookup.py", "--card", "Blood Moon", "--card", "Urborg, Tomb of Yawgmoth")
        also = out.split("## ALSO RELEVANT")[1]
        self.assertIn("305.7", also)
        self.assertIn("613.8a", also)
        code, out = run("lookup.py", "--card", "Doubling Season", "--card", "Hardened Scales", "--card", "Humility")
        also = out.split("## ALSO RELEVANT")[1]
        self.assertIn("616.1", also)
        self.assertIn("613.1f", also)

    def test_ruling_search_crosses_cards(self):
        code, out = run("lookup.py", "--rulings", "Ring tempts")
        self.assertIn("## RULINGS", out)
        self.assertRegex(out, r"\[[a-z0-9-]+\] \d{4}-\d{2}-\d{2} .+: ")

    def test_skill_example_passes_the_check(self):
        with open(os.path.join(SKILL, "SKILL.md"), encoding="utf-8") as f:
            m = re.search(r"```json\n(\{.*?\n\})\n```", f.read(), re.S)
        code, out = build(json.loads(m.group(1)), "--check")
        self.assertEqual(code, 0, out)
        self.assertIn("choose the value of X", out)  # the ruling the example cites is the X-spell one


if __name__ == "__main__":
    unittest.main()
