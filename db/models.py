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
    label: Mapped[str] = mapped_column(String, unique=True)  # e.g. '119-102not101'
    currency_date: Mapped[datetime.date] = mapped_column(Date)
    seq: Mapped[int] = mapped_column(Integer, unique=True)  # global ordering; labels don't sort


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


class Section(Base):
    __tablename__ = "sections"
    __table_args__ = (UniqueConstraint("title_id", "identifier"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    title_id: Mapped[int] = mapped_column(ForeignKey("titles.id"))
    identifier: Mapped[str] = mapped_column(String)  # '/us/usc/t16/s45f' — cross-release identity


class SectionVersion(Base):
    __tablename__ = "section_versions"
    __table_args__ = (
        UniqueConstraint("section_id", "content_hash", "first_release_id"),
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
    seq_in_title: Mapped[int] = mapped_column(Integer)  # document order -> prev/next
    source_credit: Mapped[str | None] = mapped_column(Text, nullable=True)


class SectionReleaseMap(Base):
    __tablename__ = "section_release_map"

    section_version_id: Mapped[int] = mapped_column(
        ForeignKey("section_versions.id"), primary_key=True
    )
    release_id: Mapped[int] = mapped_column(ForeignKey("release_points.id"), primary_key=True)


class GuidMap(Base):
    __tablename__ = "guid_map"

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
