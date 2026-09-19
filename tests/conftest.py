"""Public tests use a fictional birth only.

The golden tests against real 文墨天机 / 测测 exports contain personal birth data
and live in data/golden/ (git-ignored); deploy.sh runs them when present.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import app  # noqa: E402,F401  (adds vendored lunar_python to sys.path)

# Fictional sample: 2000-01-01 12:00 (UTC+8 clock time), male, Beijing longitude.
SAMPLE = {"solar": "2000-01-01 12:00", "gender": "男", "longitude": 116.4}


def sample_birth():
    from app.engine.settings import BirthInput
    from app.engine.calendar import parse_dt
    return BirthInput(solar=parse_dt(SAMPLE["solar"]), gender=SAMPLE["gender"], longitude=SAMPLE["longitude"])
