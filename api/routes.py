"""The machine surface: PLAN §4's routes under `/api/v1`, and nothing else.

Two families, on purpose:

  * **`/api/v1/us/usc/…`** mirrors the USLM `@identifier` exactly, so a citation is
    a URL and a URL is a citation. One handler serves it, because the identifier
    decides what the thing *is* — `/us/usc/t16/ch1` is a TOC node,
    `/us/usc/t16/s45f/c/5` is a provision inside a section — and a caller shouldn't
    have to know which before asking.
  * **`/api/v1/{sections,releases,titles}/…`** for everything that is about a
    provision rather than being one: neighbours, version timeline, release points.

No SQL and no version-resolution logic lives here (CLAUDE.md architecture rule 1);
handlers resolve a release point, ask the `Repository`, and shape the answer.

Machine formats only (ADR-0010): JSON by default, verbatim USLM for `?format=xml`
or an XML `Accept:`. A browser's `Accept: text/html` gets JSON here rather than a
template — the surface that answers people is `/app`, and the bare citation URL
`/us/usc/…` is the redirector that sends each caller to the right one.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from api.diff import cached_diff_ops, diff_ops, strip_guids
from api.schemas import (
    CitationOut,
    CorpusStatusOut,
    DiffOpOut,
    DiffOut,
    DiffSectionOut,
    ErrorOut,
    GuidOut,
    NeighborsOut,
    ReleaseOut,
    SectionOut,
    SourceCheckOut,
    StatusOut,
    TitleOut,
    TocEntryOut,
    TocOut,
    VersionOut,
    VersionsOut,
)
from citeparse import ParsedCitation, parse_citation
from params import (
    IMMUTABLE,
    MACHINE_FORMATS,
    DateParam,
    FormatParam,
    ReleaseParam,
    RepositoryDep,
    cache_control,
    if_none_match,
    negotiated_format,
    normalize_identifier,
    not_found,
    parse_date_param,
    public_cache,
    rate_limit,
    resolve_release_or_404,
    served_note,
)
from storage import (
    SOURCE_URL,
    Repository,
    ResolvedRelease,
    SectionResult,
    TocEntry,
    title_num_from_identifier,
)

api = APIRouter(
    prefix="/api/v1",
    tags=["api"],
    # Every route on this surface is public and cacheable; the section handler
    # overrides this with `immutable` when the release point was pinned.
    dependencies=[Depends(public_cache)],
)

# Rate limits (ADR-0029). Sized by what a route costs and by who calls it — the
# reasoning is in `params.py`'s rate-limiting section, and the short version is
# that anything the reader's server-side render calls arrives from one address
# for the whole readership, so it is sized for a server.

_limit_citation = rate_limit("citation", capacity=120, per_second=10.0)
"""Called by `/app/goto` on the server, so it is a server's budget. The parse
itself is pure and cheap (`citeparse`); the `labels()` existence check behind it
is not free."""

_limit_labels = rate_limit("labels", capacity=300, per_second=30.0)
"""One call per section page rendered, server-side, for the whole readership —
so this is the most generous of the three. What it bounds is the fan-out: the
`identifier` list is now capped at 100, and this caps how often a caller may
send a full one."""

_limit_diff = rate_limit("diff", capacity=5, per_second=0.2)
"""The tight one, and the reason this work exists. `api/diff.py` sets
`Diff_Timeout = 0`, deliberately removing diff-match-patch's only runtime bound,
and `docs/verification/loadtest.json` measured ~0.45 rps failing entirely past
~10 concurrent. Nothing calls this server-side any more — ADR-0026 moved the
reader onto its own text redline — so this budget is a person's, and 12/minute
after a burst of 5 is more than a person reading redlines will ever want."""


@api.get("/releases", response_model=list[ReleaseOut], summary="All release points")
def list_releases(
    repository: RepositoryDep,
    title: str | None = Query(
        default=None, description="Only release points that changed this title."
    ),
    ingested_title: str | None = Query(
        default=None,
        description="Only release points this database actually holds this title "
        "at — what a release picker can offer without offering empty answers.",
    ),
) -> list[ReleaseOut]:
    """Every known release point, newest first.

    `titles_affected` is what OLRC says the release point changed;
    `ingested_titles` is what this database actually holds for it. The two differ
    for as long as the backfill is incomplete, and conflating them would make an
    empty answer look like a missing law — which is why they are two parameters
    and not one.
    """
    releases = repository.list_releases(title_num=title)
    if ingested_title is not None:
        releases = [r for r in releases if ingested_title in r.ingested_titles]
    return [ReleaseOut.of(r) for r in releases]


@api.get(
    "/status",
    response_model=StatusOut,
    summary="How current this mirror is, and when it last checked",
)
def status(repository: RepositoryDep) -> StatusOut:
    """What this deployment holds, and when it last asked OLRC what exists.

    A versioned mirror of a living source has two ways of being wrong and only
    one of them is visible from the text: it can be missing a release point
    that was published last week, or it can have stopped asking altogether. The
    second is the dangerous one, because a corpus that has quietly stopped
    updating is indistinguishable from a corpus with nothing to update — every
    page still renders, every date still looks authoritative. So the answer
    here is two facts side by side: the newest release point loaded, and the
    timestamp of the last poll of uscode.house.gov.

    Polled daily; `stale` goes true after a week without a successful check
    (`storage.SOURCE_CHECK_STALE_AFTER`).
    """
    check = repository.last_source_check()
    releases = repository.list_releases()
    loaded = next((r for r in releases if r.ingested_titles), None)

    behind_by = None
    if check is not None and check.ok and check.latest_label is not None:
        # Count by `seq`, the inventory's own global ordering — release-point
        # labels do not sort (gotcha 4), and comparing dates would tie.
        by_label = {r.label: r for r in releases}
        published = by_label.get(check.latest_label)
        if published is not None and loaded is not None:
            behind_by = sum(
                1 for r in releases if loaded.seq < r.seq <= published.seq
            )

    return StatusOut(
        source=SourceCheckOut.of(check, url=SOURCE_URL),
        corpus=CorpusStatusOut(
            latest_release=loaded.label if loaded else None,
            latest_currency_date=loaded.currency_date if loaded else None,
            release_points_known=len(releases),
            behind_by=behind_by,
        ),
    )


@api.get("/titles", response_model=list[TitleOut], summary="Ingested titles")
def list_titles(repository: RepositoryDep) -> list[TitleOut]:
    """Every ingested title, in the Code's own order — `1, 2, … 5, 5a, 6, … 11,
    11a, 12, …` (ADR-0025). The ordering is the Repository's contract, not this
    handler's, so the same list arrives sorted from any implementation."""
    return [TitleOut.of(t) for t in repository.list_titles()]


@api.get(
    "/citation",
    response_model=CitationOut,
    responses={422: {"model": ErrorOut}, 429: {"model": ErrorOut}},
    summary="A typed citation, resolved to an identifier",
    dependencies=[Depends(_limit_citation)],
)
def citation_lookup(
    repository: RepositoryDep,
    q: Annotated[
        str,
        Query(
            description="A citation in more or less any written form.",
            examples=["11 usc 523(a)(1)", "16 U.S.C. § 45f(c)(5)", "5 USC App. 3"],
        ),
    ],
    release: ReleaseParam = None,
    date: DateParam = None,
) -> CitationOut:
    """`11 usc 523(a)(1)` → `/us/usc/t11/s523/a/1`, and whether it is there.

    Parsing is `citeparse.parse_citation`, which is pure — it knows what string
    a citation names and nothing about what exists. Existence is answered here,
    with the batched `labels()` lookup already built for citation hover text, so
    this costs one query and needs no new `Repository` method (architecture
    rule 1).

    A string that cannot be parsed is a 422: the request was malformed. A string
    that parses but names nothing loaded is a **200 with `exists: false`** — it
    is a well-formed question with the answer "not here", and telling the reader
    which part was wrong beats an error page.
    """
    parsed = parse_citation(q)
    if parsed is None:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{q!r} is not a citation this site can read. Try "
                "'11 usc 523', '11 U.S.C. § 523(a)(1)', 'section 523 of title 11', "
                "'11/523', or '/us/usc/t11/s523'."
            ),
        )

    resolved = resolve_release_or_404(
        repository,
        release=release,
        on_date=parse_date_param(date),
        title_num=parsed.title_num,
    )
    entry, actual = _locate(repository, parsed, resolved)
    return CitationOut.of(
        parsed,
        q,
        entry=entry,
        actual=actual,
        release=resolved.release,
        message=None if entry else _why_not(parsed),
    )


def _locate(
    repository: Repository, parsed: ParsedCitation, resolved: ResolvedRelease
) -> tuple[TocEntry | None, str | None]:
    """Find what the citation named, and under which spelling.

    Two wrinkles, both discovered by typing citations at it rather than by
    reading the schema:

    **Dashes.** OLRC writes section numbers with an EN DASH — `/us/usc/t16/s45a–1`
    — and 5,697 of 65,938 loaded sections contain one while *none* contains a
    plain hyphen. A reader typing `42 USC 2000e-2` on an ordinary keyboard would
    otherwise match nothing. `parsed.section_variants` supplies the spellings and
    they all go into the one batched `labels()` call, so trying three costs what
    trying one did.

    **Structure and titles are not sections.** `labels()` answers about sections,
    so `11 USC ch. 5` and `title 11` came back `exists: false` while sitting in
    the database. Those go to `get_toc`, which is what they are.
    """
    if parsed.kind == "section":
        found = repository.labels(list(parsed.section_variants), resolved)
        for candidate in parsed.section_variants:
            if candidate in found:
                return found[candidate], candidate
        return None, None

    for candidate in parsed.section_variants:
        toc = repository.get_toc(candidate, resolved)
        if toc is not None:
            return toc.node, candidate
    return None, None


#: `/us/usc/t5a/s3` — an appendix title followed straight by a flat section
#: number. OLRC publishes no such identifier: 0 of the corpus's 461 appendix
#: sections use this form (see `citeparse`'s class docstring). The real ones put
#: the enacting law or act between the two, which is why matching on `/s` here
#: cannot catch a reachable identifier.
_FLAT_APPENDIX = re.compile(r"^/us/usc/t(\d+)a/s")


def _appendix_hint(identifier: str) -> str | None:
    """Why a flat appendix section resolves to nothing, or None.

    Written against the identifier rather than against a `ParsedCitation`, so
    the citation endpoint and the identifier lookup give the same answer to the
    same question — a reader who types `5 USC App. 3` into the box and a reader
    who lands on `/us/usc/t5a/s3` have made one mistake, not two.
    """
    match = _FLAT_APPENDIX.match(identifier)
    if match is None:
        return None
    return (
        f"Title {match.group(1)} Appendix is published under the law that enacted "
        "each provision, not under a flat section number. Its identifiers look "
        "like /us/usc/t5a/pl/92/463/s1 (by public law) or "
        "/us/usc/t50a/act/1917-05-18/ch15/s212 (by act and date). This site "
        f"cannot yet translate {identifier} into one of those."
    )


def _why_not(parsed: ParsedCitation) -> str | None:
    """Something specific to say when a well-formed citation resolves to nothing.

    Only the case this site can actually diagnose. Everything else gets no
    message, because "not found" with a confident-sounding invented reason is
    worse than "not found".
    """
    if parsed.appendix and parsed.kind != "title":
        return _appendix_hint(parsed.identifier)
    return None


@api.get(
    "/sections/{identifier:path}/neighbors",
    response_model=NeighborsOut,
    summary="Previous and next section in reading order",
)
def neighbors(
    identifier: str,
    repository: RepositoryDep,
    release: ReleaseParam = None,
    date: DateParam = None,
) -> NeighborsOut:
    """Reading order at one release point, skipping nothing: repealed, omitted and
    transferred sections keep their place and arrive badged (gotcha 9)."""
    path = normalize_identifier(identifier)
    resolved = _resolve_for(repository, path, release, date)
    result = repository.neighbors(path, resolved)
    if result is None:
        raise HTTPException(status_code=404, detail=not_found(path, resolved))
    return NeighborsOut.of(result)


@api.get(
    "/labels",
    response_model=dict[str, TocEntryOut],
    responses={429: {"model": ErrorOut}},
    summary="Num and heading for many identifiers at once",
    dependencies=[Depends(_limit_labels)],
)
def labels(
    repository: RepositoryDep,
    identifier: Annotated[
        list[str],
        Query(
            description="Repeat once per identifier, up to 100 per request; more "
            "than that is a 422. Unknown identifiers are absent from the answer "
            "rather than an error.",
            examples=[["/us/usc/t16/s45f", "/us/usc/t16/s1"]],
            # The list fans into one `IN (...)`, so an unbounded one is an
            # unbounded query (ADR-0029).
            #
            # "The densest section carries a few dozen cross references" is what
            # this comment used to say, and it was an estimate. Measured over
            # all 489,738 stored versions: the densest carries 1,011, and 4,221
            # of them carry more than 100. 3 U.S.C. § 301 has 242 distinct ones,
            # and every reader request for it was a 422 here and a 500 upstairs.
            #
            # The bound stays — it is the protection, and a caller that needs
            # more asks more than once (`LABELS_PER_REQUEST` in
            # `frontend/src/lib/api.ts`, which batches to exactly this size).
            max_length=100,
        ),
    ],
    release: ReleaseParam = None,
    date: DateParam = None,
) -> dict[str, TocEntryOut]:
    """What a list of citations *say*, in one request.

    A section's text can carry forty cross references, and a reader that labels
    them — hover text, so a citation is legible without following it — has to ask
    once, not forty times. **At most 100 identifiers per request**; a caller with
    more asks more than once.
    """
    paths = [normalize_identifier(one) for one in identifier]
    resolved = resolve_release_or_404(
        repository,
        release=release,
        on_date=parse_date_param(date),
        title_num=next(
            (
                num
                for num in map(title_num_from_identifier, paths)
                if num is not None
            ),
            None,
        ),
    )
    return {
        found: TocEntryOut.of(entry)
        for found, entry in repository.labels(paths, resolved).items()
    }


@api.get(
    "/sections/{identifier:path}/versions",
    response_model=VersionsOut,
    summary="Release points at which a section changed",
)
def versions(identifier: str, repository: RepositoryDep) -> VersionsOut:
    """The section's change timeline — one entry per distinct text, not one per
    release point, since most release points leave most sections untouched."""
    path = normalize_identifier(identifier)
    found = repository.versions(path)
    if not found:
        raise HTTPException(status_code=404, detail=f"no section at {path}")
    return VersionsOut(
        identifier=path, versions=[VersionOut.of(version) for version in found]
    )


@api.get(
    "/sections/{identifier:path}/diff",
    response_model=DiffOut,
    summary="A redline between two release points of a section",
    responses={404: {"model": ErrorOut}, 429: {"model": ErrorOut}},
    dependencies=[Depends(_limit_diff)],
)
def diff(
    identifier: str,
    response: Response,
    repository: RepositoryDep,
    from_: str = Query(
        alias="from", description="Release point label to diff from.", examples=["119-99"]
    ),
    to: str = Query(description="Release point label to diff to.", examples=["119-102not101"]),
    guids: Literal["strip", "keep"] = Query(
        default="strip",
        description=(
            "Whether `@id` guids take part in the diff. They regenerate at every "
            "release point by design (ADR-0003), so `strip` — the default — "
            "compares what the section says. `keep` diffs the bytes as stored."
        ),
    ),
) -> DiffOut:
    """Diffs the two release points' XML (docs/adr/0016): a generic text diff,
    computed here because it needs no USLM vocabulary at all — presentation
    (wrapping `ops` in `<ins>`/`<del>`) is `frontend/src/lib`'s job, same as the
    section renderer itself.

    `@id` guids are dropped before the comparison unless `guids=keep`. They are
    regenerated at every release point whether or not the law changed (gotcha
    1), so about half of what this endpoint used to report was identifier churn
    — 31 of § 45f's 51 ops — and computing it was about half the cost."""
    path = normalize_identifier(identifier)
    title_num = title_num_from_identifier(path)
    from_resolved = resolve_release_or_404(
        repository, release=from_, on_date=None, title_num=title_num
    )
    to_resolved = resolve_release_or_404(
        repository, release=to, on_date=None, title_num=title_num
    )

    from_section = repository.get_section(path, from_resolved)
    if from_section is None:
        raise HTTPException(status_code=404, detail=not_found(path, from_resolved))
    to_section = repository.get_section(path, to_resolved)
    if to_section is None:
        raise HTTPException(status_code=404, detail=not_found(path, to_resolved))

    pinned = from_resolved.is_exact and to_resolved.is_exact
    if pinned:
        # Both endpoints pinned: the redline between two published release points
        # is as fixed as the two texts it is drawn from.
        response.headers["Cache-Control"] = IMMUTABLE

    strip = guids == "strip"
    from_xml = strip_guids(from_section.xml) if strip else from_section.xml
    to_xml = strip_guids(to_section.xml) if strip else to_section.xml

    # Memoised on the *resolved* labels, and only when both were pinned: an
    # unpinned label names a different release point the moment a newer one is
    # loaded, so caching under it would serve a redline for a pair the URL no
    # longer means.
    if pinned:
        ops = cached_diff_ops(
            (path, from_resolved.release.label, to_resolved.release.label, strip),
            from_xml,
            to_xml,
        )
    else:
        ops = diff_ops(from_xml, to_xml)

    return DiffOut(
        identifier=path,
        from_=DiffSectionOut.of(from_section),
        to=DiffSectionOut.of(to_section),
        guids=guids,
        ops=[DiffOpOut.of(op) for op in ops],
    )


@api.get(
    "/us/usc/",
    response_model=GuidOut,
    tags=["us code"],
    summary="Look a provision up by its XML @id",
    responses={404: {"model": ErrorOut}},
)
def lookup_by_guid(
    repository: RepositoryDep,
    id: str = Query(
        description="An `@id` guid from the USLM, e.g. "
        "`id0b32dff7-810c-11f1-b7ce-bdea3d14cbdd`.",
        examples=["id0b32dff7-810c-11f1-b7ce-bdea3d14cbdd"],
    ),
) -> GuidOut:
    """No release parameter, by design: a guid identifies (provision, release point)
    on its own, which makes it the stable citation for *this exact text at this
    exact moment* (ADR-0003)."""
    resolution = repository.resolve_id(id)
    if resolution is None:
        raise HTTPException(status_code=404, detail=f"no provision with @id {id!r}")
    return GuidOut.of(resolution)


@api.get(
    "/us/usc/{identifier:path}",
    tags=["us code"],
    summary="A provision, section, or table-of-contents node by identifier",
    response_model=None,
    responses={
        200: {
            "content": {
                "application/json": {},
                "application/xml": {},
            }
        },
        404: {"model": ErrorOut},
        409: {"model": ErrorOut},
    },
)
def get_by_identifier(
    identifier: str,
    request: Request,
    repository: RepositoryDep,
    release: ReleaseParam = None,
    date: DateParam = None,
    format: FormatParam = None,
) -> Response | SectionOut | TocOut:
    """Resolve a US Code identifier at a release point.

    Longest-prefix match means `/us/usc/t16/s45f/c/5` returns section 45f *with*
    paragraph (c)(5) extracted and anchored, rather than the paragraph alone —
    sub-section provisions are cut from the section at request time (ADR-0001), so
    the reader never loses context.

    If the identifier names no section, it is tried as a structural node, and a
    table of contents comes back instead.
    """
    path = normalize_identifier(f"us/usc/{identifier}")
    resolved = _resolve_for(repository, path, release, date)
    wanted = negotiated_format(request, format, allowed=MACHINE_FORMATS)

    section = repository.get_section(path, resolved)
    if section is not None:
        return _section_response(request, section, resolved, wanted)

    toc = repository.get_toc(path, resolved)
    if toc is not None:
        return TocOut.of(toc, note=resolved.note)

    # The one 404 this site can diagnose. Reaching the reader matters as much as
    # reaching an API client: a bare "nothing here" reads as "this provision was
    # never enacted", and the truth is that it exists under a different scheme.
    hint = _appendix_hint(path)
    detail = not_found(path, resolved)
    raise HTTPException(status_code=404, detail=f"{detail} — {hint}" if hint else detail)


def _section_response(
    request: Request,
    section: SectionResult,
    resolved: ResolvedRelease,
    wanted: str,
) -> Response | SectionOut:
    note = served_note(section, resolved)
    etag = f'"{section.content_hash}"'
    headers = {
        # Content is immutable per (section text, release point): the same section
        # at the same release point can never change, so the hash of its content is
        # a true ETag (PLAN Day 6's cache-forever plan starts here).
        "ETag": etag,
        # JSON and XML still share this URL, so the ETag alone would let a cache
        # hand one caller the representation another asked for first.
        "Vary": "Accept",
        # …but only a *pinned* release point may be cached forever: an unpinned
        # request is answered from the newest ingested release point at or before
        # it, and that changes under the URL. See params.cache_control.
        "Cache-Control": cache_control(resolved),
        "X-Release-Point": section.release.label,
        "X-Served-From": section.served_from.label,
    }
    if section.release.caveat:
        headers["X-Release-Caveat"] = section.release.caveat

    if if_none_match(request, etag):
        # The caller already holds this text. 304 carries the validators and the
        # freshness, never a body (RFC 9110 §15.4.5).
        return Response(status_code=304, headers=headers)

    if wanted == "xml":
        # Exactly what the identifier names: the provision if one was asked for,
        # otherwise the whole section, verbatim USLM either way.
        fragment = (
            section.provision.xml
            if section.provision and section.provision.found and section.provision.xml
            else section.xml
        )
        return Response(
            content=fragment, media_type="application/xml; charset=utf-8", headers=headers
        )

    out = SectionOut.of(section, note=note)
    return Response(
        content=out.model_dump_json(),
        media_type="application/json",
        headers=headers,
    )


def _resolve_for(
    repository: Repository, path: str, release: str | None, date: str | None
) -> ResolvedRelease:
    return resolve_release_or_404(
        repository,
        release=release,
        on_date=parse_date_param(date),
        title_num=title_num_from_identifier(path),
    )
