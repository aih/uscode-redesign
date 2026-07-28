# Prior art: `loadusc-xcitedb` and `versions`

Two existing dreamproit repositories already solved parts of this problem. CLAUDE.md's "External
source etiquette" says to reuse them rather than rediscover solved problems; this document records
what each actually does, what we take, and — with reasons — what we deliberately do differently.

Read at these commits:

| Repo | Commit | Upstream |
|---|---|---|
| `../loadusc-xcitedb` | `d16f1ee` | <https://github.com/dreamproit/loadusc-xcitedb> |
| `../versions` | `c937641` | <https://github.com/dreamproit/versions> |

Line references below are to those commits.

---

## 1. `loadusc-xcitedb` — release-point downloader and XCiteDB loader

A small Python package (~1,270 lines including config data) with four modules and one shell script,
installed onto a server and run nightly from cron (`updateusc.sh`, `README.adoc:33-54`).

### What it does

**`loadusc/downloadusc.py` (326 lines) — scrape and download.**
`getUSCReleasePoints()` (`:155`) fetches two pages with BeautifulSoup: `download.shtml` for the
*current* release point and `priorreleasepoints.htm` for the prior ones. From each prior-RP `<a
class="releasepoint">` it takes the label out of the href (`getDirName`, `:120` — splits on `@`),
and mines the link *text* for the currency date (`getReleaseDate`, `:133`) and the affected titles
(`getTitlesAffected`, `:142`). It writes `uscreleasepoints.json`, an array of
`{name, date, titlesAffected, url}`. `downloadUSCReleasepointZips()` (`:247`) then walks that list
and calls `getAndUnzipURL()` (`:73`), which downloads each affected title's zip and extracts it to
`USC_RELEASEPOINTS/{label}/`.

**`loadusc/loaduscxcite.py` (160 lines) — load into XCiteDB.**
`loadUSCReleasePointsFromJSON()` (`:62`) reverses the inventory into chronological order, joins each
RP label to a public-law enactment date from an external `publawsDict.json` dump, and shells out to
the XCiteDB binary once per RP:
`XCiteDB -db <xmldb> -dc document.conf -date <mm/dd/yyyy> load-xml -r <rp-dir>` (`:120-135`).

**`loadusc/getxcite.py` (271 lines) — query XCiteDB.**
Two functions, both `subprocess.run` wrappers returning parsed JSON:
- `getIdentifier(identifier, date)` (`:39`) — retrieve a node's XML as of a date.
- `getChangeDates(identifier, fromDate, toDate)` (`:146`) — the change log for a node, as
  `[{identifier, date, action}]` where action is `created` / `modified` / `deleted`.

**`loadusc/constants.py` (95 lines)** — env-driven paths plus the identifier and citation regexes.
**`data/document.conf` (281 lines)** — XCiteDB's document model: per element, whether it is a
hierarchical level, its designation style, and the **short form used in identifiers**.

### What we reuse directly

**The RP inventory JSON shape.** `{name, date, titlesAffected, url}` (`README.adoc:24`) is already
ours: `ReleasePointEntry.as_json()` (`ingest/inventory.py:113-122`) emits exactly those keys so the
two projects can read each other's files. We add `seq` and `description` as extra keys, which their
reader ignores.

**The download-URL construction rules**, all now in `title_zip_url` / `ingest/inventory.py`:
- RP page URL → zip URL: rewrite `usc-rp` → `xml_uscAll` and `.htm(l)` → `.zip` (`:226-228`,
  driven by `USC_RP_TEXT` / `USC_XML_TEXT`, `constants.py:82-83`).
- All-titles zip → single-title zip: `re.sub(r"_usc.*@", "_usc" + title + "@", url)` (`:93`).
- Title-number normalization: lowercase, then zero-pad to two digits *ignoring* a trailing `a`, so
  `5` → `05` and `5A` → `05a` (`:89-91`). This is the appendix-title handling of CLAUDE.md gotcha 7,
  and it is not guessable from the URL alone.

**`titlesAffected` drives ingest.** `getAndUnzipURL` downloads only the affected titles for each RP
(`:87`), with `['All']` as the escape hatch. That is CLAUDE.md gotcha 10's storage strategy, learned
here first.

