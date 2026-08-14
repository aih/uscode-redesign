"""Upload the exported parquet shards to the Hugging Face dataset repo (ADR-0069).

Two entry points, matching the one-time / recurring split:

  * `init_repo()` — one-time setup: create `dreamproit/uscode` (idempotent,
    `exist_ok=True`) and upload the committed card as its `README.md`. Pushes
    no data.
  * `upload()`   — the recurring path: push `data/hf/`'s shards and manifest in
    one commit. Unchanged files are skipped by hash on the hub side;
    `delete_patterns` removes shards a re-export no longer writes, so a
    changed shard count leaves no orphans.

Authentication is whatever `huggingface_hub` finds on its own — the token
`hf auth login` stored under `~/.cache/huggingface/`, or `HF_TOKEN`. Nothing
here takes a token argument, so no token can end up in a shell history or a
commit.

After a data upload, `docs/verification/hf-dataset.json` records what went out
(documentation duty 5) — commit it.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

from huggingface_hub import HfApi

DEFAULT_REPO = "dreamproit/uscode"
CARD_PATH = Path("docs/hf/dataset-card.md")
VERIFICATION_PATH = Path("docs/verification/hf-dataset.json")

_DATA_PATTERNS = ["current/*.parquet", "versions/*.parquet", "manifest.json"]


def init_repo(
    *,
    repo_id: str = DEFAULT_REPO,
    card: Path = CARD_PATH,
    private: bool = False,
    api: HfApi | None = None,
) -> str:
    """Create the dataset repo and upload the card. Safe to re-run."""
    api = api or HfApi()
    url = api.create_repo(
        repo_id, repo_type="dataset", private=private, exist_ok=True
    )
    api.upload_file(
        path_or_fileobj=card,
        path_in_repo="README.md",
        repo_id=repo_id,
        repo_type="dataset",
        commit_message="Update dataset card",
    )
    return str(url)


def upload(
    *,
    repo_id: str = DEFAULT_REPO,
    data_dir: Path = Path("data/hf"),
    card: bool = False,
    message: str | None = None,
    api: HfApi | None = None,
    verification_path: Path = VERIFICATION_PATH,
) -> str:
    """Push the exported shards (and optionally the card) in one commit each."""
    manifest_path = data_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"{manifest_path} does not exist — run `make hf-export` first"
        )
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("partial"):
        raise ValueError(
            f"{manifest_path} records a --limit export; refusing to publish a "
            "partial corpus (re-run `make hf-export` without --limit)"
        )

    api = api or HfApi()
    newest = (manifest.get("fingerprint", {}).get("newest_release") or {}).get("label")
    commit = api.upload_folder(
        folder_path=data_dir,
        repo_id=repo_id,
        repo_type="dataset",
        allow_patterns=_DATA_PATTERNS,
        delete_patterns=_DATA_PATTERNS,
        commit_message=message or (f"Update to {newest}" if newest else "Update data"),
    )
    if card:
        api.upload_file(
            path_or_fileobj=CARD_PATH,
            path_in_repo="README.md",
            repo_id=repo_id,
            repo_type="dataset",
            commit_message="Update dataset card",
        )

    commit_url = getattr(commit, "commit_url", str(commit))
    _write_verification(
        verification_path, repo_id=repo_id, commit_url=commit_url, manifest=manifest
    )
    return commit_url


def _write_verification(
    path: Path, *, repo_id: str, commit_url: str, manifest: dict
) -> None:
    payload = {
        "_comment": (
            "What the last `make hf-upload` published (ADR-0069). Regenerate "
            "by re-running it; the shard hashes come from data/hf/manifest.json."
        ),
        "repo": repo_id,
        "uploaded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "commit_url": commit_url,
        "newest_release": manifest.get("fingerprint", {}).get("newest_release"),
        "exported_at": manifest.get("exported_at"),
        "git_commit": manifest.get("git_commit"),
        "configs": {
            name: {
                "rows": entry.get("rows"),
                "shards": [shard["name"] for shard in entry.get("shards", [])],
                "bytes": sum(shard.get("bytes", 0) for shard in entry.get("shards", [])),
                "sha256": {
                    shard["name"]: shard["sha256"] for shard in entry.get("shards", [])
                },
            }
            for name, entry in manifest.get("configs", {}).items()
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")
