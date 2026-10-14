#!/usr/bin/env bash
set -euo pipefail
# Runs as root only inside the disposable Arch CI container.
pacman -Syu --noconfirm --needed python desktop-file-utils namcap git \
    bash glibc libgcc libxcb libxkbcommon libxkbcommon-x11 wayland \
    vulkan-icd-loader hicolor-icon-theme xdg-utils
useradd --create-home builder
chown -R builder:builder "$GITHUB_WORKSPACE"
git config --global --add safe.directory "$GITHUB_WORKSPACE"
