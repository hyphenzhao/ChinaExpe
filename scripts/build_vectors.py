"""Build website and literature LanceDB vectors using local Ollama bge-m3.

Run on the NAS (where Ollama runs):  python3 scripts/build_vectors.py
"""
import asyncio
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import app  # noqa: E402,F401
from app.services.knowledge_service import knowledge_service  # noqa: E402
from scripts.build_website_vectors import build as build_website  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=("all", "ziwei", "literature"), default="all")
    args = parser.parse_args()
    def prog(done, total):
        if done % 160 == 0 or done == total:
            print(f"  {done}/{total}", flush=True)
    if args.scope in ("all", "ziwei"):
        print(asyncio.run(build_website(progress=prog)), flush=True)
    if args.scope in ("all", "literature"):
        result = asyncio.run(knowledge_service.build_literature_vectors(progress=prog))
        print(result, flush=True)
        if not result.get("success"):
            raise SystemExit(1)


if __name__ == "__main__":
    main()
