from pathlib import Path

from typer.testing import CliRunner

from hugo.cli import app

runner = CliRunner()


def test_status_reports_not_running_when_no_pidfile(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HUGO_STATE_DIR", str(tmp_path))

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 1
    assert "not running" in result.output


def test_status_reports_running_for_a_live_pid(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HUGO_STATE_DIR", str(tmp_path))
    (tmp_path / "hugo.pid").write_text(str(1))  # pid 1 always exists

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert "is running" in result.output


def test_status_reports_not_running_for_a_stale_pidfile(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HUGO_STATE_DIR", str(tmp_path))
    # PID 999999 is very unlikely to exist on any real machine.
    (tmp_path / "hugo.pid").write_text(str(999_999))

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 1
    assert "not running" in result.output
