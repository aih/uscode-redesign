"""Storage layer: the `Repository` interface and its implementations.

`api/` and `web/` import from here and never from `db/` — PLAN §2's hard rule, so
the XCiteDB implementation can land beside `PostgresRepository` without either of
them noticing. `ingest/` is deliberately on the other side of this boundary: it
writes `db/` models directly.
"""

from storage.accounts import (
    AccountsError,
    AccountsRepository,
    DuplicateEmailError,
    SessionRef,
    UnknownReleaseError,
    UnknownTitleError,
    UserRef,
    WatchlistItemRef,
    WatchlistRef,
)
from storage.postgres import PostgresRepository, title_num_from_identifier
from storage.postgres_accounts import PostgresAccounts
from storage.session import get_accounts, get_repository
from storage.repository import (
    SOURCE_CHECK_STALE_AFTER,
    SOURCE_URL,
    AmbiguousReleaseError,
    GuidResolution,
    Neighbors,
    Provision,
    ReleaseNotFoundError,
    ReleaseRef,
    Repository,
    RepositoryError,
    ResolvedRelease,
    SectionResult,
    SectionVersionInfo,
    SourceCheckInfo,
    TitleInfo,
    TocEntry,
    TocResult,
)

__all__ = [
    "SOURCE_CHECK_STALE_AFTER",
    "SOURCE_URL",
    "AccountsError",
    "AccountsRepository",
    "AmbiguousReleaseError",
    "DuplicateEmailError",
    "GuidResolution",
    "Neighbors",
    "PostgresAccounts",
    "PostgresRepository",
    "Provision",
    "ReleaseNotFoundError",
    "ReleaseRef",
    "Repository",
    "RepositoryError",
    "ResolvedRelease",
    "SectionResult",
    "SectionVersionInfo",
    "SessionRef",
    "SourceCheckInfo",
    "TitleInfo",
    "TocEntry",
    "TocResult",
    "UnknownReleaseError",
    "UnknownTitleError",
    "UserRef",
    "WatchlistItemRef",
    "WatchlistRef",
    "get_accounts",
    "get_repository",
    "title_num_from_identifier",
]
