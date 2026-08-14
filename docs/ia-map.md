# The reader's information architecture

Every route `/app` serves, what it is for, how a reader reaches it, and where it lets them go.
Maintained alongside the routes themselves: a new page under `frontend/src/pages/` belongs in the
table below as well as in a guide chapter's `covers.routes`.

## How this was derived

The route list is `readerRoutes()` in `frontend/tests/guide.test.ts` — the same function the guide
ratchet uses, reading `frontend/src/pages/` from disk. The chapter column is each chapter's
`covers.routes` frontmatter. Neither is typed out from memory here.

```bash
# the routes the reader serves
cd frontend && npx vitest run tests/guide.test.ts

# every inbound link, with the file and line that makes it
cd frontend/src && grep -rnE 'appHref|versionsHref|diffHref|gotoHref|searchHref|syntaxHref|settingsHref|loginHref|signupHref|previewHref|classificationHref|classificationEcctHref|\$\{APP\}/' pages components layouts
```

`Base.astro`'s props are what "chrome" means in the last column: `crumbs` (breadcrumb trail),
`release` (release context and the switcher), `bar` (the sticky `SectionBar`), `searchValue`
(prefills the one search box). Every page gets `SiteHeader` and `SiteFooter` regardless.

## Routes

| Route | Page file | Purpose | Reached from | Exits to | Chrome |
|---|---|---|---|---|---|
| `/app/` | `index.astro` | The titles loaded, in numeric order (ADR-0025) | `SiteHeader:118,183,303`, `SiteFooter:84`, `ErrorPage:42`, `AccountsOff:32` | a title TOC, `/app/demo`, `/app/guide` | header, footer |
| `/app/us/usc/…` | `us/usc/[...identifier].astro` | A section with the named provision anchored in place, or a structural node's TOC | `index.astro:46`, `releases.astro:87`, `search.astro:181`, `provisions.astro:64`, `goto.astro:66,116`, `Neighbors`, `SectionBar`, `KeyboardNav`, `CopyColumn`, `Breadcrumbs`, every `<ref>` in the text | prev/next/up, `/app/versions`, `/app/diff`, the API in JSON or XML, the citation URL | breadcrumb, release context + switcher, sticky bar, chapter rail |
| `/app/us/usc/?id=…` | `us/usc/index.astro` | Guid lookup in a browser; 307s to the identifier it pins | the `Cite this exact text` link on a section page | the section it resolved to | header, footer |
| `/app/versions/…` | `versions/[...identifier].astro` | Every release point at which this section's text changed | `us/usc/[...identifier].astro:197`, `diff/[...identifier].astro:176` | the text at any listed release, a diff between any two | breadcrumb only — the page spans every release point, so it is reading none |
| `/app/diff/…` | `diff/[...identifier].astro` | A reading-text redline between two release points (ADR-0026) | `versions/[...identifier].astro:88`, its own from/to picker | back to the text, `/app/versions`, the source redline, the API diff | breadcrumb only — the page is about two release points, so a bar naming one would mislead |
| `/app/releases` | `releases.astro` | Every release point, its currency date, and when the source was last checked (ADR-0036) | `SiteHeader:202`, `SiteFooter:86`, `about.astro:69`, `search/syntax.astro:223`, `AccountsOff:37` | a title at a chosen release point | header, footer |
| `/app/classification` | `classification/index.astro` | The classification tables: the lookup box with its table scope select (`?scope=`, ADR-0068), the session being classified now, the registry of every table, and — with `?title=`+`?section=` — every row ever classified to one section (ADR-0067) | `SiteHeader:209`, `SiteFooter:89`, `palette.ts:70`, `classification/[congress]/[session].astro:181`, `classification/ecct.astro:80`, `ClassificationLookup` (the unscoped no-script form's action) | one table, the ECCT, a section in the reader | header, footer |
| `/app/classification/<congress>/<session>` | `classification/[congress]/[session].astro` | One classification table, sorted in public law or U.S. Code order, filtered by law, law section, title or section, 50 rows to a page — and the lookup scoped to the table, whose `?q=` is answered on the page (ADR-0068) | `classification/index.astro:341,375`, the lookup's own suggestions (`api/classification.py`'s `_app_path`), `ClassificationLookup` (the scoped form posts back to the page) | a section in the reader, govinfo, the OLRC statviewer, the ECCT, back to the index | header, footer, wide |
| `/app/classification/ecct` | `classification/ecct.astro` | The Editorial Classification Change Table — where a provision moved without a law moving it | `classification/index.astro:392`, `classification/[congress]/[session].astro:332` | back to the index; no cell links into the reader, by rule | header, footer, wide |
| `/app/goto` | `goto.astro` | The one search box's target: routes a citation to its provision, anything else to `/app/search` | `SiteSearch:57` (form action), `search.astro:102,158`, `search/syntax.astro:91,288`, its own examples | the provision, or `/app/search` | header, footer, prefilled box |
| `/app/search` | `search.astro` | Keyword results (ADR-0028), strict by default (ADR-0031) | `goto.astro:45,58,123`, `search/syntax.astro` examples, its own pager | a section per result, `/app/search/syntax`, `/app/goto` | header, footer, prefilled box |
| `/app/search/syntax` | `search/syntax.astro` | The operators the search box accepts, each with a live example | `SiteFooter:99`, `SiteSearch:98`, `about.astro:83`, `search.astro:126,155`, `AccountsOff:42` | a worked search for every operator, `/app/goto`, `/app/releases` | header, footer |
| `/app/guide` | `guide/index.astro` | Contents of the user guide (ADR-0038) | `SiteHeader:241`, `SiteFooter:98`, `index.astro:38`, `demo.astro:50,56`, `GuideLayout:45,77` | any chapter | header, footer |
| `/app/guide/<chapter>` | `guide/*.md` | One chapter, ten of them | `guide/index.astro`, the pager in `GuideLayout`, `SiteFooter:109` (Keyboard shortcuts, to chapter 02 — intercepted by `KeyboardNav` into the dialog when the island has run) | the next and previous chapter, the routes it documents | header, footer, wide |
| `/app/demo` | `demo.astro` | The captioned demo video, recorded from the guide's scenarios | `index.astro:37` | `/app/guide` | header, footer |
| `/app/design` | `design.astro` | The design system: every component the reader is built from, with specimen data, and the contrast of every declared colour pair computed in the browser (ADR-0053) | `SiteFooter:130` | almost nothing — every link on it is a specimen under title 0, which OLRC does not publish, and the classification specimen's govinfo and statviewer links name public law 0-1 and volume 0. The two exceptions are real: the lookup specimen submits to `/app/classification`, and the palette specimen's rows are `siteCommands()` | header, footer |
| `/app/about` | `about.astro` | What this site is, and what it is not | `SiteHeader:266`, `SiteFooter:136,149` | `/app/releases`, `/app/docs`, `/app/search/syntax`, OLRC, the repository | header, footer |
| `/app/docs` | `docs.astro` | The OpenAPI schema in this site's chrome, rather than the bare Swagger page | `SiteHeader:244`, `SiteFooter:121`, `about.astro:76`, `AccountsOff:47` | `/docs`, `/redoc`, `/openapi.json` | header, footer |
| `/app/provisions` | `provisions.astro` | The watchlist. Switched off in the UI (ADR-0034) | `SiteHeader:190`, `AuthNav:48` | a watched provision, `/app/login` | header, footer |
| `/app/settings` | `settings.astro` | How links open, and the theme. Switched off in the UI | `palette.ts:88` (the command palette, ADR-0062), `AuthNav:49` | `/app/login` | header, footer |
| `/app/login` | `login.astro` | Sign in. Switched off in the UI | `provisions.astro:46`, `settings.astro:52`, `signup.astro:53`, `AuthNav:35` | `/app/signup`, the `?next=` destination | header, footer |
| `/app/signup` | `signup.astro` | Create an account. Switched off in the UI | `login.astro:58`, `AuthNav:37` | `/app/login`, the `?next=` destination | header, footer |
| `/app/404` | `404.astro` | Anything under `/app` that is not a citation | any wrong URL | `/app/` | header, footer |
| `/app/preview/…` | `preview/[...identifier].ts` | The rendered fragment the hover card fetches (ADR-0024). An endpoint, not a page | `CitePreview.astro:199`, by `fetch` | — | none |
| `/app/healthz` | `healthz.ts` | Liveness for the container | the orchestrator | — | none |
| `/us/usc/…` | served by FastAPI (`citation.py`) | The bare citation URL; 307s to `/app` or `/api/v1` by `Accept:` (ADR-0010) | printed on every section page; anything a reader pastes | the reader or the API | none |