**Validity check on the response body.** `zipfile.is_zipfile(io.BytesIO(r.content))` (`:95`) —
uscode.house.gov returns HTTP 200 with an HTML error page for a missing zip, so status code alone is
not enough. Session 6's bulk downloader must keep this check.

**The `u1` fallback.** If `…u1.zip` does not come back as a zip, retry the same URL without the `u1`
(`:99-102`). Related to gotcha 4 — 17 of 385 published RPs carry a `u1` suffix, and the file may or
may not exist under it.

**Cache on disk, never re-download.** `if not os.path.exists(dir_name) or redownload` (`:86`).
Ours is per-file rather than per-directory (`ingest/download.py:44-45`).

**`document.conf`'s short-form table is the authority behind our `@identifier` path segments.**
`title`→`t`, `subtitle`→`st`, `part`→`pt`, `subpart`→`spt`, `chapter`→`ch`, `subchapter`→`sch`,
`section`→`s`, `division`→`d`, `toc`→`toc`, `notes`→`nt`; subsection and below have an **empty**
short form, which is why `/us/usc/t16/s45f/c/5` has bare `c/5` and not `ss/c`. Keep this file as the
reference when we add `/nt` (notes) retrieval, and note it also marks `notes`, `sourceCredit` and
`footnote` as `is_main_content: false, skip_text: true` — a ready-made answer for what our reader's
notes toggle should hide (Day 4).

**XCiteDB query patterns, for the second Repository implementation.** `getxcite.py` is the closest
thing we have to a spec for the XCiteDB CLI, and it maps cleanly onto `storage/repository.py`:

| Repository method | XCiteDB invocation | Source |
|---|---|---|
| `get_section(identifier, release)` | `query -match <identifier> -date <mm/dd/yyyy>` | `getxcite.py:122-131` |
| `get_toc(...)` | `query -match-start <ancestor> -match-end <descendant>` | `getxcite.py:108-115` |
| `versions(identifier)` | `query -match-start <identifier>/ -log`, merged with `query -match <identifier> -log` | `getxcite.py:220-265` |

Two details in there that would cost a day to rediscover:
- **Identifiers are en-dashed.** `identifier.replace('-', '–')` (`:72`, `:185`) — XCiteDB stores
  U+2013, not U+002D. Any XCiteDB-backed repository must do this at the boundary.
- **Big levels are stripped from section identifiers.** `/us/usc/t16/ch1/schII/s45f` is normalized
  to `/us/usc/t16/s45f` (`:117-119`, `:215-217`) — XCiteDB keys sections by title + section only.
  Our Postgres implementation stores the full path, so this is an XCiteDB-side adapter concern, not
  a schema change.
- **`versions()` needs two queries.** `-match-start` finds changes to descendants; `-match` finds
  changes to the section node itself. Neither alone is the full history.

### What we deliberately do differently

**Release points are keyed by label, not by date.** `loaduscxcite.py` resolves each RP to a public
law's enactment date and hands XCiteDB `-date` (`:92-94`); everything downstream is date-addressed.
We make the RP label primary and treat `?date` as a query that *resolves* to an RP. Two reasons:
RP labels do not sort and do not correspond 1:1 to dates (gotcha 4), and at a "not" release point the
text is genuinely not current through the stated date (gotcha 5) — a date-only interface cannot
express that, and `served_from` exists precisely to report it.

**No external public-law dump.** Their date resolution depends on `publawsDict.json`, itself derived
from a MongoDB query documented only as a comment (`utils.py:14-16`). Worse, the RPs it can date are
filtered to those matching neither `not` nor `u1$` (`loaduscxcite.py:74-80`) — exactly the
awkward RPs. We take `currency_date` straight from the inventory page text, so every RP is dated
with no external dependency. Their committed inventory has **202** RPs (last dated 04/28/2020); ours
seeds **382**.

**Ordering is materialized, not implicit.** They rely on list order plus a reversal and an index
dict (`:68`, `:81-85`). We assign a global `seq` from page position and store it, because it is the
only reliable total order (`ingest/inventory.py` docstring).

