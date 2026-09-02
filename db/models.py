"""Core schema per PLAN.md §3. Sections are the storage atom (ADR-0001);
sub-section provisions are extracted from `xml` at request time, not stored
separately. Guids are (provision, release point) pins, never a cross-release
identity — see CLAUDE.md and ADR-0003 before touching guid_map."""

import datetime
import uuid

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class ReleasePoint(Base):
    __tablename__ = "release_points"

    id: Mapped[int] = mapped_column(primary_key=True)
    congress: Mapped[int] = mapped_column(Integer)
    law_num: Mapped[int] = mapped_column(Integer)
    excluded_laws: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=list)
    # `u1` re-issues of the same public law (`118-22` vs `118-22u1`): 17 of the 385
    # published release points, and distinct release points with distinct files, so
    # (congress, law_num, excluded_laws) does not identify one on its own.
    update_num: Mapped[int | None] = mapped_column(Integer, nullable=True)
    label: Mapped[str] = mapped_column(String, unique=True)  # e.g. '119-102not101'
    currency_date: Mapped[datetime.date] = mapped_column(Date)
    seq: Mapped[int] = mapped_column(Integer, unique=True)  # global ordering; labels don't sort
    # Which titles this release point actually changed, from the RP inventory —
    # every release point republishes all of them (gotcha 10). Drives ingest, and
    # is what /api/v1/releases reports as changed-title flags.
    titles_affected: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)