## Unreachable routes

`/app/settings` was here until ADR-0062. Its only linker was `AuthNav.astro:49`, which
`SiteHeader` does not render while `ACCOUNTS_ENABLED` is false (ADR-0034), leaving prose in guide
chapter 06 as the one way in. The command palette's `Reading settings` row (`lib/palette.ts:88`)
now links it from every page — behind ⌘K, so it is a keyboard route rather than a visible one.

`/app/login` and `/app/signup` are in the same position one hop further out: reachable only from
`/app/provisions`, `/app/settings` and each other. That is consistent with accounts being off, and
they are listed here so the state is recorded rather than assumed.

## Thinly reachable

**`/app/diff` is two hops from the text it compares, unless the reader knows ⌘K.** The only visible
link into it from outside itself is on `/app/versions`, and the only link to `/app/versions` is one
line under the section heading. A reader on `§ 45f` who wants to know what changed goes: section →
version history → pick two releases → diff. The command palette's `Compare with the previous
release point` row (ADR-0062, `lib/palette.ts:131`) makes it one keystroke, against the release
point before the one on screen. Task B5 still owns the "Compare with…" affordance on the section
header, and the arbitrary pair; B5 is defined in `claude-code/WORKSTREAM-B-STATE.md`, not in
`docs/backlog.md`.

**`/app/demo` has one inbound link**, on the front page, and only for a reader who has not scrolled
past the first paragraph.

**Six routes are behind the header's menu rather than in it** (ADR-0061): `/app/releases`,
`/app/classification`, `/app/guide`, `/app/docs`, `/app/about` and the Downloads control are behind
**More**, so the header does not show where they are. Each keeps a link in the footer, which lists
all ten destinations in the open, and each is still one click from any page once More is open.

## Duplicate paths

Three candidates were checked; none is a duplicate, and each is recorded so the question is not
re-opened.

- **`/app/goto` and `/app/search`** are one path, not two. `goto` is a router: it redirects a
  citation to its provision and everything else to `search`. `SiteSearch` posts to `goto` alone.
- **`SectionBar`, `Neighbors` and `KeyboardNav`** are three prev/next affordances on a section page:
  the top of the text, the bottom of the text, and the keyboard. That is what B1 asks for.
- **Navigation *inside* a section is a fourth set** (ADR-0055), and none of it is a route:
  `SectionContents` above the text links to each top-level provision and to `#section-source` and
  `#section-notes`; the section bar's own number links to `#main`; and `KeyboardNav`, now in `Base`
  rather than on the section page, binds `c`, `[`, `]`, `s`, `n` and `t` to the same places. The
  shortcut list itself is `ShortcutsDialog`, a modal `<dialog>` on every page rather than a page of
  its own — `?` opens it, and the footer's link is the no-script fallback to guide chapter 02.
