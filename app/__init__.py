"""玄学助手 application package.

Adds the vendored pure-python dependencies (``app/vendor``) to ``sys.path`` so
that ``import lunar_python`` works without a network-dependent pip install on
the NAS.
"""
import sys
from pathlib import Path

_VENDOR = Path(__file__).resolve().parent / "vendor"
if _VENDOR.is_dir() and str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))
