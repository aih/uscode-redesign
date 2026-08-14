---
license: cc0-1.0
language:
- en
pretty_name: United States Code, versioned by release point
size_categories:
- 100K<n<1M
task_categories:
- text-retrieval
- question-answering
- summarization
tags:
- legal
- legislation
- statutes
- us-code
- uslm
configs:
- config_name: current
  default: true
  data_files:
  - split: train
    path: current/train-*
- config_name: versions
  data_files:
  - split: train
    path: versions/train-*
---

# United States Code, versioned by release point

Every section of the United States Code, as published by the Office of the Law
Revision Counsel (OLRC) at [uscode.house.gov](https://uscode.house.gov), across
every release point from 113-21 (July 18, 2013) through the present. A release
point is OLRC's republication of the Code after a batch of Public Laws is
classified; this dataset covers 381 of them over 58 titles.

Each row carries the section's plain text, its verbatim USLM XML, its
citation, its place in the Code's hierarchy, and its release-point metadata.
The text of a section that did not change between release points is stored
once, with the list of release points that published it.

## Configs

- **`current`** (65,938 rows) — one row per section, carrying the text in
  force at the newest release point that section appears at. Use this for
  retrieval, RAG, and any pipeline that wants "the US Code, today".
- **`versions`** (489,738 rows) — one row per distinct text a section has had,
  with `first_release`/`last_release`/`releases` recording when it was in
  force. Use this to follow a provision over time or to read the Code as it
  stood at a past release point.

## Usage

```python
from datasets import load_dataset

current = load_dataset("dreamproit/uscode", "current", split="train")

# Title 16, sections only, plain text:
t16 = current.filter(lambda row: row["title"] == "16")

# One provision's history, oldest text first:
versions = load_dataset("dreamproit/uscode", "versions", split="train")
history = sorted(
    versions.filter(lambda row: row["identifier"] == "/us/usc/t16/s45f"),
    key=lambda row: row["first_release_seq"] or 0,
)
```

`content_hash` is shared between the two configs: a `current` row and the
`versions` row holding the same text carry the same value.

## Data fields — `current`

| Field | Type | Description |
|---|---|---|
| `identifier` | string | USLM logical path, e.g. `/us/usc/t16/s45f`. Stable across release points unless the section is renumbered. |
| `citation` | string \| null | `16 U.S.C. § 45f`. Null for appendix and act-style identifiers (see limitations). |
| `title` | string | Title number as a string — `5a` (an appendix title) and `5` are different titles. |
| `title_name` | string | `CONSERVATION` |
| `title_is_positive_law` | bool | Whether the title has been enacted as positive law. |
| `num` | string \| null | The designator as published, e.g. `§ 45f.` |
| `num_value` | string \| null | The machine designator, e.g. `45f`. May contain U+2013 (en dash). |
| `heading` | string \| null | Section heading. |
| `status` | string \| null | `repealed`, `omitted`, `transferred`, `reserved`, `renumbered`, … Free text, not a closed set. |
| `parent_identifier` | string \| null | The enclosing subdivision at this release point. |
| `ancestors` | list of struct | The chain from the title down to the parent: `{identifier, level, num, heading}` per node, from the newest release's structure. |
| `seq_in_title` | int32 | Reading order within the title at this release point. |
| `text` | string | Plain text of the statutory body: one line per provision, designator and heading on the provision's first line. Notes, source credit, and tables of contents are excluded — they have their own fields. |
| `xml` | string | The section's USLM XML, verbatim, namespace declarations included. |
| `source_credit` | string \| null | The enactment/amendment credit line. |
| `notes` | list of struct | OLRC's editorial and statutory notes: `{topic, role, heading, text}` per note. The notes' verbatim XML is inside `xml`. |
| `uslm_schema` | string | Schema of the source file, e.g. `uslm-1.0.15`. |
| `release_label` | string | The release point this row's text and placement come from, e.g. `119-102not101`. |
| `release_seq` | int32 | The release point's position in OLRC's publication order. Labels do not sort lexically; sort on this. |
| `currency_date` | date | The date the release point is current through. A label containing `not` means listed laws are excluded even before this date. |
| `release_congress` | int32 | `119` |
| `release_law` | int32 | `102` |
| `release_update` | int32 \| null | The `u1` re-issue number, when present. |
| `release_excluded_laws` | list of int32 | The laws named by `not` in the label. |
| `content_hash` | string | SHA-256 (hex) of the XML with every `@id` removed — the key that joins a row to its `versions` counterpart. |
| `text_since` | string \| null | The earliest release point that published this exact text. |

## Data fields — `versions`

`identifier` through `content_hash` as above, plus:

| Field | Type | Description |
|---|---|---|
| `uslm_version` | string | USLM generation of this version's XML: `1` or `2`. |
| `first_release` / `last_release` | string \| null | The earliest and latest release points that published this text. |
| `first_release_seq` / `last_release_seq` | int32 \| null | Their positions in publication order. |
| `first_currency_date` / `last_currency_date` | date \| null | Their currency dates. |
| `releases` | list of string | Every release point that published this text, in publication order. |
| `release_count` | int32 | Length of `releases`. |
| `is_current` | bool | Whether this is the text in force at the newest release point — the row the `current` config carries. |
| `identifier_collision` | bool | True on the 160 (identifier, release) pairs where the source published two elements under one identifier. |
| `parent_identifier` / `seq_in_title` | string / int32 \| null | Placement at this version's first mapped release point. |

## Source and provenance

The corpus is downloaded from OLRC's release-point archive at
uscode.house.gov, one zip per (title, release point), and parsed from USLM XML
(1.x and 2.x). Each ingested release point has a manifest recording the source
URL, the zip's SHA-256, and per-title section counts, in the
[source repository](https://github.com/aih/uscode-redesign) under
`data/manifests/`. The same pipeline serves
[uscode.linkedlegislation.org](https://uscode.linkedlegislation.org), where any
row's `identifier` resolves to a reader page
(`/app/us/usc/t16/s45f?release=119-99`) and `/api/v1/us/usc/…` returns the same
content over JSON or verbatim XML.

The source is polled daily. When OLRC publishes a new release point, the
corpus reloads and this dataset is re-exported and re-uploaded; the commit
message names the release point. `manifest.json` in this repo records the
export's fingerprint, row counts, and per-shard SHA-256 hashes.

## Limitations

- `citation` is null for the 461 appendix sections: their identifiers are
  act- or law-relative (`/us/usc/t5a/pl/92/463/s1`), and OLRC publishes
  nothing at the flat `5 U.S.C. App. 3` form.
- Section numbers use U+2013 (en dash), not a hyphen: `45a–1`. 5,697 sections
  contain one. Match user input against both.
- At 160 (identifier, release point) pairs the source publishes two elements
  under one identifier. Both texts are present in `versions`, flagged
  `identifier_collision`; `current` carries one of the two.
- `text` runs a headed provision's designator and heading on one line with the
  body below; the printed Code runs them into the body text.
- `ancestors` reflects the hierarchy at the newest loaded release point, for
  rows of every age.
- `status` values are OLRC's own and are not a closed set. Repealed and
  omitted sections keep their place in reading order.
- Four section identifiers embed a literal `§ ` (a converter artifact);
  `citation` and `num_value` strip it, `identifier` keeps it verbatim.

## License

The United States Code is a work of the United States Government and is in the
public domain ([CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/)).

## Maintainer

[DreamProIT](https://huggingface.co/dreamproit). Related dataset:
[bill_summary_us](https://huggingface.co/datasets/dreamproit/bill_summary_us).