**A tolerant inventory parser.** `getTitlesAffected` (`:142`) assumes every link text ends in
`affecting title(s) …` and strips `and`/spaces. Against the current page that is not enough: there
are duplicate `<li>` entries (one with *different* affected titles between its two appearances),
commented-out entries for RPs that were never published, singular "title", Oxford "and", unpadded
dates, and a *second* trailing date that is not the currency date. Our parser handles each case with
a test; see the `ingest/inventory.py` module docstring.

**TLS verification stays on.** `SSLWarningSuppressor` (`:42-64`) disables certificate verification
for `uscode.house.gov` and silences the warning, passing `verify=False` on every call. The
site's certificate validates today. If it stops, we pin a CA bundle rather than disable verification.

**Polite, resumable, verifiable downloads.** Theirs has no rate limiting, no User-Agent, retries up
to 20 times with no backoff or sleep (`:97-108`), and buffers each zip fully in memory. Ours
throttles to 1 req/sec (`ingest/download.py:80-85`), streams to a `.part` file and renames only on
completion so an interrupted download is never mistaken for a cached one (`:47-56`), and records a
sha256 (`:72`).

**Provenance manifests.** No equivalent exists upstream. Every ingest here writes
`data/manifests/{release}.json` (`ingest/manifest.py`) — source URL, timestamp, zip sha256, per-title
counts (PLAN §11.4).

**Content dedupe.** They load every RP wholesale into XCiteDB. We hash the guid-stripped
`content_key` and store one row per distinct text (ADR-0007) — measured at 2 new / 5,093 deduped for
Title 16 across two adjacent RPs.

**The query layer is behind an interface, not imported by the web service.** `versions`'
Flask service imports `loadusc.getxcite` directly (`services_py/index.py:23`), so the storage engine
is wired into the HTTP handlers. Architecture rule 1 exists to prevent exactly that: XCiteDB becomes
one `Repository` implementation, and no API handler learns it exists.

**CLI parsing stays in `__main__`.** `processUSCReleasePoints()` reads a module-global `args` from
inside the function body (`:278`), so importing the module and calling it as a library raises
`NameError`. Our entry points live in `ingest/__main__.py` and the library functions take arguments.

**One bug worth not inheriting:** `downloadUSCReleasepointZips` (`:255-266`) skips the last (oldest)
RP inside the loop, then after the loop calls `getAndUnzipURL(url, dir_name, titlesAffected=['All'])`
using leftover loop variables — `url` is the oldest RP's, but `dir_name` was last assigned on the
*second*-oldest iteration. The oldest release point's files land in the wrong directory.

---

## 2. `versions` — the temporal-diff display site

Two Angular applications and a Flask service, deployed behind Nginx (`README.adoc:73-235`). This is
the working predecessor of what we are building: it already shows a U.S. Code provision at two points
in time, side by side and diffed.

### What it does

**`Demo_UI/` — the diff tool** (`package.json:2`, `document-date-diff` v0.4.0; Angular 11 +
Material). One route. The user picks a document type, types a citation, picks two dates, and gets a
three-tab result: Compare, From, To (`home/home.component.html:54-65`). `searchDocument()`
(`home/home.component.ts:98`) issues one request, then diffs the two returned XML strings **in the
browser** with `@emmetio/xml-diff` (`package.json:30`, called at `:180`) and renders the result via
`[innerHTML]` through a `safeHtml` pipe. `home/ruler.js` (84 lines) paints a change minimap beside
the scrollbar.

**`services_py/index.py` (189 lines) — the Flask API.** Two endpoints:
- `GET /services/law/<path:identifier>?date=` (`:71`) — one document at one date.
- `GET /services/getDocument?cite=&fromDate=&toDate=` (`:112`) — returns `{fromDoc, toDoc,
  changeDates}` in a single response (`:150-154`).

`citeToIdentifier()` (`:44`) converts `26 USC 6343(b)` → `/us/usc/t26/s6343/b`, using
`USC_CITE_REGEX` from `loadusc` (`constants.py:92`).

**`Home_UI/`** is a static Bootstrap marketing landing page built with gulp. **`services/index.js`**
is a dead Express stub that serves four fixed XML files regardless of the query (`:18-39`) — a
pre-Flask prototype, not live code.

