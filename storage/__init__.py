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
from storage.classification import (
    CLASSIFICATION_SORTS,
    CLASSIFICATION_SOURCE_URL,
    ClassificationCheckInfo,
    ClassificationEntryRef,
    ClassificationError,
    ClassificationFileInfo,
    ClassificationPage,
    ClassificationRepository,
    EcctEntryRef,
    UnknownPublicLawError,
    identifier_variants,
    law_in_ranges,
    normalize_section_input,
)
from storage.cache import (
    CorpusCache,
    cache_key,
    cache_status,
    close_cache_client,
    get_cache,
)
from storage.postgres import PostgresRepository, title_num_from_identifier
from storage.postgres_accounts import PostgresAccounts
from storage.postgres_classification import PostgresClassification
from storage.session import get_accounts, get_classification, get_repository
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
    RepositoryUnavailableError,
    ResolvedRelease,
    SectionResult,
    SectionVersionInfo,
    SourceCheckInfo,
    TitleInfo,
    TocEntry,
    TocResult,
    VersionLawRef,
)

__all__ = [
    "CLASSIFICATION_SORTS",
    "CLASSIFICATION_SOURCE_URL",
    "SOURCE_CHECK_STALE_AFTER",
    "SOURCE_URL",
    "AccountsError",
    "AccountsRepository",
    "AmbiguousReleaseError",
    "ClassificationCheckInfo",
    "ClassificationEntryRef",
    "ClassificationError",
    "ClassificationFileInfo",
    "ClassificationPage",
    "ClassificationRepository",
    "DuplicateEmailError",
    "EcctEntryRef",
    "GuidResolution",
    "Neighbors",
    "PostgresAccounts",
    "PostgresClassification",
    "PostgresRepository",
    "Provision",
    "ReleaseNotFoundError",
    "ReleaseRef",
    "Repository",
    "RepositoryError",
    "RepositoryUnavailableError",
    "ResolvedRelease",
    "SectionResult",
    "SectionVersionInfo",
    "SessionRef",
    "SourceCheckInfo",
    "TitleInfo",
    "TocEntry",
    "TocResult",
    "UnknownPublicLawError",
    "UnknownReleaseError",
    "UnknownTitleError",
    "UserRef",
    "VersionLawRef",
    "WatchlistItemRef",
    "WatchlistRef",
    "get_accounts",
    "get_classification",
    "get_repository",
    "identifier_variants",
    "law_in_ranges",
    "normalize_section_input",
    "title_num_from_identifier",
]
