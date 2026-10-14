#!/usr/bin/env bash
# Push only the package recipe and its local sources, never GitHub automation or binaries.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${AUR_SSH_KEY_PATH:?Set AUR_SSH_KEY_PATH to the dedicated private key file}"
key_path=$(realpath "$AUR_SSH_KEY_PATH")
known_hosts=$(realpath scripts/aur_known_hosts)
printf -v GIT_SSH_COMMAND 'ssh -i %q -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=%q' "$key_path" "$known_hosts"
export GIT_SSH_COMMAND
staging=$(mktemp -d)
trap 'rm -rf "$staging"' EXIT
git clone ssh://aur@aur.archlinux.org/horizon-launcher-bin.git "$staging/aur"
files=(PKGBUILD .SRCINFO horizon-launcher.sh horizon-launcher.desktop horizon.desktop
       horizon.svg LICENSE.upstream OFL-Geist.txt LICENSE)
for file in "${files[@]}"; do
    cp "$file" "$staging/aur/$file"
done
cd "$staging/aur"
git config user.name rdbt
git config user.email 87152661+rdbtCVS@users.noreply.github.com
git add "${files[@]}"
if git diff --cached --quiet; then
    printf 'AUR already matches this package.\n'
    exit 0
fi
source PKGBUILD
git commit -m "Update horizon-launcher-bin to $pkgver-$pkgrel"
git push origin HEAD:master
