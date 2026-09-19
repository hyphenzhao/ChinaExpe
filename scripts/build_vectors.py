"""Build LanceDB vectors for knowledge_base/literature using Ollama bge-m3.

Run on the NAS (where Ollama runs):  python3 scripts/build_vectors.py
"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import app  # noqa: E402,F401
from app.services.knowledge_service import knowledge_service  # noqa: E402


def main():
    def prog(done, total):
        print(f"\r  {done}/{total}", end="", flush=True)
    res = asyncio.run(knowledge_service.build_literature_vectors(progress=prog))
    print()
    print(res)


if __name__ == "__main__":
    main()
