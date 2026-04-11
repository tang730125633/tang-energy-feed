# Archive directory

This directory is the **authoritative historical record** of every daily
digest that has been successfully sent to Feishu. It is written by
`scripts/archive.py` immediately after a successful send, and is
committed to the repository so the full history is permanently available
on GitHub.

## What's in here

### Per-day files (under `YYYY/MM/`)

For each day a digest is sent, three files are created:

| Filename | Purpose |
|---|---|
| `YYYY-MM-DD-input.json` | The full AI remix output — machine-readable. Can be replayed through `build_card.py` to regenerate the exact Feishu card. |
| `YYYY-MM-DD.md` | Human-readable Markdown rendering. GitHub previews this directly — click the file on GitHub to read the digest as if it were a blog post. |
| `YYYY-MM-DD-meta.json` | Audit metadata: send timestamp, Feishu message_id, target chat_id, AI model name, feed generation time, article count. |

### Rolling dedup cache

`seen-urls.json` — a rolling 7-day cache of article URLs that have already
been used in a digest. `scripts/classify_candidates.py` reads this file
and automatically excludes any URL in the window from tomorrow's candidate
pools. This guarantees that **the same news article can never appear in
two different daily digests within a 7-day period**, even if the upstream
feed keeps returning it.

The TTL is configurable in the JSON itself (`ttlDays` field, default `7`).
Entries older than the TTL are pruned automatically during the next archive
step.

## How the history is used

### Reading a historical digest

```bash
# See the digest for 2026-04-11 as rendered markdown
cat archive/2026/04/2026-04-11.md

# Or browse it on GitHub:
open https://github.com/tang730125633/tang-energy-feed/blob/main/archive/2026/04/2026-04-11.md
```

### Searching history

```bash
# Find every mention of "铜价" across all archived digests
grep -r "铜价" archive/2026/

# Find every digest that included 储能 in top3
grep -l "储能" archive/2026/*/*.md

# Count digests sent per month
ls archive/2026/*/2026-*-*.md | sort | uniq -c
```

### Replaying an old digest

```bash
# Re-send the 2026-04-11 digest to a test group
python3 scripts/build_card.py archive/2026/04/2026-04-11-input.json > /tmp/card.json
# Then send /tmp/card.json via lark-cli or send_lark.py
```

## Why commit this to git?

Committing the archive to git, rather than keeping it in a database or
S3 bucket, follows the **follow-builders philosophy**: *git is your
database*.

Benefits:
- **Zero infrastructure** — no S3 bucket, no Postgres, no RDS
- **Free** — GitHub hosts the history at no cost
- **Free diff/history** — `git log archive/2026/04/2026-04-11.md`
  shows when it was written, and any subsequent edits
- **Free public access** — anyone can clone the repo and read the history
- **Grep-able** — plain text files, searchable with standard tools
- **Self-documenting** — the filename already tells you what it is

Estimated disk usage: ~15 KB per day × 365 days ≈ 5 MB / year.
git handles this without any performance concerns.

## Manual interventions

If you need to force a digest re-send (e.g. debugging), delete the
`.last-sent-date` file at the repo root:

```bash
rm .last-sent-date
./scripts/run.sh
```

**Warning**: if the seen-urls cache still contains the previous URLs,
the replay will pick different articles (by design). To force an
*identical* replay, use `build_card.py` on the existing
`YYYY-MM-DD-input.json` directly — see "Replaying an old digest" above.

## Schema evolution

The three per-day files have stable schemas. If we ever need to add
fields:

- **Backward-compatible additions** (new fields, new sections): just add
  them. Old files remain valid.
- **Breaking changes** (renaming fields, changing types): bump a version
  number in the filename prefix (e.g. `v2/2027-01-01-input.json`) and
  keep `v1/` readable indefinitely.
