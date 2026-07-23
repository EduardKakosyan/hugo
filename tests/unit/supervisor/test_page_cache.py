from pathlib import Path

import pytest

from hugo.supervisor import page_cache
from hugo.supervisor.page_cache import evict_directory_from_page_cache, hf_model_cache_dir


def test_hf_model_cache_dir_matches_hub_layout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HF_HOME", "/models/hf")

    path = hf_model_cache_dir("nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-NVFP4")

    assert path == Path("/models/hf/hub/models--nvidia--NVIDIA-Nemotron-3-Super-120B-A12B-NVFP4")


def test_evict_walks_files_and_reports_bytes(tmp_path: Path) -> None:
    (tmp_path / "shard-1.safetensors").write_bytes(b"x" * 100)
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "shard-2.safetensors").write_bytes(b"y" * 50)

    evicted = evict_directory_from_page_cache(tmp_path)

    # On Linux both files are advised; platforms without posix_fadvise
    # (macOS dev machines) report a clean no-op.
    assert evicted == (150 if page_cache._fadvise is not None else 0)


def test_evict_missing_directory_is_a_no_op(tmp_path: Path) -> None:
    assert evict_directory_from_page_cache(tmp_path / "does-not-exist") == 0
