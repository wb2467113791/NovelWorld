"""使用真实 Chroma 检索、固定模型替身和真实工具执行 20 Tick。"""

import tempfile
from pathlib import Path

from demo_v1 import run_demo
from retrieval.chroma_index import ChromaIndex


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
        run_demo(lambda world_id: ChromaIndex(world_id, Path(directory)))