- **The from/to picker on `/app/versions` and on `/app/diff`** is the same form on two pages. The
  first chooses a comparison; the second changes one already on screen.

The section page's `formats` row links `Version history` to `/api/v1/sections/…/versions` while the
line under the heading links the same words to `/app/versions/…`. Same label, different surfaces.
The `formats` row is the machine-format row and is read as one, so the API link stays and the label
names its format.

## The chrome

One set of components, in one order, on every page that is a place in the Code — ADR-0043 and
ADR-0044. Before those, only `us/usc/[...identifier].astro` passed `crumbs`, `release` or `bar` to
`Base`; every other page got the header and footer and nothing else.

1. **`SiteHeader`** — brand, and four things: **Titles**, **My Provisions**, the single
   search-and-citation box (ADR-0023) and **More** (ADR-0061). `SiteSearch` is mounted here and
   nowhere else; a page showing results prefills it through `Base`'s `searchValue` rather than
   rendering a second box. Titles and More are `<details>` whose panels open over the page; the two
   display switches and the account control are rows of More. Below 64em the header is a 52px bar —
   **Menu**, the site's name, and the light/dark switch — with the search box on a full-width row
   under it, and Menu opens a sheet in which More's rows sit in the open rather than behind a second
   disclosure (ADR-0064). The footer's list is the same disclosure opening in flow (ADR-0058). The
   wordmark is written twice, once per band, and exactly one copy is displayed.
2. **`Breadcrumbs`** — the citation hierarchy, each ancestor a link, the current node last and not a
   link, carrying `aria-current="page"`.
3. **`ReleaseContext`** — which release point is being read, its currency date, whether it is the
   newest, the exception on a `not` label, and the release the answer actually came from when that
   differs from the one asked for. `ReleasePicker` — the newest, a date, or a named release point,
   each preserving the provision — is a `<details>` in `.contextbar` whose closed summary is the
   release-point line the bar already carried, and whose open panel is absolutely positioned
   (ADR-0056, amending ADR-0044's placement of both in the page body).
4. **`SectionBar`** — sticky: the section's own number, heading and status, with prev/next naming
   the neighbour and an up link to the parent.
5. **`ChapterRail`** — the sections either side of this one in the parent subdivision, in reading
   order, with status badges shown in place. A left rail at 64em and wider; a disclosure above the
   text below that.
6. **`Neighbors`** — prev/next again at the foot of the text, with headings and badges.

Pages that are not a place in the Code — the guide, `/app/about`, the auth pages — carry 1 alone.
