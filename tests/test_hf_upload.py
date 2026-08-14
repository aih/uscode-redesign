"""The Hugging Face uploader (`ingest/hf_upload.py`, ADR-0069) against a mocked
`HfApi` — no network, no token."""

import json
from unittest.mock import MagicMock

import pytest

pytest.importorskip("huggingface_hub")

from ingest import hf_upload


def _manifest(tmp_path, partial=False):
    data_dir = tmp_path / "hf"
    data_dir.mkdir()
    manifest = {
        "exported_at": "2026-08-14T00:00:00+00:00",
        "git_commit": "abc123",
        "partial": partial,
        "fingerprint": {"newest_release": {"label": "119-102not101", "seq": 381}},
        "configs": {
            "current": {
                "rows": 65938,
                "shards": [{"name": "train-00000-of-00001.parquet", "bytes": 7, "sha256": "aa"}],
            },
            "versions": {
                "rows": 489738,
                "shards": [{"name": "train-00000-of-00001.parquet", "bytes": 9, "sha256": "bb"}],
            },
        },
    }
    (data_dir / "manifest.json").write_text(json.dumps(manifest))
    return data_dir


def test_init_repo_creates_and_uploads_the_card_only():
    api = MagicMock()
    api.create_repo.return_value = "https://huggingface.co/datasets/dreamproit/uscode"
    url = hf_upload.init_repo(api=api)
    api.create_repo.assert_called_once_with(
        "dreamproit/uscode", repo_type="dataset", private=False, exist_ok=True
    )
    assert api.upload_file.call_count == 1
    assert api.upload_file.call_args.kwargs["path_in_repo"] == "README.md"
    api.upload_folder.assert_not_called()
    assert url == "https://huggingface.co/datasets/dreamproit/uscode"


def test_upload_pushes_shards_with_the_release_label(tmp_path):
    data_dir = _manifest(tmp_path)
    api = MagicMock()
    api.upload_folder.return_value = MagicMock(commit_url="https://hf.co/commit/1")

    url = hf_upload.upload(
        data_dir=data_dir,
        api=api,
        verification_path=tmp_path / "hf-dataset.json",
    )

    kwargs = api.upload_folder.call_args.kwargs
    assert kwargs["repo_id"] == "dreamproit/uscode"
    assert kwargs["repo_type"] == "dataset"
    assert kwargs["commit_message"] == "Update to 119-102not101"
    assert kwargs["allow_patterns"] == kwargs["delete_patterns"]
    assert "current/*.parquet" in kwargs["allow_patterns"]
    api.upload_file.assert_not_called()
    assert url == "https://hf.co/commit/1"

    verification = json.loads((tmp_path / "hf-dataset.json").read_text())
    assert verification["repo"] == "dreamproit/uscode"
    assert verification["commit_url"] == "https://hf.co/commit/1"
    assert verification["newest_release"]["label"] == "119-102not101"
    assert verification["configs"]["current"]["rows"] == 65938


def test_upload_without_an_export_fails(tmp_path):
    with pytest.raises(FileNotFoundError):
        hf_upload.upload(data_dir=tmp_path, api=MagicMock())


def test_upload_refuses_a_partial_export(tmp_path):
    data_dir = _manifest(tmp_path, partial=True)
    with pytest.raises(ValueError, match="partial"):
        hf_upload.upload(data_dir=data_dir, api=MagicMock())


def test_upload_with_card_also_updates_the_readme(tmp_path):
    data_dir = _manifest(tmp_path)
    api = MagicMock()
    api.upload_folder.return_value = MagicMock(commit_url="https://hf.co/commit/2")
    hf_upload.upload(
        data_dir=data_dir,
        card=True,
        api=api,
        verification_path=tmp_path / "hf-dataset.json",
    )
    assert api.upload_file.call_count == 1
    assert api.upload_file.call_args.kwargs["path_in_repo"] == "README.md"
