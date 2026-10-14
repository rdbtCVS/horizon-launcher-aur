#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

bash -n PKGBUILD
sh -n horizon-launcher.sh
bash -n scripts/*.sh
desktop-file-validate horizon-launcher.desktop horizon.desktop
python -m unittest discover -s scripts -p 'test_*.py'
metadata=$(mktemp)
trap 'rm -f "$metadata"' EXIT
makepkg --printsrcinfo > "$metadata"
diff -u .SRCINFO "$metadata"
makepkg --cleanbuild --force --noconfirm

source PKGBUILD
archive=$(makepkg --packagelist)
diagnostics=$(mktemp)
trap 'rm -f "$metadata" "$diagnostics"' EXIT
namcap PKGBUILD "$archive" | tee "$diagnostics"
if grep -qE '(^Error:| E:)' "$diagnostics"; then
    printf 'Namcap reported a packaging error.\n' >&2
    exit 1
fi
test_home=$(mktemp -d)
trap 'rm -f "$metadata" "$diagnostics"; rm -rf "$test_home"' EXIT
export HORIZON_LAUNCHER_NO_SELF_UPDATE=1
export HORIZON_LAUNCHER_HOME="$test_home/launcher"
export XDG_DATA_HOME="$test_home/data"
export HORIZON_HOME="$test_home/game"
[[ $(pkg/horizon-launcher-bin/usr/lib/horizon-launcher/horizon-launcher --version) == "horizon-launcher $pkgver" ]]
pkg/horizon-launcher-bin/usr/lib/horizon-launcher/horizon-launcher --help >/dev/null
pkg/horizon-launcher-bin/usr/lib/horizon-launcher/horizon-launcher versions --installed --json
pkg/horizon-launcher-bin/usr/lib/horizon-launcher/horizon-launcher desktop-entry --remove
python - "$HORIZON_LAUNCHER_HOME/settings.json" <<'PY'
import json
import sys
from pathlib import Path
assert json.loads(Path(sys.argv[1]).read_text())["desktop_entry"] is False
PY
printf 'Package build, metadata, checksums and offline CLI smoke checks passed.\n'