### What we reuse directly

**The diff algorithm and its configuration.** Retrieve the same identifier at two dates, diff the two
XML strings, render inline `<ins>` / `<del>`. `@emmetio/xml-diff` is structure-aware — it diffs XML
rather than treating it as text, so attribute and element changes don't smear across the output.
Critically, it is called with `{dmp: {Diff_Timeout: 0}}` (`home.component.ts:148-150`): the
underlying diff-match-patch bails out on a timeout by default and returns a *worse* diff, so this is
disabled to force a complete one. Reuse both the library and that option in the Astro app (ADR-0011).

**The change-date strip — this is our version timeline (Day 4).** `getChangeDates` returns raw log
entries; the UI dedupes dates, sorts them, and renders each as clickable text with `◀from` and
`▶to` arrows that set the respective date picker (`home.component.html:47`, logic at
`home.component.ts:168-177`). Two refinements worth keeping:
- `created` / `deleted` entries are filtered to identifiers matching `/\/s[0-9][^\/]*$/`
  (`:173-174`) — i.e. the *section itself* appearing or disappearing, as distinct from a subsection
  changing. That is how the UI can say "this section did not exist yet" rather than showing an empty
  document, and it pairs with our gotcha 3 (an identifier can vanish without being repealed).
- Change dates are collected across the whole subtree, so a subsection edit surfaces on the
  section's timeline.

**`ruler.js` as-is.** 84 lines, no dependencies, merges adjacent markers so a heavily-edited section
doesn't become a solid bar (`canCollapseMarkers`, `maxCombined: 20`), clamps marker height to a
3px minimum so single-word changes stay visible. Port to TypeScript unchanged.

**`citeToIdentifier` and `USC_CITE_REGEX`.** Ready-made for a citation search box; handles
`26 USC 6343`, `26 U.S.C. 6343(b)`, and passes through anything already in identifier form
(`index.py:46-47`). It does **not** handle prose citations ("Section 501 of…") — their TODO at
`:41-43`, still open.

**`Demo_UI/src/assets/uslm.css` (3,238 lines) as a presentation reference.** Version 2.07 of what is
recognizably GPO's own USLM stylesheet — print-width constraints for `uscDoc` (426pt margins),
per-level indent rules, note and source-credit styling. Use it to cross-check element coverage in
`web/uslm_html.py` and its Astro successor, especially for the table/indent handling `Uslm2Parser`
still lacks (Day 7).

**The sample-query dropdown.** A fixed list of citations known to have interesting version history
(`home.component.ts:29-39`), e.g. `15 USC 637(d)(16)` and `/us/usc/t26/s501/c/12/E`. Cheap, effective
demo affordance, and a ready-made source of manual test cases.

**The reverse-proxy split.** Nginx serves the static UI at `/` and proxies `/services` to the
application server (`nginx.conf.sample:56-63`). That is structurally ADR-0010's `/app` vs `/api/v1`
split, one layer down.

### What we deliberately do differently

**One URL per provision.** Their entire app is a single route; the citation and both dates are form
state, not addressable. You cannot link to a provision, a browser cannot bookmark one, and a crawler
sees nothing. Our thesis is the opposite (ADR-0009, ADR-0010): `/us/usc/t16/s45f/c/5` is the URL,
server-rendered, `Accept`-negotiated, with `?release=` / `?date=` as explicit qualifiers.

**No `bypassSecurityTrustHtml` on stored XML.** `safe-html.pipe.ts:12` disables Angular's sanitizer
and injects database content straight into the DOM. We transform USLM into HTML server-side in
`web/uslm_html.py`, emitting a known set of elements rather than passing markup through.

**HTML conversion, not CSS-namespaced raw XML.** `uslm.css` styles USLM elements directly via
`@namespace uslm "http://schemas.gpo.gov/xml/uslm"` (`:2`). It is elegant, and it couples display to
the schema — note that the declared namespace is the **2.x** one, so USLM 1.x documents (our primary
fixture, and every RP before the 2.x migration) would not match a single selector. Architecture
rule 2's whole point is that downstream layers stay schema-agnostic; converting to semantic HTML in
one designated place is how we keep that true across both schemas.

