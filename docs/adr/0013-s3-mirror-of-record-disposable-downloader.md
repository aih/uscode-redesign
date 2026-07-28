# ADR-0013: S3 is the corpus of record; the downloader is a disposable EC2 box

**Status:** Accepted — 2026-07-28 (Session 6.5)
**Context:** ADR-0012 (resumable backfill, ledger); CLAUDE.md "External source
etiquette"; the measured corpus (~9 GB, ~3,200 files) and the measured link
(OLRC serves ~50 KB/s; our throttle is 1 req/sec → a 40–50 hour run).
Operational guide: docs/remote-ops.md.

## The asset is the download time, not the bytes

The original sizing fear (40–80 GB) turned out wrong — size-weighted projection
from the live run is ~9 GB, which fits anywhere. What is genuinely expensive is
the **40–50 hours of deliberately polite downloading**, and the etiquette budget
with uscode.house.gov it represents. That cost should be paid exactly once,
ever. A laptop is the wrong place to pay it (sleep cycles, lid closes, travel),
and re-paying it because a disk died or a colleague needs the corpus would be
self-inflicted.

## Decision

1. **S3 holds the corpus of record** under `s3://{bucket}/usc/`: the zips, the
   ledger, the inventory JSON, the provenance manifests, and the verification
   report. Private bucket, versioned (a bad push can never destroy the previous
   ledger). Every consumer — rebuild, CI, second machine, Session 8's loader —
   pulls from the mirror and never touches OLRC.
2. **The backfill runs on a disposable `t4g.micro`** driven by two systemd units
   (`scripts/ec2-user-data.sh`): pull resume state → backfill → deep verify →
   push → **power itself off** (billing ends; the run costs well under $1).
   An hourly push timer bounds an instance loss at one hour of downloads.
   Access is SSM only — no key pairs, no inbound ports.
3. **One writer.** The ledger's writer is wherever the backfill runs; every
   other machine is a reader. A handoff is push-then-pull, never two writers.
4. **Transport is delegated; trust is not.** `aws s3 sync` does transfer
   (retries, multipart, credentials — its solved problems; no new Python
   dependencies). Every pull re-hashes what landed against the ledger's
   sha256s — the same stance `verify-downloads` takes toward the local disk.
5. **Push order is a correctness property.** Zips sync first, `ledger.json`
   uploads last, so a mirror reader never sees a ledger referencing files the
   mirror doesn't hold. An interrupted push leaves the previous ledger
   describing the previous complete state.
6. **Local development does not move.** Fixtures, samples, and `make dev-data`
   stay the daily loop; `mirror pull --title N` fetches a verified slice when a
   task needs real history. Remote *compute* for the bulk load is deferred to
   Session 8, decided against a measured database size, not a guess.

To make the ledger survive the trip, its paths went machine-portable: entries
record `{label}/{filename}` relative to the corpus directory, resolved against
the ledger's own location; skip decisions check the *computed* local target,
never the recorded string; pre-existing absolute paths normalize on load.

## Alternatives set aside

- **Develop remotely against the full corpus** — trades a 20 ms local test loop
  for network round-trips, to solve a capacity problem that no longer exists at
  9 GB.
- **EBS/EFS as the store** — pays for provisioned capacity to serve one box;
  S3 is cheaper, multi-reader, versioned, and survives the instance.
- **Requester-pays public bucket now** — the corpus is public-domain US law and
  sharing it is in-mission, but that's a distribution decision for later; a
  private mirror loses nothing meanwhile.
- **Spot instance** — the run is interruption-proof, so spot would work, but
  saving ~70% of $0.40 is not worth the extra moving part.

## Consequences

- The backfill becomes fire-and-forget: launch, and the box stops itself when
  the corpus is complete and verified.
- `unavailable` entries ride the ledger to every consumer — nobody re-asks OLRC
  settled questions from a fresh machine.
- The bucket (~$0.25/mo) is the only standing cost; role and scripts are reusable
  for re-runs when new release points appear.
- `data/` remains gitignored and never committed; the mirror is where the corpus
  lives long-term (documentation duty 4's manifests still ride along in git).
