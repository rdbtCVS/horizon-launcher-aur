# Horizon launcher for Arch Linux

Community-maintained AUR package for the official Linux x86_64 launcher releases
from [ludovic111/horizon](https://github.com/ludovic111/horizon), maintained by
**rdbt**. This repository contains the package recipe and update automation.
Upstream does not maintain this package.

## Install

```sh
paru -S horizon-launcher-bin
# or: yay -S horizon-launcher-bin
```

Without an AUR helper:

```sh
git clone https://aur.archlinux.org/horizon-launcher-bin.git
cd horizon-launcher-bin
makepkg -si
```

Launch **Horizon** from the applications menu or run `horizon-launcher`.
Use `horizon-launcher --help` for the CLI or `horizon-launcher mcp` for the MCP server.

You need a working Vulkan driver. Preparing game resources requires your own
Minecraft: Java Edition installation and a Java 25 JDK (`jdk25-openjdk`); older
Horizon versions may also need Python. GNOME Keyring or KWallet can store Microsoft
sign-in credentials between sessions. No Minecraft assets are included.

## Package integration

Update the launcher through your AUR helper. The `horizon-launcher` command wraps
the executable in `/usr/lib/horizon-launcher/` and disables launcher self-updates.
Game downloads and updates remain managed by the launcher, with data normally
stored in `~/.local/share/horizon-launcher`.

The package installs the system menu entries and icon. Opening the GUI through
the wrapper removes separate per-user entries and disables their automatic
registration, preserving other settings. The launcher's applications-menu switch
does not control the package's system entry.

The wrapper sets `HORIZON_LAUNCHER_DESKTOP_EXEC=/usr/bin/horizon-launcher` so newly
generated menu entries also use the wrapper, including after re-enabling the
switch in Settings. **Launcher 0.2.0 does not support this override; it requires a
new upstream release.** After upgrading to a supporting release, run
`horizon-launcher` once from a terminal to clear older entries that bypassed it.

## Maintain

```sh
python scripts/update.py                  # newest stable launcher-vX.Y.Z
python scripts/update.py --check          # release metadata only; no package changes
python scripts/update.py --refresh        # refresh current release and local checksums
bash scripts/validate.sh                 # requires namcap and desktop-file-utils
```

The updater selects stable `launcher-vX.Y.Z` releases and refreshes the archive
checksum, icon, licence notices and `.SRCINFO`. All sources are pinned with
SHA-256; downloads are also checked against GitHub's published digest when
available. For packaging changes at the same launcher version, increment
`pkgrel` and run `--refresh` before committing.

GitHub Actions checks for updates every 15 minutes and on manual dispatch.
Scheduled runs skip builds when the package version is current and wait for the
Linux archive before updating. GitHub may delay scheduled runs.

Updates and pushes to `main` build in an Arch container, run the updater and
wrapper tests, validate desktop entries and metadata, check namcap diagnostics,
and run offline CLI smoke checks before publishing. Pull requests validate with
read-only permissions and no AUR credentials.

For a manual rebuild or publication retry, enable **force** on the workflow's
dispatch form or run:

```sh
gh workflow run update.yml -f force=true
```

## Publishing

Publishing uses an independent AUR Git repository. Only `PKGBUILD`, `.SRCINFO`,
the wrapper, desktop entries, icon and licence notices are copied there.

To configure publishing on a new copy of this repository:

1. Add a dedicated SSH public key to your AUR account.
2. Store the matching private key in the `AUR_SSH_PRIVATE_KEY` Actions secret.
3. Set the Actions repository variable `AUR_PUBLISH_ENABLED` to `true`.
4. Run the **Update and publish AUR package** workflow.

The AUR host key in `scripts/aur_known_hosts` was checked against the fingerprint
published on [the AUR homepage](https://aur.archlinux.org/):
`SHA256:RFzBCUItH9LZS0cKB5UE6ceAYhBD5C8GeOBip8Z11+4` (Ed25519).
If the host key changes, verify the replacement with Arch before updating it.

For a manual push after validation:

```sh
AUR_SSH_KEY_PATH="$HOME/.ssh/horizon-launcher-aur_ed25519" bash scripts/publish.sh
```

Report packaging problems in this repository. Report launcher bugs upstream.
The wrapper and automation are MIT licensed; upstream notices are in
`LICENSE.upstream` and `OFL-Geist.txt`.
