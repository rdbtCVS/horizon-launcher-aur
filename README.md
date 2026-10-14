# Horizon launcher for Arch Linux

Community-maintained AUR packaging by **rdbt**, using the official Linux x86_64
launcher releases from [ludovic111/horizon](https://github.com/ludovic111/horizon).
This repository contains the package recipe and automation, not the launcher
source or binaries. Upstream does not maintain this package.

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

Launch **Horizon** from the applications menu, or run `horizon-launcher`.
The same command provides the CLI and MCP server (`horizon-launcher mcp`).

You need a working Vulkan driver. Preparing game resources needs your own
Minecraft: Java Edition installation and a **Java 25 JDK** (`jdk25-openjdk`).
Older Horizon versions may also need Python. A Secret Service provider such as
GNOME Keyring or KWallet enables persistent Microsoft sign-in; otherwise the
launcher can retain a session only while it runs. No Minecraft assets are packaged.

## Package integration

The executable is installed under `/usr/lib/horizon-launcher/`. The command in
`/usr/bin` sets `HORIZON_LAUNCHER_NO_SELF_UPDATE=1`, so update the launcher through
your AUR helper. Horizon game downloads and updates still happen in the launcher,
normally under `~/.local/share/horizon-launcher`.

The package owns the system desktop entries and icon. On GUI startup, the wrapper
uses upstream's `desktop-entry --remove` command to disable its separate per-user
menu registration. This preserves other launcher settings and prevents a user
entry from bypassing the wrapper. The launcher's “applications menu” setting
therefore does not control the package's system menu entry. Use `horizon-launcher`
rather than invoking the private executable directly.

## Maintain

```sh
python scripts/update.py                  # newest stable launcher-vX.Y.Z
python scripts/update.py --refresh        # refresh current release and local checksums
bash scripts/validate.sh                 # requires namcap and desktop-file-utils
```

The updater excludes game tags, drafts and prereleases, handles pagination,
compares the downloaded archive with GitHub's published digest when available,
and pins every source with SHA-256. It updates the upstream MIT licence, Geist
font licence, icon and `.SRCINFO`. When changing packaging at the same launcher
version, increment `pkgrel`, then run `--refresh` before committing.

GitHub Actions checks upstream every six hours and on manual dispatch. An update
must build in a clean Arch container, pass updater tests, validate its desktop
entries and metadata, and pass offline CLI smoke checks before it is committed
and published. Namcap diagnostics are printed for review. Pull requests run
validation with read-only permissions and no AUR credentials.

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
