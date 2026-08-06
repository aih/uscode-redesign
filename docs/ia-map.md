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
cd frontend/src && grep -rnE 'appHref|versionsHref|diffHref|gotoHref|searchHref|syntaxHref|settingsHref|loginHref|signupHref|previewHref|\$\{APP\}/' pages components layouts
```

`Base.astro`'s props are what "chrome" means in the last column: `crumbs` (breadcrumb trail),
`release` (release context and the switcher), `bar` (the sticky `SectionBar`), `searchValue`
(prefills the one search box). Every page gets `SiteHeader` and `SiteFooter` regardless.

## Routes

| Route | Page file | Purpose | Reached from | Exits to | Chrome |
|---|---|---|---|---|---|
| `/app/` | `index.astro` | The titles loaded, in numeric order (ADR-0025) | `SiteHeader:36,43`, `SiteFooter:29`, `ErrorPage:42`, `AccountsOff:32` | a title TOC, `/app/demo`, `/app/guide` | header, footer |
| `/app/us/usc/…` | `us/usc/[...identifier].astro` | A section with the named provision anchored in place, or a structural node's TOC | `index.astro:46`, `releases.astro:87`, `search.astro:181`, `provisions.astro:64`, `goto.astro:66,116`, `Neighbors`, `SectionBar`, `KeyboardNav`, `CopyColumn`, `Breadcrumbs`, every `<ref>` in the text | prev/next/up, `/app/versions`, `/app/diff`, the API in JSON or XML, the citation URL | breadcrumb, release context + switcher, sticky bar, chapter rail |
| `/app/us/usc/?id=…` | `us/usc/index.astro` | Guid lookup in a browser; 307s to the identifier it pins | the `Cite this exact text` link on a section page | the section it resolved to | header, footer |
| `/app/versions/…` | `versions/[...identifier].astro` | Every release point at which this section's text changed | `us/usc/[...identifier].astro:197`, `diff/[...identifier].astro:176` | the text at any listed release, a diff between any two | breadcrumb only — the page spans every release point, so it is reading none |
| `/app/diff/…` | `diff/[...identifier].astro` | A reading-text redline between two release points (ADR-0026) | `versions/[...identifier].astro:88`, its own from/to picker | back to the text, `/app/versions`, the source redline, the API diff | breadcrumb only — the page is about two release points, so a bar naming one would mislead |
| `/app/releases` | `releases.astro` | Every release point, its currency date, and when the source was last checked (ADR-0036) | `SiteHeader:46`, `SiteFooter:30`, `about.astro:70`, `search/syntax.astro:219`, `AccountsOff:37` | a title at a chosen release point | header, footer |
| `/app/goto` | `goto.astro` | The one search box's target: routes a citation to its provision, anything else to `/app/search` | `SiteSearch:57` (form action), `search.astro:102,158`, `search/syntax.astro:91,288`, its own examples | the provision, or `/app/search` | header, footer, prefilled box |
| `/app/search` | `search.astro` | Keyword results (ADR-0028), strict by default (ADR-0031) | `goto.astro:45,58,123`, `search/syntax.astro` examples, its own pager | a section per result, `/app/search/syntax`, `/app/goto` | header, footer, prefilled box |
| `/app/search/syntax` | `search/syntax.astro` | The operators the search box accepts, each with a live example | `SiteFooter:47`, `SiteSearch:98`, `about.astro:84`, `search.astro:126,155`, `AccountsOff:42` | a worked search for every operator, `/app/goto`, `/app/releases` | header, footer |
| `/app/guide` | `guide/index.astro` | Contents of the user guide (ADR-0038) | `SiteHeader:55`, `SiteFooter:31`, `index.astro:38`, `demo.astro:50,56`, `GuideLayout:45,77` | any chapter | header, footer |
| `/app/guide/<chapter>` | `guide/*.md` | One chapter, nine of them | `guide/index.astro`, the pager in `GuideLayout`, `SiteFooter:42` (Keyboard shortcuts, to chapter 02 — intercepted by `KeyboardNav` into the dialog when the island has run) | the next and previous chapter, the routes it documents | header, footer, wide |
| `/app/demo` | `demo.astro` | The captioned demo video, recorded from the guide's scenarios | `index.astro:37` | `/app/guide` | header, footer |
| `/app/design` | `design.astro` | The design system: every component the reader is built from, with specimen data, and the contrast of every declared colour pair computed in the browser (ADR-0053) | `SiteFooter:49` | nothing — every link on it is a specimen under title 0, which OLRC does not publish | header, footer |
| `/app/about` | `about.astro` | What this site is, and what it is not | `SiteHeader:70`, `SiteFooter:50,67` | `/app/releases`, `/app/docs`, `/app/search/syntax`, OLRC, the repository | header, footer |
| `/app/docs` | `docs.astro` | The OpenAPI schema in this site's chrome, rather than the bare Swagger page | `SiteHeader:62`, `SiteFooter:48`, `about.astro:77`, `AccountsOff:47` | `/docs`, `/redoc`, `/openapi.json` | header, footer |
| `/app/provisions` | `provisions.astro` | The watchlist. Switched off in the UI (ADR-0034) | `SiteHeader:49`, `AuthNav:48` | a watched provision, `/app/login` | header, footer |
| `/app/settings` | `settings.astro` | How links open, and the theme. Switched off in the UI | `AuthNav:49` only — **see Unreachable routes** | `/app/login` | header, footer |
| `/app/login` | `login.astro` | Sign in. Switched off in the UI | `provisions.astro:46`, `settings.astro:52`, `signup.astro:53`, `AuthNav:35` | `/app/signup`, the `?next=` destination | header, footer |
| `/app/signup` | `signup.astro` | Create an account. Switched off in the UI | `login.astro:58`, `AuthNav:37` | `/app/login`, the `?next=` destination | header, footer |
| `/app/404` | `404.astro` | Anything under `/app` that is not a citation | any wrong URL | `/app/` | header, footer |
| `/app/preview/…` | `preview/[...identifier].ts` | The rendered fragment the hover card fetches (ADR-0024). An endpoint, not a page | `CitePreview.astro:199`, by `fetch` | — | none |
| `/app/healthz` | `healthz.ts` | Liveness for the container | the orchestrator | — | none |
| `/us/usc/…` | served by FastAPI (`citation.py`) | The bare citation URL; 307s to `/app` or `/api/v1` by `Accept:` (ADR-0010) | printed on every section page; anything a reader pastes | the reader or the API | none |

## Unreachable routes

**`/app/settings` has no inbound link from any rendered page.** Its only linker is
`AuthNav.astro:49`, and `SiteHeader` does not render `AuthNav` while `ACCOUNTS_ENABLED` is false
(ADR-0034). The single reachable link to it is prose in guide chapter 06. The page itself is not
dead — it renders `AccountsOff` and explains the link-target default — but a reader who has not read
the guide cannot get there.

`/app/login` and `/app/signup` are in the same position one hop further out: reachable only from
`/app/provisions`, `/app/settings` and each other. That is consistent with accounts being off, and
they are listed here so the state is recorded rather than assumed.

## Thinly reachable

**`/app/diff` is two hops from the text it compares.** The only link into it from outside itself is
on `/app/versions`, and the only link to `/app/versions` is one line under the section heading. A
reader on `§ 45f` who wants to know what changed goes: section → version history → pick two
releases → diff. Task B5 owns the "Compare with…" affordance that shortens this; B5 is defined in
`claude-code/WORKSTREAM-B-STATE.md`, not in `docs/backlog.md`.

**`/app/demo` has one inbound link**, on the front page, and only for a reader who has not scrolled
past the first paragraph.

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

1. **`SiteHeader`** — brand, primary nav, the single search-and-citation box (ADR-0023), the theme
   toggle. `SiteSearch` is mounted here and nowhere else; a page showing results prefills it through
   `Base`'s `searchValue` rather than rendering a second box.
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
