from pathlib import Path

from hugo.supervisor.pidfile import Pidfile


def test_read_returns_none_when_missing(tmp_path: Path) -> None:
    pidfile = Pidfile(tmp_path / "hugo.pid")

    assert pidfile.read() is None


def test_write_then_read_round_trips(tmp_path: Path) -> None:
    pidfile = Pidfile(tmp_path / "nested" / "hugo.pid")

    pidfile.write(12345)

    assert pidfile.read() == 12345


def test_read_returns_none_for_corrupt_contents(tmp_path: Path) -> None:
    path = tmp_path / "hugo.pid"
    path.write_text("not-a-pid")
    pidfile = Pidfile(path)

    assert pidfile.read() is None


def test_remove_is_safe_when_missing(tmp_path: Path) -> None:
    pidfile = Pidfile(tmp_path / "hugo.pid")

    pidfile.remove()  # must not raise

    assert pidfile.read() is None


def test_remove_deletes_file(tmp_path: Path) -> None:
    pidfile = Pidfile(tmp_path / "hugo.pid")
    pidfile.write(1)

    pidfile.remove()

    assert not pidfile.path.exists()
