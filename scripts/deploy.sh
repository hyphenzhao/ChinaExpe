#!/usr/bin/env bash
# Deploy to the NAS: run tests, restart the service, verify health + autostart.
# Usage: bash scripts/deploy.sh [--skip-tests] [--skip-ui]
set -euo pipefail
cd "$(dirname "$0")/.."
HOST="haifeng@192.168.50.6"
PUBLIC="http://192.168.50.6:1248"
SKIP_TESTS=0; SKIP_UI=0
for a in "$@"; do case "$a" in --skip-tests) SKIP_TESTS=1;; --skip-ui) SKIP_UI=1;; esac; done

if [ "$SKIP_TESTS" = 0 ]; then
  echo "== pytest"
  # data/golden holds the private golden tests (real 文墨天机/测测 exports); it is git-ignored.
  TEST_PATHS="tests"; [ -d data/golden ] && TEST_PATHS="tests data/golden"
  PYTHONIOENCODING=utf-8 python -m pytest $TEST_PATHS -q
fi

echo "== syntax check (js)"
if command -v node >/dev/null 2>&1; then for f in app/static/js/v2/*.js; do node --check "$f"; done; fi

echo "== restart on NAS"
bash scripts/restart_remote.sh "$HOST" "$PUBLIC"

echo "== autostart status"
ssh -o BatchMode=yes "$HOST" 'printf "xuanxue: %s / %s\n" "$(systemctl is-enabled xuanxue)" "$(systemctl is-active xuanxue)"; printf "apache2: %s\n" "$(systemctl is-enabled apache2)"; printf "ollama: %s\n" "$(systemctl is-enabled ollama 2>/dev/null || echo n/a)"'

if [ "$SKIP_UI" = 0 ] && python -c "import playwright" 2>/dev/null; then
  echo "== ui smoke against production"
  PYTHONIOENCODING=utf-8 python scripts/ui_smoke.py "$PUBLIC" 2>/dev/null | grep -v "Overlapped\|windows_events\|_poll\|^Traceback\|RuntimeError" || true
fi
echo "== deployed: $PUBLIC  version: $(curl -s -m 5 "$PUBLIC/api/health")"
