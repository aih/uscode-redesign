"""The S3 mirror: command construction, push ordering, pull verification.

No aws CLI and no network: every test injects a `runner` that records the
argv it was given (and optionally fakes the transfer's side effects on disk),
so what's under test is the contract — what gets synced, in what order, with
which filters — and the hash verification, which is real.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

from ingest.backfill import DownloadLedger, LedgerEntry
from ingest.download import FetchStatus
from ingest.mirror import (
    MirrorError,
    _include_patterns,
    pull,
    push,
    resolve_bucket,
)


def _zip_bytes(payload: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("usc.xml", payload)
    return buffer.getvalue()


class RecordingRunner:
    """Records every aws invocation; optionally performs fake side effects."""

    def __init__(self, on_run=None):
        self.commands: list[list[str]] = []
        self.on_run = on_run

    def __call__(self, cmd: list[str]) -> int:
        self.commands.append(cmd)
        if self.on_run is not None:
            return self.on_run(cmd)
        return 0


def _corpus(tmp_path: Path, members: dict[str, bytes]) -> Path:
    """A downloaded corpus + matching ledger under tmp_path/releases."""
    dest = tmp_path / "releases"
    ledger = DownloadLedger(dest / "ledger.json")
    for key, body in members.items():
        release, title = key.split("/")
        path = dest / release / f"xml_usc{title}@{release}.zip"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        ledger.record(
            LedgerEntry(
                release_label=release,
                title_num=title,
                status=str(FetchStatus.OK),
                url=f"https://example/{key}",
                path=f"{release}/xml_usc{title}@{release}.zip",
                sha256=hashlib.sha256(body).hexdigest(),
                bytes=len(body),
            )
        )
    ledger.save()
    return dest


# --------------------------------------------------------------------------
# Bucket resolution
# --------------------------------------------------------------------------


def test_bucket_normalizes_bare_name():
    assert resolve_bucket("my-usc-mirror") == "s3://my-usc-mirror"
    assert resolve_bucket("s3://my-usc-mirror/") == "s3://my-usc-mirror"


def test_bucket_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("USC_MIRROR_BUCKET", "env-bucket")
    assert resolve_bucket(None) == "s3://env-bucket"


def test_no_bucket_anywhere_is_an_error(monkeypatch):
    monkeypatch.delenv("USC_MIRROR_BUCKET", raising=False)
    with pytest.raises(MirrorError, match="USC_MIRROR_BUCKET"):
        resolve_bucket(None)


# --------------------------------------------------------------------------
# Push
# --------------------------------------------------------------------------


def test_push_uploads_ledger_last(tmp_path):
    """The ordering property: a reader of the mirror must never see a ledger
    that references zips the mirror doesn't hold yet."""
    dest = _corpus(tmp_path, {"113-21/16": _zip_bytes(b"a")})
    runner = RecordingRunner()

    push("bkt", dest_dir=dest, inventory_path=tmp_path / "none.json",
         manifest_dir=tmp_path / "no-manifests",
         verification_path=tmp_path / "no-verify.json", runner=runner)

    sync_cmd = runner.commands[0]
    assert sync_cmd[:3] == ["aws", "s3", "sync"]
    assert "ledger.json" in sync_cmd  # excluded from the bulk sync
    assert sync_cmd[sync_cmd.index("ledger.json") - 1] == "--exclude"

    last = runner.commands[-1]
    assert last[:3] == ["aws", "s3", "cp"]
    assert last[4] == "s3://bkt/usc/releases/ledger.json"


def test_push_excludes_partial_files(tmp_path):
    dest = _corpus(tmp_path, {"113-21/16": _zip_bytes(b"a")})
    runner = RecordingRunner()

    push("bkt", dest_dir=dest, inventory_path=tmp_path / "none.json",
         manifest_dir=tmp_path / "no-manifests",
         verification_path=tmp_path / "no-verify.json", runner=runner)

    sync_cmd = runner.commands[0]
    assert "*.part" in sync_cmd


def test_push_includes_inventory_and_manifests_when_present(tmp_path):
    dest = _corpus(tmp_path, {"113-21/16": _zip_bytes(b"a")})
    inventory = tmp_path / "uscreleasepoints.json"
    inventory.write_text("{}")
    manifests = tmp_path / "manifests"
    manifests.mkdir()
    runner = RecordingRunner()

    push("bkt", dest_dir=dest, inventory_path=inventory, manifest_dir=manifests,
         verification_path=tmp_path / "no-verify.json", runner=runner)

    joined = [" ".join(c) for c in runner.commands]
    assert any("uscreleasepoints.json" in c and " cp " in c for c in joined)
    assert any("manifests" in c and " sync " in c for c in joined)


