#!/usr/bin/env python3
"""Checks for the share-link format (scripts/share.py) and the rules data feed.

  python3 tests/test_share.py

Runs in the daily workflow too, so a data update that breaks the link contract is caught.
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
FIX = os.path.join(HERE, "fixtures")
DATA = os.path.join(ROOT, "docs", "data")
SCRIPTS = os.path.join(ROOT, "plugins", "mtg-rules-judge", "skills", "mtg-rules-judge", "scripts")
sys.path.insert(0, SCRIPTS)
import share  # noqa: E402


def fixtures(suffix):
    return sorted(f for f in os.listdir(FIX) if f.endswith(suffix))


def load(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return json.load(f)


class Encoding(unittest.TestCase):
    def test_round_trip(self):
        for name in fixtures(".share.json"):
            p = load(name)
            self.assertEqual(share.decode_fragment(share.encode_fragment(p)), p, name)

    def test_fragment_files_match_payloads(self):
        for name in fixtures(".fragment.txt"):
            with open(os.path.join(FIX, name), encoding="utf-8") as f:
                frag = f.read().strip()
            self.assertEqual(share.decode_fragment(frag), load(name.replace(".fragment.txt", ".share.json")), name)

    def test_damaged_fragment_is_rejected(self):
        frag = share.encode_fragment({"v": 1, "title": "x" * 200})
        for bad in (frag[:-5], frag[:20] + "A" + frag[21:], "2." + frag[2:], "nope"):
            with self.assertRaises(ValueError, msg=bad[:30]):
                share.decode_fragment(bad)

    def test_hashes(self):
        # sha1("Flash")[:8] and sha1("x")[:8]; the viewer must compute the same
        self.assertEqual(share.card_hash({"oracleText": "Flash"}), "b6248223")
        self.assertEqual(share.ruling_hash("x"), "11f6ad8e")
        # faces: joined with "\n//\n"; a card with faces ignores its top-level oracleText
        two = {"oracleText": "ignored", "faces": [{"oracleText": "A"}, {"oracleText": "B"}]}
        self.assertEqual(share.card_hash(two), share._h8("A\n//\nB"))
        self.assertEqual(share.card_hash({}), share._h8(""))

    def test_cap(self):
        p = load("ruby-medallion.share.json")
        url, n = share.make_link(p, "https://example.test/", max_chars=100)
        self.assertIsNone(url)
        self.assertGreater(n, 100)
        url, n = share.make_link(p, "https://example.test/")
        self.assertTrue(url.startswith("https://example.test/#1."))
        self.assertLessEqual(n, share.LINK_MAX_CHARS)
        self.assertEqual(share.make_link(p, ""), (None, 0))

    def test_link_line(self):
        r = load("ruby-medallion.resolved.json")
        self.assertEqual(share.link_line(r, ""), "")
        self.assertTrue(share.link_line(r, "https://example.test").startswith("Link: https://example.test/#1."))
        os.environ["MTG_JUDGE_LINK_MAX"] = "50"
        try:
            self.assertIn("omitted", share.link_line(r, "https://example.test/"))
        finally:
            del os.environ["MTG_JUDGE_LINK_MAX"]


class Payload(unittest.TestCase):
    def test_db_cards_are_slim_and_external_cards_full(self):
        for name in fixtures(".share.json"):
            for c in load(name)["cards"]:
                if "oid" in c:
                    self.assertEqual(set(c) - {"note"}, {"id", "name", "oid", "h"}, (name, c["name"]))
                    self.assertRegex(c["h"], r"^[0-9a-f]{8}$")
                else:
                    self.assertIn("oracleText", c, (name, c["name"]))
                    self.assertIn("source", c, (name, c["name"]))

    def test_web_fallback_fixture(self):
        p = load("web-fallback.share.json")
        ext = [c for c in p["cards"] if "oid" not in c]
        self.assertEqual([c["name"] for c in ext], ["Nonexistent Test Card"])
        custom = [r for r in p["rulings"] if "text" in r]
        self.assertEqual([r["id"] for r in custom], ["nonexistent-test-card-1"])
        refs = [r for r in p["rulings"] if "h" in r]
        self.assertTrue(refs and all(set(r) == {"id", "card", "d", "h"} for r in refs))
        self.assertTrue(p["reddit"]["searched"])

    def test_reddit_default_is_omitted_and_false_is_kept(self):
        self.assertNotIn("reddit", load("ruby-medallion.share.json"))
        self.assertIs(load("fable-layers-fr.share.json")["reddit"], False)

    def test_dates_and_lang(self):
        for name in fixtures(".share.json"):
            p = load(name)
            self.assertEqual(p["v"], 1)
            self.assertIn(p["lang"], ("en", "fr"))
            self.assertTrue(p["cr"] and p["at"] and p["db"], name)
            self.assertTrue(all(isinstance(r, str) for r in p["rules"]), name)

    def test_typical_link_is_short(self):
        frag = share.encode_fragment(load("ruby-medallion.share.json"))
        self.assertLess(len(frag), 1500)


class PageLink(unittest.TestCase):
    """build.py prints the link for the reply and also puts it in the page."""

    def build(self, *extra):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "a.html")
            res = subprocess.run([sys.executable, os.path.join(SCRIPTS, "build.py"),
                                  os.path.join(FIX, "ruby-medallion.in.json"), "-o", out, *extra],
                                 check=True, capture_output=True, text=True, encoding="utf-8",
                                 env=dict(os.environ, MTG_JUDGE_SITE="https://example.test/", PYTHONIOENCODING="utf-8"))
            with open(out, encoding="utf-8") as f:
                return f.read(), res.stdout

    def page_links(self, html):
        return set(re.findall(r'(?:href|data-url|value)="(https://example\.test/#1\.[^"]+)"', html))

    def test_link_is_printed_and_in_the_page(self):
        html, stdout = self.build()
        urls = self.page_links(html)
        self.assertEqual(len(urls), 1)  # open link, copy button and manual field all hold the same URL
        url = urls.pop()
        self.assertEqual(share.decode_fragment(url.split("#", 1)[1]), load("ruby-medallion.share.json"))
        self.assertEqual(stdout.strip().splitlines()[-1], "Link: " + url)
        self.assertNotIn("ublish this file", stdout)  # artifact delivery is off

    def test_link_only_writes_no_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = subprocess.run([sys.executable, os.path.join(SCRIPTS, "build.py"),
                                  os.path.join(FIX, "ruby-medallion.in.json"), "--link-only"],
                                 check=True, capture_output=True, text=True, encoding="utf-8", cwd=tmp,
                                 env=dict(os.environ, MTG_JUDGE_SITE="https://example.test/", PYTHONIOENCODING="utf-8"))
            self.assertEqual(os.listdir(tmp), [])  # no answer.html, nothing else
        last = res.stdout.strip().splitlines()[-1]
        self.assertTrue(last.startswith("Link: https://example.test/#1."), last)
        self.assertEqual(share.decode_fragment(last.split("#", 1)[1]), load("ruby-medallion.share.json"))

    def test_no_link(self):
        html, stdout = self.build("--no-link")
        self.assertEqual(self.page_links(html), set())
        self.assertNotIn('class="share"', html)
        self.assertNotIn("Link:", stdout)


class DataFeed(unittest.TestCase):
    def test_every_fixture_rule_is_in_the_feed(self):
        with open(os.path.join(DATA, "meta.json"), encoding="utf-8") as f:
            meta = json.load(f)
        for name in fixtures(".share.json"):
            p = load(name)
            self.assertEqual(p["cr"], meta["crEffectiveDate"], name)  # fixtures were built from the same CR
            for rid in p["rules"]:
                sec = rid[:3]
                self.assertIn(sec, meta["sections"], rid)
                with open(os.path.join(DATA, "rules", sec + ".json"), encoding="utf-8") as f:
                    self.assertIn(rid, json.load(f)["rules"], rid)


if __name__ == "__main__":
    unittest.main(verbosity=1)
