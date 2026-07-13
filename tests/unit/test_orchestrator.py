"""Tests the orchestrator's pure construction logic (health check URL
building, process spec assembly) without spawning real subprocesses —
process_manager.py's own tests already cover spawn/health-check/teardown
mechanics. The websocket health check is exercised against a real (tiny,
local) websocket server, same pattern as test_stt_roundtrip.py."""

from pathlib import Path

import pytest
import websockets

from hugo.config import Config
from hugo.orchestrator import _build_specs, _http_health_check, _websocket_health_check


class _FakeHttpResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _FakeHttpClient:
    def __init__(self, status_code: int, urls: list[str]) -> None:
        self._status_code = status_code
        self._urls = urls

    async def __aenter__(self) -> "_FakeHttpClient":
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        return None

    async def get(self, url: str) -> _FakeHttpResponse:
        self._urls.append(url)
        return _FakeHttpResponse(self._status_code)


async def test_http_health_check_builds_health_path_from_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_urls: list[str] = []
    monkeypatch.setattr(
        "hugo.orchestrator.httpx.AsyncClient",
        lambda **_kwargs: _FakeHttpClient(200, requested_urls),
    )

    check = _http_health_check("http://127.0.0.1:8000/v1")
    result = await check()

    assert result is True
    assert requested_urls == ["http://127.0.0.1:8000/health"]


async def test_http_health_check_returns_false_on_non_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "hugo.orchestrator.httpx.AsyncClient",
        lambda **_kwargs: _FakeHttpClient(503, []),
    )

    check = _http_health_check("http://127.0.0.1:8000/v1")

    assert await check() is False


async def test_websocket_health_check_true_for_a_reachable_server() -> None:
    async def handler(_ws: object) -> None:
        return None

    async with websockets.serve(handler, "127.0.0.1", 0) as server:
        port = next(iter(server.sockets)).getsockname()[1]
        check = _websocket_health_check(f"ws://127.0.0.1:{port}")

        assert await check() is True


async def test_websocket_health_check_false_for_an_unreachable_server() -> None:
    check = _websocket_health_check("ws://127.0.0.1:1")  # nothing listens on port 1

    assert await check() is False


def test_build_specs_names_and_commands(tmp_path: Path) -> None:
    config = Config(repo_dir=tmp_path, state_dir=tmp_path / "state")

    specs = _build_specs(config)

    names = [s.name for s in specs]
    assert names == ["vllm", "stt", "tts"]

    vllm_spec = specs[0]
    assert vllm_spec.command[0] == str(tmp_path / ".venv-vllm" / "bin" / "vllm")
    assert vllm_spec.command[1:3] == ["serve", config.llm_model]

    stt_spec = specs[1]
    assert stt_spec.command == [
        str(tmp_path / ".venv-stt" / "bin" / "python"),
        "-m",
        "hugo.servers.stt_server",
    ]

    tts_spec = specs[2]
    assert tts_spec.command == [
        str(tmp_path / ".venv-tts" / "bin" / "python"),
        "-m",
        "hugo.servers.tts_server",
    ]


def test_build_specs_all_have_health_checks(tmp_path: Path) -> None:
    config = Config(repo_dir=tmp_path, state_dir=tmp_path / "state")

    specs = _build_specs(config)

    assert all(spec.health_check is not None for spec in specs)
