"""Page-cache eviction for huge model checkpoints (VEN-56).

On the DGX Spark's unified memory, reading vLLM's 74.8GB checkpoint off
disk leaves it sitting in the page cache — and a subsequent CUDA
allocation does NOT force reclaim: Parakeet's STT load fails with a real
"CUDA error: out of memory" while `free` shows tens of GB in buff/cache
(reproduced live 2026-07-22 and again 2026-07-23). posix_fadvise
DONTNEED on the checkpoint files right after vLLM finishes loading makes
the next model's startup reliable. This existed as loose /tmp scripts on
dgx1 (evict_ckpt.py + evict_watcher.sh); the orchestrator now runs it as
the vllm spec's after_healthy hook.
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# getattr indirection because both names exist only on Linux (typeshed
# gates them by platform; dev machines are macOS). 4 is the Linux ABI
# value of POSIX_FADV_DONTNEED, never used when _fadvise is None.
_fadvise = getattr(os, "posix_fadvise", None)
_FADV_DONTNEED: int = getattr(os, "POSIX_FADV_DONTNEED", 4)


def evict_directory_from_page_cache(root: Path) -> int:
    """Advises the kernel to drop cached pages for every file under root.
    Returns the total size in bytes of the files advised. A no-op on
    platforms without posix_fadvise (macOS dev machines) and for files
    that vanish mid-walk."""
    if _fadvise is None:
        return 0
    total_bytes = 0
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            fd = os.open(path, os.O_RDONLY)
        except OSError:
            continue
        try:
            size = os.fstat(fd).st_size
            _fadvise(fd, 0, 0, _FADV_DONTNEED)  # length 0 = the whole file
            total_bytes += size
        except OSError:
            continue
        finally:
            os.close(fd)
    return total_bytes


def hf_model_cache_dir(model_id: str) -> Path:
    """The huggingface_hub cache directory for a model id like
    'org/name' — where vLLM's checkpoint shards actually live."""
    hf_home = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
    return hf_home / "hub" / f"models--{model_id.replace('/', '--')}"