class SourceCheck(Base):
    """One poll of uscode.house.gov's release-points page.

    A row is written every time the inventory is fetched — including when the
    fetch *fails*, which is the case this table exists for. A mirror of a
    living source has two ways to fall behind: the source publishes something
    new and we don't ingest it, or we stop asking altogether. The first is
    visible (the newest release point on the site is older than the newest one
    on OLRC's page); the second is invisible, because a corpus that has stopped
    updating looks identical to a corpus with nothing to update. Recording the
    *attempt*, not just its result, is what tells those two apart, and it is
    what `/api/v1/status` reports and the reader shows on the releases page.

    Deliberately append-only and never pruned: at one row a day this is ~4 KB a
    year, and the history answers "when did it stop working" rather than only
    "is it working now".
    """

    __tablename__ = "source_checks"
    __table_args__ = (Index("ix_source_checks_checked_at", "checked_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    checked_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    source_url: Mapped[str] = mapped_column(String)
    ok: Mapped[bool] = mapped_column(Boolean)
    # NULL on a failed check — the page never parsed, so there is no count to
    # record. Zero would be a lie of a different kind.
    release_points_seen: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Labels the page carried that `release_points` did not already hold. This
    # is the answer to "was there anything new", and it is recorded rather than
    # recomputed because the next check will have seeded them and the answer
    # would be lost.
    new_labels: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    latest_label: Mapped[str | None] = mapped_column(String, nullable=True)
    latest_currency_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Title(Base):
    __tablename__ = "titles"

    id: Mapped[int] = mapped_column(primary_key=True)
    num: Mapped[str] = mapped_column(String, unique=True)  # '16', '05a'
    name: Mapped[str] = mapped_column(String)
    is_positive_law: Mapped[bool] = mapped_column(Boolean)


class TitleVersion(Base):
    __tablename__ = "title_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    title_id: Mapped[int] = mapped_column(ForeignKey("titles.id"))
    release_id: Mapped[int] = mapped_column(ForeignKey("release_points.id"))
    source_zip_sha256: Mapped[str] = mapped_column(String)
    schema_version: Mapped[str] = mapped_column(String)  # 'uslm-1.0.15' | 'uslm-2.x'
    downloaded_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    unchanged_from_release_id: Mapped[int | None] = mapped_column(
        ForeignKey("release_points.id"), nullable=True
    )
    sections_loaded: Mapped[int | None] = mapped_column(Integer, nullable=True)
    """Sections stored for this (title, release), written only once the load
    finishes. **NULL means the load did not complete** — the row is created before
    sections are read and `load_release` commits as it goes, so presence of the row
    proves nothing on its own. This is the resume marker `load-all` skips on, and
    the count `make verify` checks against `section_release_map`."""

    raw_section_elements: Mapped[int | None] = mapped_column(Integer, nullable=True)
    """`<section>` elements in the source file, including the ~298-per-Title-16
    that live inside `<quotedContent>` and are deliberately not stored (ADR-0005).
    Kept alongside `sections_loaded` so the gap stays visible without a re-parse."""


class Section(Base):
    __tablename__ = "sections"
    __table_args__ = (
        UniqueConstraint("title_id", "identifier"),
        # Resolution starts from a URL path and doesn't know the title_id yet.
        Index("ix_sections_identifier", "identifier"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title_id: Mapped[int] = mapped_column(ForeignKey("titles.id"))
    identifier: Mapped[str] = mapped_column(String)  # '/us/usc/t16/s45f' — cross-release identity


class StructureNode(Base):
    """The hierarchy above the section: title → chapter → subchapter → part → subpart.

    Nothing else holds a chapter's heading — `sections` stores only identifiers, and
    the TOC routes need names (PLAN §3, Day 1 item 3a). Filled by the parser's TOC
    pass from the *structural elements*, not from `<toc>` (ADR-0006).

    Unversioned on purpose (PLAN §3: "start unversioned and measure"). Headings
    change rarely; what does change is which nodes exist, so each row records the
    first and last release point it was seen in. `first_release_id` is a real filter
    — a chapter added at RP 119-99 must not appear in a 2013 TOC. `last_release_id`
    is informational only: with a handful of the 385 release points ingested,
    absence from the newest one is not evidence of removal.
    """

    __tablename__ = "structure_nodes"
    __table_args__ = (
        UniqueConstraint("title_id", "identifier"),
        Index("ix_structure_nodes_parent_id_seq", "parent_id", "seq"),
        # Lookup by identifier alone — what `get_section`, both `get_toc` paths
        # and `resolve_id` do. The unique constraint above leads with `title_id`,
        # and a composite index cannot serve a predicate on its second column, so
        # without this each of those sequentially scanned the table (measured:
        # 9,916 rows, 1.3 ms, migration d5c81f27a930).
        Index("ix_structure_nodes_identifier", "identifier"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title_id: Mapped[int] = mapped_column(ForeignKey("titles.id"))
    identifier: Mapped[str] = mapped_column(String)  # '/us/usc/t16/ch1/schVI'
    level: Mapped[str] = mapped_column(String)  # 'chapter' | 'subchapter' | … free text
    num: Mapped[str | None] = mapped_column(String, nullable=True)  # 'SUBCHAPTER VI—'
    num_value: Mapped[str | None] = mapped_column(String, nullable=True)  # 'VI'
    heading: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True)  # t16's one 'reserved'
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("structure_nodes.id"), nullable=True  # null for the title root
    )
    seq: Mapped[int] = mapped_column(Integer)  # document order among siblings
    depth: Mapped[int] = mapped_column(Integer)  # 0 = title root
    first_release_id: Mapped[int] = mapped_column(ForeignKey("release_points.id"))
    last_release_id: Mapped[int] = mapped_column(ForeignKey("release_points.id"))


class SectionVersion(Base):
    __tablename__ = "section_versions"
    __table_args__ = (
        UniqueConstraint("section_id", "content_hash", "first_release_id"),
        # Version-timeline queries. The unique constraint's index has content_hash
        # between these two columns, so it doesn't serve them (migration aef3da4cc2e9).
        Index("ix_section_versions_section_id_first_release_id", "section_id", "first_release_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id"))
    first_release_id: Mapped[int] = mapped_column(ForeignKey("release_points.id"))
    content_hash: Mapped[bytes] = mapped_column(LargeBinary)  # dedupe key
    xml: Mapped[str] = mapped_column(Text)  # raw XML fragment, verbatim
    html_cache: Mapped[str | None] = mapped_column(Text, nullable=True)
    num: Mapped[str | None] = mapped_column(String, nullable=True)
    heading: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True)  # repealed/omitted/transferred/reserved
    source_credit: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Facts about the content, so they sit on the content-deduped row (the
    # placement gotcha 15 cuts the other way for: these cannot change while the
    # text does not). Nullable so pre-existing rows are back-fillable by
    # `python -m ingest version-changes` (ADR-0074).
    text_hash: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    """sha256 of the parser's `plain_text()` with all whitespace removed —
    whitespace-insensitive reading text, apparatus excluded."""

    notes_hash: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    """sha256 of a stable serialization of `notes_text()` (topic/role/heading/
    text per note, joined with separators), all whitespace removed."""


class SectionVersionChange(Base):
    """One row per version group of a section, describing its arrival (ADR-0074).

    Annotates the transition from the previous stored version group to this one:
    what kind of change it was (`text` / `notes` / `structure`, decided in that
    priority; the section's earliest group is `initial`), over which release
    window, and whether the classification tables record a statute for it.
    `change_kind` and `attribution` are strings, not enums, per project
    convention (gotcha 13's lesson).

    The unique constraint on `to_version_id` is the idempotency key: recompute
    is delete-and-reinsert per section. Ordering of groups is by the earliest
    release each is mapped to in `section_release_map` — never by
    `first_release_id`, which an incremental load leaves high (ADR-0066).
    """

    __tablename__ = "section_version_changes"
    __table_args__ = (Index("ix_section_version_changes_section_id", "section_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id"))
    to_version_id: Mapped[int] = mapped_column(ForeignKey("section_versions.id"), unique=True)
    from_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("section_versions.id"), nullable=True
    )
    window_from_release_id: Mapped[int | None] = mapped_column(
        ForeignKey("release_points.id"), nullable=True
    )
    """Last release mapped to the departing group. NULL together with
    `from_version_id` on a section's first group."""

    window_to_release_id: Mapped[int] = mapped_column(ForeignKey("release_points.id"))
    """First release mapped to the arriving group."""

    change_kind: Mapped[str] = mapped_column(String)  # initial/text/notes/structure
    text_changed: Mapped[bool] = mapped_column(Boolean)
    notes_changed: Mapped[bool] = mapped_column(Boolean)
    heading_changed: Mapped[bool] = mapped_column(Boolean)
    status_changed: Mapped[bool] = mapped_column(Boolean)
    concurrent: Mapped[bool] = mapped_column(Boolean, default=False)
    """The two groups' release ranges overlap — the source published several
    elements under one identifier at one release point (ADR-0021), so window
    arithmetic is unreliable here and the UI says so."""

    attribution: Mapped[str] = mapped_column(String)
    """'classified' | 'editorial' | 'none'. `classified` when a classification
    row of the transition's own kind names a law in the window (a text row for
    a text change, a note row for a notes change); `editorial` when the only
    law in the window is one the Editorial Classification Change Table records
    as prompting a move into or out of this section (ADR-0077)."""

    computed_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SectionVersionChangeLaw(Base):
    """A Public Law attributed to one version transition (ADR-0074).

    Derived facts, re-derivable at any time by `version-changes --reattribute`.
    Deliberately **no foreign key into `classification_entries`** — those rows
    are deleted and re-inserted wholesale when their file changes, so nothing
    may FK into that table.
    """

    __tablename__ = "section_version_change_laws"
    __table_args__ = (UniqueConstraint("change_id", "pl_congress", "pl_num"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    change_id: Mapped[int] = mapped_column(
        ForeignKey("section_version_changes.id", ondelete="CASCADE")
    )
    pl_congress: Mapped[int] = mapped_column(Integer)
    pl_num: Mapped[int] = mapped_column(Integer)
    in_classification: Mapped[bool] = mapped_column(Boolean)
    """A classification row for this law names this section."""

    is_note_classification: Mapped[bool] = mapped_column(Boolean)
    """Only note rows name it — a note-only classification against a text
    transition is worth showing as such."""

    in_source_credit: Mapped[bool] = mapped_column(Boolean)
    """The citation newly appears in `source_credit` across the transition."""

    classification_actions: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    """Distinct `action` values of the matching rows (`''` = amended, `new`,
    `repealed`, `tr to`, …) — display vocabulary for the UI. An ECCT match adds
    OLRC's own token for a cross-reference to that table, `ed chg`."""

    in_ecct: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    """The Editorial Classification Change Table records this law as prompting
    an editorial move into or out of this section (ADR-0077)."""

    ecct_move: Mapped[str | None] = mapped_column(String, nullable=True)
    """The move as the ECCT writes it, former → new: `42:294t nt → 42:294u new`.
    NULL unless `in_ecct`."""


class SectionReleaseMap(Base):
    """Which version of a section a release point publishes — and where it sits.

    Reading order and parenthood are facts about (section, release point), not about
    the text: a section keeps its words while the sections around it are added or
    repealed, and a transferred section can move to another chapter without a
    character changing. Since `section_versions` is deduped on content (ADR-0007),
    storing either there would freeze it at the release the text first appeared in
    (ADR-0008).
    """

    __tablename__ = "section_release_map"
    __table_args__ = (
        # "Everything at this RP" scans and prev/next: release_id doesn't lead the PK.
        Index("ix_section_release_map_release_id_seq", "release_id", "seq_in_title"),
        # TOC leaf listing: the sections under one structure node, in reading order.
        Index(
            "ix_section_release_map_parent",
            "release_id",
            "parent_identifier",
            "seq_in_title",
        ),
    )

    section_version_id: Mapped[int] = mapped_column(
        ForeignKey("section_versions.id"), primary_key=True
    )
    release_id: Mapped[int] = mapped_column(ForeignKey("release_points.id"), primary_key=True)
    seq_in_title: Mapped[int] = mapped_column(Integer)  # document order -> prev/next
    parent_identifier: Mapped[str | None] = mapped_column(String, nullable=True)


class GuidMap(Base):
    __tablename__ = "guid_map"
    # Reverse lookup: provision @ release point -> guid.
    __table_args__ = (Index("ix_guid_map_release_id_identifier", "release_id", "identifier"),)

    guid: Mapped[str] = mapped_column(String, primary_key=True)  # (provision, release point) pin
    release_id: Mapped[int] = mapped_column(ForeignKey("release_points.id"))
    identifier: Mapped[str] = mapped_column(String)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String, unique=True)
    password_hash: Mapped[str | None] = mapped_column(String, nullable=True)  # null when OAuth-only
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Watchlist(Base):
    __tablename__ = "watchlists"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String)


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    watchlist_id: Mapped[int] = mapped_column(ForeignKey("watchlists.id"))
    identifier: Mapped[str] = mapped_column(String)
    title_id: Mapped[int] = mapped_column(ForeignKey("titles.id"))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    pinned_release_id: Mapped[int | None] = mapped_column(
        ForeignKey("release_points.id"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class UserSettings(Base):
    """One row per user, created lazily on first write (`storage/accounts.py`'s
    `get_settings`/`update_settings`) — a user who never changes anything costs
    no row, so `user_id` is both the primary key and the foreign key rather than
    a separate surrogate id that would only ever have one value per user anyway.

    `ondelete="CASCADE"` because a settings row with no user to belong to is not
    a fact worth keeping — deleting an account should not leave orphaned
    preference rows for `verify`/`test_architecture.py`-style audits to explain.
    """

    __tablename__ = "user_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    open_links_in_new_tab: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class LoginAttempt(Base):
    """One failed login, kept just long enough to slow the next one down.

    Only failures are recorded: a successful login clears the account's rows, so
    this table holds the tail of an ongoing guessing run and nothing else. It is
    deliberately not an audit log — there is no success record, no user agent,
    no session link — because an audit log of who signed in when is a different
    feature with different retention questions, and this one only has to answer
    "how many times has this been tried lately".

    Both `email` and `ip` are counted, separately: throttling only by email lets
    one host spray many accounts, and throttling only by IP lets a botnet grind
    one account. `email` is stored as typed-and-normalized rather than joined to
    `users`, so attempts against addresses that were never registered are
    counted too — otherwise probing for valid emails would be free.
    """

    __tablename__ = "login_attempts"
    # Every read is "this key, within this window", so the window belongs in the
    # index rather than being a filter applied after it.
    __table_args__ = (
        Index("ix_login_attempts_email_created_at", "email", "created_at"),
        Index("ix_login_attempts_ip_created_at", "ip", "created_at"),
        Index("ix_login_attempts_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String)
    ip: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AuthSession(Base):
    """A logged-in browser session (PLAN §4 auth).

    `id` is the sha256 hex of the random token the session cookie carries, never
    the token itself — the cookie is the only place the raw token exists, so a
    database read (backup, dump, replica) discloses nothing usable. `csrf_token`
    rides a second, readable cookie for the double-submit check on state-changing
    routes (docs/adr/0017): the session cookie alone proves a browser has *a*
    session, and the CSRF token proves the request came from a page that could
    read this session's own cookies, i.e. same-origin.
    """

    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # sha256(token)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    csrf_token: Mapped[str] = mapped_column(String)
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ClassificationFile(Base):
    """One source document from OLRC's Classification Tables (spec §2).

    A `kind='pl'` row is one `tbl{congress}{pl}_{session}.htm` file — which
    provision of which public law was classified where; a `kind='ecct'` row is
    an Editorial Classification Change Table. `kind` is a string and not an enum
    because the source has already added one document type to this family and
    may add another.

    `session` is 1 or 2, with **0 for the 104th's single whole-congress file**
    (`tbl104pl.htm`, covering 104-1 through 104-333). A sentinel rather than
    NULL, because `UniqueConstraint(kind, congress, session)` is what makes a
    re-fetch update a row in place, and NULL is never equal to itself in a
    unique index.

    `covered_laws_text` is the page header's public-law range, verbatim
    ("Public Law 119-70 and Public Laws 119-74 through 119-102"). It is the
    change-detection key: the pages carry no usable `Last-Modified` or `ETag`
    and embed a per-request `jsessionid`, so hashing the raw bytes detects
    nothing. `content_hash` is sha256 of the extracted `<PRE>` text — hex, like
    `title_versions.source_zip_sha256` — and gates the reload once a change is
    suspected. `covered_ranges` holds that same header parsed into gap-aware
    segments (`['70-70', '74-102']`), which is what answers whether a given
    public law is covered by a file that classified nothing for it.

    `row_count` and `skipped_lines` are the parse report kept beside the data,
    so a load that silently started dropping lines is visible without a
    re-parse.
    """

    __tablename__ = "classification_files"
    __table_args__ = (
        # One registry row per source document — a re-fetch updates in place
        # (spec §2: wholesale replace per file, one transaction).
        UniqueConstraint("kind", "congress", "session"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String)  # 'pl' | 'ecct' — open set
    congress: Mapped[int] = mapped_column(Integer)
    session: Mapped[int] = mapped_column(Integer)  # 1 | 2 | 0 = whole congress
    source_url: Mapped[str] = mapped_column(String)
    source_filename: Mapped[str] = mapped_column(String)  # 'tbl118pl_2nd.htm'
    covered_laws_text: Mapped[str | None] = mapped_column(Text, nullable=True)  # null for ECCT
    covered_ranges: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    first_law: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_law: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prepared_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    # The Stat. volume from the column header ('138 Stat.'). NULL for the 104th,
    # whose header is the volume-less 'Stat. Page' because that congress spans two.
    stat_volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_hash: Mapped[str] = mapped_column(String)  # sha256 hex of the <PRE> text
    fetched_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    row_count: Mapped[int] = mapped_column(Integer)
    skipped_lines: Mapped[int] = mapped_column(Integer)


class ClassificationEntry(Base):
    """One row of a Classification Table: a public-law provision and where it
    landed in the Code.

    Every `*_raw` column is the source cell verbatim after tag-stripping, and is
    NOT NULL with `''` for a blank cell — `description_raw = ''` means the
    section was amended, and `pl_section_raw = ''` means the row is about the
    whole law. Those blanks carry meaning, so they are stored as the empty
    string the source wrote rather than as NULL.

    The parsed columns beside them are best-effort. `pl_congress`/`pl_num` are
    nullable because a row whose Pub. L. cell fails to parse is kept and warned
    about, never dropped. `usc_identifier` is nullable by rule as well as by
    failure: appendix rows never derive one, since `5A / 405` cannot produce the
    `/us/usc/t5a/pl/92/463/s1` shape OLRC actually publishes, and a section cell
    naming a range rather than one section derives nothing either. Note and
    `prec` rows do derive the parent section's identifier, qualified by
    `is_note`/`action`.

    `title_num` is a string ('5a'), never an integer, and never an ORDER BY on
    its own — sort through `storage.postgres.title_sort_key` (gotcha 16).
    `section_norm` is lowercased with U+2013/U+2011 folded to '-', because OLRC
    writes section numbers with an en dash and no keyboard has that key
    (gotcha 17); it is the column user input is matched against.

    `action` is a string and not an enum: the Description column is an open set
    (`nt`, `new`, `nt new`, `prec`, `tr fr`, `tr to`, `omitted`, `repealed`,
    `gen amd`, `ed chg`, …) that the source extends without warning (gotcha 13's
    lesson applied to a second vocabulary).

    Rows are deleted and re-inserted wholesale when their file changes — the
    source has no row identity to diff against — so `id` is never a permalink
    and nothing foreign-keys into this table.
    """

    __tablename__ = "classification_entries"
    __table_args__ = (
        # Re-inserting a file's rows must not be able to double them.
        UniqueConstraint("file_id", "row_seq"),
        # "Everything Public Law 118-33 classified", in source order — the
        # /classifications/pl/{congress}/{law_num} route and the ?pl= filter.
        Index(
            "ix_classification_entries_pl_congress_pl_num_row_seq",
            "pl_congress",
            "pl_num",
            "row_seq",
        ),
        # "Everything ever classified to 42 U.S.C. 254c-15" — the
        # /classifications/code/{title_num}/{section} route, the ?title=/?section=
        # filters, and the `code` sort's leading columns.
        Index("ix_classification_entries_title_num_section_norm", "title_num", "section_norm"),
        # The by-identifier route, which is a lookup on the derived path alone
        # and cannot use the composite index above.
        Index("ix_classification_entries_usc_identifier", "usc_identifier"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[int] = mapped_column(
        ForeignKey("classification_files.id", ondelete="CASCADE")
    )
    row_seq: Mapped[int] = mapped_column(Integer)  # 0-based order within the file
    raw_line: Mapped[str] = mapped_column(Text)  # tag-stripped, verbatim
    title_raw: Mapped[str] = mapped_column(String)  # '5A'
    title_num: Mapped[str] = mapped_column(String)  # '5a' — string, see docstring
    is_appendix: Mapped[bool] = mapped_column(Boolean, default=False)
    section_raw: Mapped[str] = mapped_column(String)
    section_norm: Mapped[str] = mapped_column(String)  # lowercased, en dash -> '-'
    description_raw: Mapped[str] = mapped_column(String)  # '' = amended
    is_note: Mapped[bool] = mapped_column(Boolean, default=False)
    action: Mapped[str | None] = mapped_column(String, nullable=True)  # open set
    transfer_counterpart: Mapped[str | None] = mapped_column(String, nullable=True)  # '42/290ee-10'
    act_name: Mapped[str | None] = mapped_column(String, nullable=True)  # appendix rows
    usc_identifier: Mapped[str | None] = mapped_column(String, nullable=True)  # '/us/usc/t18/s3551'
    pl_congress: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pl_num: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pl_section_raw: Mapped[str] = mapped_column(String)  # '101(3)', '2(6), (7)', '' = whole law
    new_section_quote: Mapped[str | None] = mapped_column(String, nullable=True)  # 202 "1948"
    stat_volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stat_pages: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=list)
    # The Stat. cell's tokens verbatim, because not every page of the Statutes at
    # Large is a number: 110 Stat. 1321-9 and 3009-587 are single pages, and 1,658
    # of the 104th's 11,737 rows cite one, which `stat_pages` cannot hold. It also
    # keeps a range distinguishable from its endpoints — `863-866` is one token
    # here and two integers there.
    stat_page_labels: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)


class EcctEntry(Base):
    """One row of the Editorial Classification Change Table: a provision OLRC
    moved from one Code location to another without Congress amending it.

    The two classifications are stored raw ('42:294t nt') and split into the
    same `(title_num, section_norm, is_note)` triple `classification_entries`
    uses, so a section's editorial history is reachable from either end by the
    same normalized key. The split columns are nullable because the source
    writes free text in these cells and a cell that does not split is kept
    rather than dropped.

    `provision_affected` and `provision_prompting` are full public-law citation
    strings kept verbatim, with the congress and law number pulled out beside
    them when they parse.

    The file key and `row_seq` carry the same constraints as
    `classification_entries`, for the same reason: the load policy is wholesale
    replace per file, so a re-load must not be able to double these rows and a
    deleted registry row must not leave them orphaned.
    """

    __tablename__ = "ecct_entries"
    __table_args__ = (
        # Re-inserting a file's rows must not be able to double them.
        UniqueConstraint("file_id", "row_seq"),
        # Both directions of "what happened to this section" — the ECCT is read
        # from the old citation as often as from the new one.
        Index(
            "ix_ecct_entries_former_title_num_former_section_norm",
            "former_title_num",
            "former_section_norm",
        ),
        Index(
            "ix_ecct_entries_new_title_num_new_section_norm",
            "new_title_num",
            "new_section_norm",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[int] = mapped_column(
        ForeignKey("classification_files.id", ondelete="CASCADE")
    )
    row_seq: Mapped[int] = mapped_column(Integer)
    former_raw: Mapped[str] = mapped_column(String)  # '42:294t nt'
    former_title_num: Mapped[str | None] = mapped_column(String, nullable=True)
    former_section_norm: Mapped[str | None] = mapped_column(String, nullable=True)
    former_is_note: Mapped[bool] = mapped_column(Boolean, default=False)
    new_raw: Mapped[str] = mapped_column(String)  # '42:294u new'
    new_title_num: Mapped[str | None] = mapped_column(String, nullable=True)
    new_section_norm: Mapped[str | None] = mapped_column(String, nullable=True)
    new_is_note: Mapped[bool] = mapped_column(Boolean, default=False)
    provision_affected: Mapped[str] = mapped_column(Text)  # verbatim citation string
    provision_prompting: Mapped[str] = mapped_column(Text)
    affected_pl_congress: Mapped[int | None] = mapped_column(Integer, nullable=True)
    affected_pl_num: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompting_pl_congress: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompting_pl_num: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ClassificationSourceCheck(Base):
    """One poll of the Classification Tables index page.

    A sibling of `source_checks`, not a reuse of it. `last_source_check()` takes
    the newest row regardless of `source_url` and feeds `/api/v1/status`, so
    interleaving classification polls into that table would make the answer to
    "how current is the corpus" flap between two unrelated sources.

    Written on success and on failure, for the reason `SourceCheck`'s docstring
    gives: a scraper that has stopped running looks exactly like a source with
    nothing new. `files_seen` is NULL on a failed check rather than 0, and
    `changed_files` names the source filenames whose covered-law text differs
    from the registry — the answer to "was there anything new", recorded because
    the next successful load erases the evidence. `error` is truncated to 500
    characters by the writer.
    """

    __tablename__ = "classification_source_checks"
    # Every read is "the most recent one" — the freshness line on
    # /classifications/tables and the poll's own short-circuit.
    __table_args__ = (Index("ix_classification_source_checks_checked_at", "checked_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    checked_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    source_url: Mapped[str] = mapped_column(String)
    ok: Mapped[bool] = mapped_column(Boolean)
    files_seen: Mapped[int | None] = mapped_column(Integer, nullable=True)
    changed_files: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    latest_covered_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
