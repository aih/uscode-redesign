"""deploy/update-corpus.sh under uscode.house.gov's maintenance notice.

The script runs against stand-ins for `docker`, `aws` and `curl` on PATH. The
`docker` stand-in answers each `python -m ingest <command>` with the exit code
the test gives it, and logs the command.
"""

import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "deploy" / "update-corpus.sh"

DOCKER = textwrap.dedent(
    """\
    #!/usr/bin/env bash
    args="$*"
    case "$args" in
      *"python -m ingest "*)
        command="${args#*python -m ingest }"
        echo "$command" >> "$CALLS"
        name="${command%% *}"
        case "$name" in
          load-all) echo "planned 0: 0 loaded, 0 skipped, 0 failed" ;;
          classification) echo "4 documents linked: 4 loaded, 0 unchanged, 0 skipped, 0 failed, 0 with new content" ;;
        esac
        code_var="EXIT_$(echo "$name" | tr 'a-z-' 'A-Z_')"
        exit "${!code_var:-0}"
        ;;
      *"python -c"*) echo 0 ;;
    esac
    exit 0
    """
)


@pytest.fixture
def run_script(tmp_path):
    if shutil.which("flock") is None:
        pytest.skip("flock is not installed")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "docker").write_text(DOCKER)
    (bin_dir / "aws").write_text("#!/usr/bin/env bash\nexit 0\n")
    (bin_dir / "curl").write_text("#!/usr/bin/env bash\nexit 0\n")
    for tool in bin_dir.iterdir():
        tool.chmod(0o755)
    calls = tmp_path / "calls"
    calls.touch()

    def run(*args: str, **exits: int) -> tuple[int, list[str], str]:
        env = {
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "DATA_ROOT": str(tmp_path / "data"),
            "CALLS": str(calls),
            **{f"EXIT_{name.upper()}": str(code) for name, code in exits.items()},
        }
        calls.write_text("")
        done = subprocess.run(
            ["bash", str(SCRIPT), *args],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return done.returncode, calls.read_text().splitlines(), done.stdout

    return run


def _names(calls: list[str]) -> list[str]:
    return [call.split(" --")[0] for call in calls]


def test_a_forced_sweep_under_maintenance_loads_the_mirror_and_exits_75(run_script):
    code, calls, out = run_script(
        "--force", classification_check=75, check=75, inventory=75, classification=75
    )
    assert code == 75, out
    names = _names(calls)
    assert names[:2] == ["classification-check", "check"]
    assert "mirror pull" in names
    assert "load-all" in names
    assert "version-changes" in names
    assert "verify" in names
    assert not {"inventory", "backfill", "mirror push", "classification"} & set(names)
    assert "under maintenance" in out


def test_the_daily_poll_under_maintenance_stops_and_exits_75(run_script):
    code, calls, out = run_script(classification_check=75, check=75)
    assert code == 75, out
    assert _names(calls) == ["classification-check", "check"]


def test_classification_down_alone_still_downloads(run_script):
    code, calls, out = run_script("--force", classification_check=75)
    assert code == 75, out
    names = _names(calls)
    assert {"inventory", "backfill", "mirror push", "load-all"} <= set(names)
    assert "classification" not in names


def test_maintenance_beginning_at_inventory_skips_the_downloads(run_script):
    code, calls, out = run_script("--force", inventory=75)
    assert code == 75, out
    names = _names(calls)
    assert "inventory" in names
    assert not {"backfill", "mirror push"} & set(names)
    assert "load-all" in names


def test_a_sweep_with_the_source_up_exits_0(run_script):
    code, calls, out = run_script("--force")
    assert code == 0, out
    assert {"classification", "inventory", "backfill", "mirror push"} <= set(
        _names(calls)
    )


def test_a_real_failure_is_still_a_failure(run_script):
    code, _, out = run_script("--force", check=1, inventory=1)
    assert code == 1, out


def test_a_real_classification_failure_outranks_maintenance(run_script):
    code, _, out = run_script("--force", classification_check=1, check=75)
    assert code == 1, out
