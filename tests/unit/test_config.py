from pathlib import Path

from hugo.config import Config, load_config


def test_load_config_creates_state_dir(tmp_path: Path, monkeypatch) -> None:
    state_dir = tmp_path / "hugo-state"
    monkeypatch.setenv("HUGO_STATE_DIR", str(state_dir))

    config = load_config()

    assert config.state_dir == state_dir
    assert state_dir.is_dir()


def test_pidfile_and_memory_db_paths_live_under_state_dir(tmp_path: Path) -> None:
    config = Config(state_dir=tmp_path)

    assert config.pidfile_path == tmp_path / "hugo.pid"
    assert config.memory_db_path == tmp_path / "memory.db"


def test_tavily_api_key_defaults_to_none() -> None:
    assert Config().tavily_api_key is None


def test_tavily_api_key_loads_from_env(monkeypatch) -> None:
    monkeypatch.setenv("HUGO_TAVILY_API_KEY", "test-key")

    assert load_config().tavily_api_key == "test-key"