def test_push_failure_raises_before_ledger_upload(tmp_path):
    """If the corpus sync fails, the ledger must NOT be pushed — the mirror keeps
    advertising its previous complete state."""
    dest = _corpus(tmp_path, {"113-21/16": _zip_bytes(b"a")})
    runner = RecordingRunner(on_run=lambda cmd: 1 if cmd[2] == "sync" else 0)

    with pytest.raises(MirrorError):
        push("bkt", dest_dir=dest, inventory_path=tmp_path / "none.json",
             manifest_dir=tmp_path / "no-manifests",
             verification_path=tmp_path / "no-verify.json", runner=runner)

    assert not any("ledger.json" in c[-1] for c in runner.commands if c[2] == "cp")


# --------------------------------------------------------------------------
# Pull
# --------------------------------------------------------------------------


def test_pull_of_empty_mirror_is_not_an_error(tmp_path):
    """First boot on a fresh bucket: no ledger up there yet, start from nothing."""
    runner = RecordingRunner(on_run=lambda cmd: 1 if "ledger.json" in cmd[3] else 0)

    report = pull("bkt", dest_dir=tmp_path / "releases",
                  inventory_path=tmp_path / "inv.json", runner=runner)

    assert report.pulled_ledger is False
    assert report.sound
    assert len(runner.commands) == 1  # stopped after the ledger probe


def test_pull_verifies_hashes_against_the_ledger(tmp_path):
    """The transfer tool is trusted for transport, never for integrity."""
    body = _zip_bytes(b"content")
    dest = _corpus(tmp_path, {"113-21/16": body})  # simulates a completed sync

    report = pull("bkt", dest_dir=dest, inventory_path=tmp_path / "inv.json",
                  runner=RecordingRunner())

    assert report.pulled_ledger
    assert report.verified == 1
    assert report.sound


def test_pull_reports_a_corrupt_file(tmp_path):
    dest = _corpus(tmp_path, {"113-21/16": _zip_bytes(b"content")})
    (dest / "113-21" / "xml_usc16@113-21.zip").write_bytes(_zip_bytes(b"corrupt"))

    report = pull("bkt", dest_dir=dest, inventory_path=tmp_path / "inv.json",
                  runner=RecordingRunner())

    assert report.mismatched == ["113-21/16"]
    assert not report.sound


def test_pull_reports_a_file_the_sync_never_delivered(tmp_path):
    dest = _corpus(tmp_path, {"113-21/16": _zip_bytes(b"content")})
    (dest / "113-21" / "xml_usc16@113-21.zip").unlink()

    report = pull("bkt", dest_dir=dest, inventory_path=tmp_path / "inv.json",
                  runner=RecordingRunner())

    assert report.missing == ["113-21/16"]
    assert not report.sound


def test_pull_title_filter_verifies_only_that_slice(tmp_path):
    """A dev pulling `--title 16` must not be failed over Title 42's absence."""
    dest = _corpus(tmp_path, {"113-21/16": _zip_bytes(b"a"), "113-21/42": _zip_bytes(b"b")})
    (dest / "113-21" / "xml_usc42@113-21.zip").unlink()  # never pulled

    report = pull("bkt", dest_dir=dest, inventory_path=tmp_path / "inv.json",
                  titles={"16"}, runner=RecordingRunner())

    assert report.entries_checked == 1
    assert report.sound


def test_pull_builds_include_filters(tmp_path):
    dest = _corpus(tmp_path, {"113-21/16": _zip_bytes(b"a")})
    runner = RecordingRunner()

    pull("bkt", dest_dir=dest, inventory_path=tmp_path / "inv.json",
         titles={"16"}, verify=False, runner=runner)

    sync_cmd = next(c for c in runner.commands if c[2] == "sync")
    assert "--exclude" in sync_cmd and "*" in sync_cmd
    assert "*/xml_usc16@*" in sync_cmd


# --------------------------------------------------------------------------
# Filter patterns
# --------------------------------------------------------------------------


def test_no_filters_means_everything():
    assert _include_patterns(None, None) is None


def test_title_filter_normalizes():
    assert _include_patterns({"5"}, None) == ["*/xml_usc05@*"]


def test_release_filter():
    assert _include_patterns(None, {"119-99"}) == ["119-99/*"]


def test_title_and_release_intersect_via_the_product():
    """aws-cli `--include` flags union, so intersection needs per-pair patterns."""
    patterns = _include_patterns({"16", "5"}, {"119-99"})
    assert patterns == ["119-99/xml_usc05@*", "119-99/xml_usc16@*"]