**Dates resolve to release points, and we say which.** Their minimum date is a hard-coded
`new Date(2014, 0, 16)` (`home.component.ts:19`) with a comment noting it is whatever XCiteDB happens
to hold, and "today" is stringified client-side. We resolve `?date` against the seeded inventory and
report `served_from` when the answer comes from an earlier RP (gotcha 10) — answer, but never
silently.

**Diff at the section atom, server-side.** Diffing whole documents in the browser is fine for one
section and does not survive Title 42 (gotcha 6). Sections are our storage atom (ADR-0001), so diffs
are bounded by construction and can be computed or cached server-side.

**A much smaller frontend.** Two Angular apps, gulp, Bootstrap, jQuery, Angular Material, Flex
Layout, `rxjs-compat`, plus a dead Express service — for one form and three tabs. One Astro 5 +
USWDS app (ADR-0011), consuming `/api/v1` only.

**Real tests.** Every `*.spec.ts` in `Demo_UI` is an unmodified Angular CLI stub; nothing tests
`citeToIdentifier`, the change-date reduction, or the Flask endpoints. `make test` is our merge gate
(162 tests and counting), and `tests/test_architecture.py` enforces the boundaries this repo's rules
describe.

**Correct HTTP status codes.** `getDocs` returns validation failures as HTTP 200 with
`{'success': False}` (`index.py:134`, `:145`), so a caller cannot distinguish a bad date from a
result. FastAPI gives us proper status codes and we use them.

---

## 3. Summary of the inheritance

| Concern | Source | Status here |
|---|---|---|
| RP inventory JSON shape | `loadusc-xcitedb` `README.adoc:24` | Adopted verbatim (`ingest/inventory.py:113`) |
| Zip URL construction, title padding, `05a`/`18a` | `downloadusc.py:88-93`, `:226-228` | Adopted (`title_zip_url`) |
| `titlesAffected` drives which titles to fetch | `downloadusc.py:87` | Adopted; gotcha 10 |
| `is_zipfile` body check, `u1` fallback | `downloadusc.py:95`, `:99-102` | Adopted for Session 6 |
| Identifier short-form vocabulary | `data/document.conf` | Reference for `@identifier` and `/nt` |
| XCiteDB CLI query patterns, en-dash, big-level stripping | `getxcite.py:39`, `:146` | Spec for the future XCiteDB `Repository` |
| Structure-aware XML diff with `Diff_Timeout: 0` | `home.component.ts:148-180` | Adopted for Day 4 |
| Change-date timeline with from/to arrows | `home.component.ts:168-177` | Adopted for Day 4 |
| `ruler.js` change minimap | `Demo_UI/src/app/home/ruler.js` | Port to TS unchanged |
| `citeToIdentifier`, `USC_CITE_REGEX` | `services_py/index.py:44`, `constants.py:92` | Adopted for citation search |
| `uslm.css` presentation rules | `Demo_UI/src/assets/uslm.css` | Reference only — we emit HTML |
| Date as primary retrieval key | both | **Replaced** by release-point label + `served_from` |
| External `publawsDict.json` for dating RPs | `loaduscxcite.py:92-94` | **Dropped** — dates come from the inventory page |
| `verify=False` on uscode.house.gov | `downloadusc.py:42-64` | **Rejected** — verification stays on |
| Unthrottled, in-memory, unverified downloads | `downloadusc.py:73-118` | **Replaced** — 1 req/s, streamed, sha256, manifests |
| Load every RP wholesale | `loaduscxcite.py` | **Replaced** by content dedupe (ADR-0007) |
| SPA with the citation as form state | `Demo_UI` | **Replaced** by one URL per provision (ADR-0009/0010) |
| `bypassSecurityTrustHtml` on stored XML | `safe-html.pipe.ts:12` | **Rejected** — server-side HTML conversion |
| CSS `@namespace` styling of raw XML | `uslm.css:2` | **Rejected** — 2.x-only, couples display to schema |
| Storage engine imported by the web service | `services_py/index.py:23` | **Rejected** — architecture rule 1 |
