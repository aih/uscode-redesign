"""OLRC's Classification Tables on the machine surface (spec §4, ADR-0067).

The tables record which provision of which public law was classified to which
Code section — `118-35 §101(3) → 18 USC 3551 note`. They are a mirror of a set
of published documents rather than a view of the corpus, so nothing here
resolves a release point and nothing here touches `Repository`, except the one
place the lookup asks whether a section a reader typed actually exists.

Three things about the data decide the shape of these routes, and each of them
was measured rather than assumed:

  * **Two spellings of a section number.** `section_norm` holds the table's own
    hyphen and is what typed input matches; `usc_identifier` holds the corpus's
    EN DASH (gotcha 17). A route taking typed input normalizes; a route taking an
    `@identifier` tries both.
  * **Covered but empty is not the same as uncovered.** `covered_ranges` is
    gap-aware, so "no table covers Public Law 119-150" is a 404 and "a table
    covers 119-2 and it classified nothing" is a 200 with no rows.
  * **Nullable columns that are not failures.** 1,533 rows derive no
    `usc_identifier`, 2 rows could not read their Pub. L. cell, and 6,053 cite a
    Statutes at Large page with no integer form. All of them are returned, and
    `stat_page_labels` is the column to print.

Cache policy is `REVALIDATE` everywhere (`public_cache` on the router): nothing
here is pinned to a release point, and an old table can be editorially corrected
— which is exactly what the ECCT documents.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from api.schemas import (
    ClassificationCheckOut,
    ClassificationFileOut,
    ClassificationPageOut,
    ClassificationSuggestionOut,
    ClassificationSuggestOut,
    ClassificationTablesOut,
    EcctEntryOut,
    EcctOut,
    ErrorOut,
)
from citeparse import parse_citation
from params import (
    RepositoryDep,
    normalize_identifier,
    public_cache,
    rate_limit,
    resolve_release_or_404,
)
from storage import (
    CLASSIFICATION_SOURCE_URL,
    ClassificationRepository,
    Repository,
    UnknownPublicLawError,
    get_classification,
    normalize_section_input,
)

router = APIRouter(
    prefix="/api/v1",
    tags=["classification"],
    dependencies=[Depends(public_cache)],
)

ClassificationDep = Annotated[ClassificationRepository, Depends(get_classification)]

MAX_LIMIT = 500
"""The page bound on every listing route. The largest document is the 104th's
11,737 rows and the largest section history is a few dozen, so this is well past
what a page shows and well short of what a table dump would cost."""

IDENTIFIER_LIMIT = 200
"""The by-identifier route returns one section's whole classification history in
one answer, so it takes no `offset` — it takes a ceiling instead. Measured over
the loaded corpus, the busiest identifier carries far fewer rows than this; a
section that ever exceeded it would be truncated rather than paged, which is
recorded here rather than discovered."""

_limit_classification = rate_limit("classification", capacity=120, per_second=10.0)
"""ADR-0029, sized for a server rather than for a person. `/app/classification`
and its session pages render on the frontend server and call these routes over
HTTP, so the whole readership's table browsing arrives from one address — the
same reasoning that sizes `/api/v1/search` and `/api/v1/labels`. What it bounds
is a caller hitting `/api/v1` directly: each answer is one indexed query and a
count, bounded at 500 rows, so 120 in a burst and 10 a second is generous for a
program and still refuses a scrape of 144,837 rows at full speed."""

_limit_classification_suggest = rate_limit(
    "classification_suggest", capacity=30, per_second=5.0
)
"""ADR-0029, sized for a person. The lookup box's autocomplete is called from
the *browser* as someone types, so this budget is one human's: 30 in a burst
covers a typed citation with a keystroke each, and 5 a second sustains faster
typing than the debounce sends. It is the tighter of the two because it costs
more than the others — the citation half resolves a release point and asks
`Repository.labels` whether the section exists."""


# ---------------------------------------------------------------- input parsing

#: `?pl=` on the session-page route: `118-33`, or a bare `33` meaning that
#: number within the congress the path already named.
_PL_FILTER = re.compile(r"^(?:(?P<congress>\d{2,3})-)?(?P<num>\d{1,4})$")

#: The lookup's public-law shorthand: `118-33`, `118-33 101`, `pl 118-33`,
#: `Pub. L. 118-33 § 101(3)`.
_PL_SHORTHAND = re.compile(
    r"^(?:(?:pub(?:lic)?\.?|p\.?)\s*l(?:aw)?\.?\s*)?"
    r"(?P<congress>\d{2,3})-(?P<num>\d{1,4})"
    r"(?:[\s,]+(?:sec(?:tion)?\.?\s*|§\s*)?(?P<section>\S.*?))?$",
    re.IGNORECASE,
)

READER_NOTES_ANCHOR = "#section-notes"
"""The anchor ADR-0055 gives a section's notes. OLRC prints a provision's
classification history there, which is why the lookup's first suggestion for a
citation leads to it rather than to the top of the section."""


def _session_number(value: str) -> int:
    """`1` | `2` | `all` → the integer the database holds. `all` is 0.

    Both spellings are accepted on the way in: `0` is what the registry stores
    for the 104th's single whole-congress file, and `all` is what spec §5's URL
    vocabulary writes it as. One of them had to be the canonical answer and the
    friendlier contract is to take either.
    """
    text = value.strip().lower()
    if text == "all":
        return 0
    try:
        return int(text)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"session must be 1, 2 or all (0 for a whole-congress table), not {value!r}",
        ) from None


def _pl_filter(value: str, *, congress: int) -> tuple[int, int]:
    match = _PL_FILTER.match(value.strip())
    if match is None:
        raise HTTPException(
            status_code=422,
            detail=f"pl must be a public law number like 118-33 or 33, not {value!r}",
        )
    return (
        int(match.group("congress")) if match.group("congress") else congress,
        int(match.group("num")),
    )


def _ordinal(number: int) -> str:
    """`119` → `119th`, `121` → `121st`. Every congress this mirror holds is a
    `th`, and the next few are not."""
    if number % 100 in (11, 12, 13):
        return f"{number}th"
    return f"{number}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(number % 10, 'th') }"


def _app_path(path: str, params: dict[str, str] | None = None) -> str:
    """A reader path relative to `/app`, percent-encoded and ready to use.

    `/app` is spelled once in `frontend/src/lib/url.ts` (architecture rule 5),
    so nothing here writes it. What these routes return is the part after it.
    """
    query = urlencode({key: value for key, value in (params or {}).items() if value})
    return f"{path}?{query}" if query else path


# ------------------------------------------------------------------- 1. registry


@router.get(
    "/classifications/tables",
    response_model=ClassificationTablesOut,
    responses={429: {"model": ErrorOut}},
    summary="The classification tables held, and how fresh they are",
    dependencies=[Depends(_limit_classification)],
)
def classification_tables(classification: ClassificationDep) -> ClassificationTablesOut:
    """Every source document this mirror holds, newest first, with the timestamp
    of the last poll of OLRC's index page.

    The freshness half is this workstream's own check and not the one
    `/api/v1/status` reports. That one polls the release-point inventory; these
    are two unrelated sources published on different schedules, and one answer
    covering both would flap between them.
    """
    files = classification.list_files()
    pl_files = [f for f in files if f.kind == "pl"]
    return ClassificationTablesOut(
        source=ClassificationCheckOut.of(
            classification.last_classification_check(), url=CLASSIFICATION_SOURCE_URL
        ),
        files=[ClassificationFileOut.of(f) for f in files],
        current=ClassificationFileOut.of(pl_files[0]) if pl_files else None,
        entry_total=sum(f.row_count for f in pl_files),
    )


# --------------------------------------------------------------- 2. session page


@router.get(
    "/classifications/tables/{congress}/{session}/entries",
    response_model=ClassificationPageOut,
    responses={404: {"model": ErrorOut}, 422: {"model": ErrorOut}, 429: {"model": ErrorOut}},
    summary="One session's classification table, filtered and paged",
    dependencies=[Depends(_limit_classification)],
)
def classification_entries(
    classification: ClassificationDep,
    congress: Annotated[int, Path(description="Congress number.", examples=[119])],
    session: Annotated[
        str,
        Path(
            description="`1`, `2`, or `all` for a whole-congress table (the 104th). "
            "`0` is accepted as well and is what the database holds for `all`.",
            examples=["2"],
        ),
    ],
    sort: Literal["pl", "code"] = Query(
        default="pl",
        description="`pl` is the source's own order. `code` is the Code's order — "
        "title first (`5, 5a, 6, … 10`, never as text), then section number.",
    ),
    pl: str | None = Query(
        default=None,
        description="Only rows classifying this public law. `118-33`, or a bare "
        "`33` meaning that law of the congress in the path.",
        examples=["118-33"],
    ),
    pl_section: str | None = Query(
        default=None,
        description="Only rows whose Sec. cell starts with this — a prefix, so "
        "`101` matches `101(3)` and `101(a)`.",
        examples=["101"],
    ),
    title: str | None = Query(
        default=None, description="Only rows classified to this US Code title.", examples=["42"]
    ),
    section: str | None = Query(
        default=None,
        description="Only rows classified to this section. Normalized on the way "
        "in — an en dash and a hyphen both match.",
        examples=["254c-15"],
    ),
    limit: int = Query(default=100, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> ClassificationPageOut:
    """One `tbl{congress}pl_{session}.htm` as rows.

    404 when no such document is held — the congress is out of range, or its
    table has not been loaded. An empty `items` with a 200 means the document is
    here and the filters matched nothing in it.
    """
    session_num = _session_number(session)
    file = classification.get_file(congress=congress, session=session_num)
    if file is None:
        raise HTTPException(
            status_code=404,
            detail=f"no classification table for congress {congress}, session {session}",
        )

    pl_congress = pl_num = None
    if pl:
        pl_congress, pl_num = _pl_filter(pl, congress=congress)

    page = classification.entries_for_file(
        congress=congress,
        session=session_num,
        sort=sort,
        pl_congress=pl_congress,
        pl_num=pl_num,
        pl_section=pl_section,
        title_num=title,
        section=section,
        limit=limit,
        offset=offset,
    )
    return ClassificationPageOut.of(page, sort=sort, file=file)


# ----------------------------------------------------------------- 3. public law


@router.get(
    "/classifications/pl/{congress}/{law_num}",
    response_model=ClassificationPageOut,
    responses={404: {"model": ErrorOut}, 429: {"model": ErrorOut}},
    summary="Everything one public law classified",
    dependencies=[Depends(_limit_classification)],
)
def classifications_for_law(
    classification: ClassificationDep,
    congress: Annotated[int, Path(examples=[118])],
    law_num: Annotated[int, Path(examples=[35])],
    section: str | None = Query(
        default=None,
        description="Only provisions of the law whose Sec. cell starts with this.",
        examples=["101"],
    ),
    limit: int = Query(default=100, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> ClassificationPageOut:
    """The law's rows in source order, with the document that covers it.

    **404 and an empty page mean different things here.** A 404 says no
    classification table covers this public law — the table for its session has
    not been published or not been loaded. A 200 with no rows says a table does
    cover it and it classified nothing to the Code, which is an ordinary thing
    for a law to do.
    """
    try:
        page = classification.entries_for_law(
            congress=congress,
            law_num=law_num,
            section=section,
            limit=limit,
            offset=offset,
        )
    except UnknownPublicLawError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    file = classification.file_covering_law(congress=congress, law_num=law_num)
    return ClassificationPageOut.of(page, file=file)


# --------------------------------------------------------------- 4. code section


@router.get(
    "/classifications/code/{title_num}/{section}",
    response_model=ClassificationPageOut,
    responses={429: {"model": ErrorOut}},
    summary="Everything ever classified to one Code section",
    dependencies=[Depends(_limit_classification)],
)
def classifications_for_section(
    classification: ClassificationDep,
    title_num: Annotated[str, Path(description="A title number — a string, `5a` included.", examples=["18"])],
    section: Annotated[
        str,
        Path(
            description="A section number as typed. Lowercased and dash-folded on "
            "the way in, so `254C–15` and `254c-15` are the same request.",
            examples=["3551"],
        ),
    ],
    congress: int | None = Query(
        default=None, description="Only rows from laws of this congress."
    ),
    exact: bool = Query(
        default=True,
        description="False matches any section number starting with what was "
        "given — `45` then also reaches `45a` and `45f`.",
    ),
    limit: int = Query(default=100, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> ClassificationPageOut:
    """Newest public law first, which is the order a section's classification
    history reads in. A section nothing was ever classified to is an empty page,
    not a 404: the tables cover 1996 onward, so silence here is ordinary."""
    page = classification.entries_for_section(
        title_num=title_num,
        section=section,
        congress=congress,
        exact=exact,
        limit=limit,
        offset=offset,
    )
    return ClassificationPageOut.of(page)


# ---------------------------------------------------------------- 5. identifier


@router.get(
    "/classifications/us/usc/{identifier:path}",
    response_model=ClassificationPageOut,
    responses={429: {"model": ErrorOut}},
    summary="Classification rows for a USLM identifier",
    dependencies=[Depends(_limit_classification)],
)
def classifications_for_identifier(
    identifier: str,
    classification: ClassificationDep,
) -> ClassificationPageOut:
    """The rows whose derived `usc_identifier` is this path, newest law first.

    Both dash spellings are tried: the stored value uses OLRC's EN DASH and a
    caller's path may carry a plain hyphen (gotcha 17). Bounded at 200 rows and
    unpaged — this is one section's history, and the answer is meant to be
    whole.
    """
    path = normalize_identifier(f"us/usc/{identifier}")
    page = classification.entries_for_identifier(path, limit=IDENTIFIER_LIMIT)
    return ClassificationPageOut.of(page)


# ------------------------------------------------------------------- 6. suggest


@router.get(
    "/classifications/suggest",
    response_model=ClassificationSuggestOut,
    responses={429: {"model": ErrorOut}},
    summary="What the classification lookup box can offer for what was typed",
    dependencies=[Depends(_limit_classification_suggest)],
)
def classification_suggest(
    classification: ClassificationDep,
    repository: RepositoryDep,
    q: Annotated[
        str,
        Query(
            description="A public law in shorthand, or a US Code citation.",
            examples=["118-33 101", "16 USC 45f"],
            max_length=200,
        ),
    ],
) -> ClassificationSuggestOut:
    """Two families of answer, decided by what the string parses as.

    A **public law** — `118-33`, `118-33 101`, `pl 118-33` — leads to the session
    table covering it, filtered to that law. Filtering rather than scrolling,
    because the table is paged and a scroll anchor cannot reach a row on another
    page; the filtered view is also citable by its URL alone.

    A **US Code citation** goes through `citeparse`, the same parser
    `/api/v1/citation` uses — there is one citation parser in this project and it
    is in Python. When the section exists in the corpus, the first suggestion
    leads to its notes, where OLRC prints the provision's own classification
    history. When classification rows mention it, the second leads to those.
    Either may appear without the other.

    An empty `suggestions` is the answer for a string that is neither, and for a
    law or a section nothing is held about.
    """
    query = q.strip()
    suggestions: list[ClassificationSuggestionOut] = []
    if query:
        suggestions.extend(_pl_suggestions(classification, query))
        suggestions.extend(_citation_suggestions(classification, repository, query))
    return ClassificationSuggestOut(query=q, suggestions=suggestions)


def _pl_suggestions(
    classification: ClassificationRepository, query: str
) -> list[ClassificationSuggestionOut]:
    match = _PL_SHORTHAND.match(query)
    if match is None:
        return []
    congress = int(match.group("congress"))
    law_num = int(match.group("num"))
    file = classification.file_covering_law(congress=congress, law_num=law_num)
    if file is None:
        return []

    pl = f"{congress}-{law_num}"
    pl_section = (match.group("section") or "").strip() or None
    label = f"Public Law {pl}"
    if pl_section:
        label = f"{label} § {pl_section}"
    session_words = {0: "whole congress", 1: "1st session", 2: "2nd session"}
    return [
        ClassificationSuggestionOut(
            kind="pl",
            label=label,
            detail=(
                f"{_ordinal(congress)} Congress, "
                f"{session_words.get(file.session, str(file.session))} table"
            ),
            href=_app_path(
                f"/classification/{congress}/{file.session_label}",
                {"pl": pl, "pl_section": pl_section or ""},
            ),
            congress=congress,
            session=file.session,
            session_label=file.session_label,
            pl=pl,
            pl_section=pl_section,
        )
    ]


def _citation_suggestions(
    classification: ClassificationRepository,
    repository: Repository,
    query: str,
) -> list[ClassificationSuggestionOut]:
    parsed = parse_citation(query)
    if parsed is None or parsed.kind != "section" or parsed.section_num is None:
        return []

    suggestions: list[ClassificationSuggestionOut] = []
    entry, identifier = _resolve_section(repository, parsed.section_variants)
    if entry is not None and identifier is not None:
        suggestions.append(
            ClassificationSuggestionOut(
                kind="section-notes",
                label=f"{parsed.title_num} U.S.C. § {parsed.section_num} — notes, in the reader",
                detail=entry.heading,
                href=quote(identifier) + READER_NOTES_ANCHOR,
                title_num=parsed.title_num,
                section=normalize_section_input(parsed.section_num),
                identifier=identifier,
                fragment=READER_NOTES_ANCHOR,
            )
        )

    section = normalize_section_input(parsed.section_num)
    page = classification.entries_for_section(
        title_num=parsed.title_num, section=section, limit=1
    )
    if page.total:
        suggestions.append(
            ClassificationSuggestionOut(
                kind="section-classifications",
                label=f"Classification entries for {parsed.title_num} U.S.C. § {parsed.section_num}",
                detail=f"{page.total} row{'' if page.total == 1 else 's'}",
                href=_app_path(
                    "/classification", {"title": parsed.title_num, "section": section}
                ),
                title_num=parsed.title_num,
                section=section,
                count=page.total,
            )
        )
    return suggestions


def _resolve_section(repository: Repository, variants: tuple[str, ...]):
    """Does the corpus hold this section, and under which spelling?

    The same batched `labels()` lookup `/api/v1/citation` uses, so a citation
    that resolves in the box resolves here too. A deployment with no release
    points loaded answers "no" rather than raising: this route's job is to
    suggest, and an empty suggestion list is a usable answer where a 404 is not.
    """
    try:
        resolved = resolve_release_or_404(repository, release=None, on_date=None)
    except HTTPException:
        return None, None
    found = repository.labels(list(variants), resolved)
    for candidate in variants:
        if candidate in found:
            return found[candidate], candidate
    return None, None


# ---------------------------------------------------------------------- 7. ECCT


@router.get(
    "/classifications/ecct",
    response_model=EcctOut,
    responses={429: {"model": ErrorOut}},
    summary="The Editorial Classification Change Table",
    dependencies=[Depends(_limit_classification)],
)
def ecct(
    classification: ClassificationDep,
    congress: int | None = Query(default=None),
    session: int | None = Query(
        default=None, description="1 or 2. 0 is a whole-congress table."
    ),
) -> EcctOut:
    """Provisions OLRC moved from one Code location to another without Congress
    amending them, newest session first.

    Returned whole rather than paged: the table is 21 rows across two documents,
    and only the 119th has one. The two filters exist for the sessions to come.
    """
    items = classification.list_ecct(congress=congress, session=session)
    return EcctOut(items=[EcctEntryOut.of(entry) for entry in items], total=len(items))


__all__ = ["router"]
