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
