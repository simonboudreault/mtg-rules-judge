# MTG Rules Judge — Claude plugin

Ask Claude a *Magic: The Gathering* rules question and get an answer a judge would
stand behind: every claim backed by the Comprehensive Rules, the card's Oracle text or
an official ruling, quoted so you can check it. Works in the Claude app (web, desktop
and mobile), in Cowork and in Claude Code, in English or French.

The rules text and the card database are bundled in the plugin and **update
themselves**: a GitHub Actions job checks Wizards and Scryfall every day and publishes
a new version when the Comprehensive Rules change or a new set comes out. Everyone who
installed the plugin gets it automatically.

## Install

### In the Claude app (also covers mobile and Cowork)

1. Open [claude.ai/customize/plugins](https://claude.ai/customize/plugins)
   (**Customize > Plugins**).
2. **Add > Add marketplace**, enter `simonboudreault/mtg-rules-judge`.
3. Add the **mtg-rules-judge** plugin from the list.
4. Open the marketplace you just added and turn on **Sync automatically**, so new
   versions arrive without you doing anything.

Then just ask: *"Does Ruby Medallion reduce the X in Fireball?"* Claude loads the
skill when a question matches. To force it, type `/` and pick `mtg-rules-judge`.

By default the reply is a link to the full answer page, and nothing else — except one
line above it when the answer rests on an assumption or isn't high confidence, and a
question back when a fact the verdict depends on is missing. Start or end your
message with `quick` (`rapide` or `vite` in French) to get the short answer and the
confidence level first, without the link; type `link` afterwards if you want the
page too.

A plugin installed here also shows up in Claude Code the next time you start a
session with the same account.

### In Claude Code only

```
/plugin marketplace add simonboudreault/mtg-rules-judge
/plugin install mtg-rules-judge@mtg-rules-judge
```

Turn on auto-update for the marketplace under **Marketplaces** in `/plugin`.

### Without plugins (manual upload)

Each release on the [Releases page](https://github.com/simonboudreault/mtg-rules-judge/releases)
has a `mtg-rules-judge-skill.zip`. Upload it under **Settings > Capabilities > Skills**.
You'll have to re-upload it yourself after each release; the plugin route doesn't need that.

## How the automatic updates work

`tools/update.py` runs daily from `.github/workflows/update.yml`:

| Source | Check | Action |
|---|---|---|
| **Comprehensive Rules** | The "effective as of" date on [magic.wizards.com/en/rules](https://magic.wizards.com/en/rules) is later than the bundled file's | Download the new `.txt` |
| **Cards and rulings** | Scryfall lists a real set (not tokens/promos) released since the database was built, or the database is over 90 days old | Rebuild `cards.json` from Scryfall's bulk data, French names included |

When either changed, it bumps the plugin version (`YYYY.MDD.n`, e.g. `2026.1005.0`),
commits, pushes and publishes a GitHub release with the zip. Claude only re-downloads
a plugin when its version changes, which is why the version only moves when the data did.

Run it by hand from the **Actions** tab (**Update rules and cards > Run workflow**),
with the *force* boxes if you want a rebuild without waiting for a new set. Locally:

```
python tools/update.py --check          # what would change
python tools/update.py                  # update, bump version (no commit)
python tools/update.py --force-cards    # rebuild cards even if nothing is new
```

The card rebuild downloads Scryfall's "all cards" file (large) for the French names;
`--no-french` skips it.

## Repository size

The card database is committed as plain JSON with one card, ruling list or French
name per line, sorted, rather than gzipped. Git delta-compresses it, so a rebuild only
adds the lines that changed to the history (about 1 KB for a one-card update, against
~9 MB for each gzip blob). It's ~32 MB in the working tree but ~9 MB to clone, and the
history is never rewritten. The release zip ships it gzipped; `carddb.py` reads either.

## Repository layout

```
.claude-plugin/marketplace.json        the marketplace catalog (one plugin)
plugins/mtg-rules-judge/
  .claude-plugin/plugin.json           name, version, description
  skills/mtg-rules-judge/
    SKILL.md                           the skill Claude follows
    scripts/                           lookup.py, build.py, rules.py, build_card_db.py, ...
    data/cards.json                    Oracle text, rulings, French names (Scryfall)
    references/MagicCompRules.txt      the Comprehensive Rules (Wizards of the Coast)
    assets/answer-template.html        the interactive answer page
tools/update.py                        the updater the workflow runs
.github/workflows/update.yml           daily schedule
```

Card data comes from [Scryfall](https://scryfall.com); the Comprehensive Rules are
© Wizards of the Coast. This project is unofficial fan content permitted under the
Fan Content Policy and is not endorsed by Wizards.
