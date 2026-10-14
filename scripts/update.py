#!/usr/bin/env python3
"""Pin the newest stable launcher release, its assets, checksums and SRCINFO."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
UPSTREAM = "ludovic111/horizon"
ASSET = "horizon-launcher-linux-x86_64.tar.gz"
LOCAL_SOURCES = (
    "horizon-launcher.sh", "horizon-launcher.desktop", "horizon.desktop",
    "horizon.svg", "LICENSE.upstream", "OFL-Geist.txt", "LICENSE",
)
UPSTREAM_FILES = {
    "horizon.svg": "packaging/icons/hicolor/scalable/apps/horizon.svg",
    "LICENSE.upstream": "LICENSE",
    "OFL-Geist.txt": "crates/horizon-theme/fonts/OFL-Geist.txt",
}


def version(tag):
    match = re.fullmatch(r"launcher-v(\d+)\.(\d+)\.(\d+)", tag)
    return tuple(map(int, match.groups())) if match else None


def newest_release(releases):
    stable = [r for r in releases if version(r["tag_name"]) is not None
              and not r.get("draft") and not r.get("prerelease")]
    if not stable:
        raise ValueError("No stable launcher-vX.Y.Z release found")
    return max(stable, key=lambda r: version(r["tag_name"]))


def fetch(url):
    headers = {"User-Agent": "horizon-launcher-aur", "Accept": "application/vnd.github+json"}
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token and url.startswith("https://api.github.com/"):
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def find_release(tag=None):
    base = f"https://api.github.com/repos/{UPSTREAM}/releases"
    if tag:
        if version(tag) is None:
            raise ValueError("Use a stable tag such as launcher-v0.2.0")
        release = json.loads(fetch(f"{base}/tags/{tag}"))
        return newest_release([release])
    releases = []
    for page in range(1, 51):
        batch = json.loads(fetch(f"{base}?per_page=100&page={page}"))
        releases.extend(batch)
        if len(batch) < 100:
            return newest_release(releases)
    raise ValueError("Release catalog exceeded 50 pages; use --tag explicitly")


def checked_asset(release):
    asset = next((a for a in release["assets"] if a["name"] == ASSET), None)
    if asset is None:
        raise ValueError(f"{release['tag_name']} has no {ASSET}; publication may still be in progress")
    expected_url = f"https://github.com/{UPSTREAM}/releases/download/{release['tag_name']}/{ASSET}"
    if asset["browser_download_url"] != expected_url:
        raise ValueError("Unexpected release download URL")
    data = fetch(expected_url)
    digest = hashlib.sha256(data).hexdigest()
    published = asset.get("digest")
    if published and published != f"sha256:{digest}":
        raise ValueError("Downloaded archive differs from GitHub's published digest")
    return data, digest


def updated_pkgbuild(text, tag, checksums):
    current = re.search(r"^pkgver=(\d+\.\d+\.\d+)$", text, re.M)
    if not current:
        raise ValueError("Unsupported PKGBUILD version field")
    if version(tag) < version("launcher-v" + current[1]):
        raise ValueError("Refusing to downgrade the package")
    if tag != "launcher-v" + current[1]:
        text = re.sub(r"^pkgver=.*$", f"pkgver={tag.removeprefix('launcher-v')}", text, flags=re.M)
        text = re.sub(r"^pkgrel=.*$", "pkgrel=1", text, flags=re.M)
    sums = "sha256sums=(\n" + "".join(f"    '{s}'\n" for s in checksums) + ")"
    text, count = re.subn(r"^sha256sums=\(.*?^\)", sums, text, flags=re.M | re.S)
    if count != 1:
        raise ValueError("Expected one checksum array")
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", help="Pin a specific stable launcher tag")
    parser.add_argument("--refresh", action="store_true", help="Refresh assets/checksums at the current version")
    args = parser.parse_args()
    release = find_release(args.tag)
    tag = release["tag_name"]
    pkgbuild = ROOT / "PKGBUILD"
    old_text = pkgbuild.read_text()
    current = re.search(r"^pkgver=(.+)$", old_text, re.M)[1]
    if version(tag) < version("launcher-v" + current):
        raise ValueError("Refusing to downgrade the package")
    if tag == "launcher-v" + current and not args.refresh:
        print(f"Already tracking {tag}")
        return
    archive, digest = checked_asset(release)
    # Fetch everything before changing the package so partial publication cannot
    # leave a mixture of release versions on disk.
    resources = {name: fetch(f"https://raw.githubusercontent.com/{UPSTREAM}/{tag}/{path}")
                 for name, path in UPSTREAM_FILES.items()}
    checksums = [digest] + [hashlib.sha256(resources.get(name, (ROOT / name).read_bytes())).hexdigest()
                            for name in LOCAL_SOURCES]
    text = updated_pkgbuild(old_text, tag, checksums)
    for name, data in resources.items():
        (ROOT / name).write_bytes(data)
    pkgbuild.write_text(text)
    # Keep a verified archive locally for makepkg; it is excluded from Git.
    with tempfile.NamedTemporaryFile(dir=ROOT, delete=False) as temp:
        temp.write(archive)
        archive_temp = Path(temp.name)
    archive_temp.replace(ROOT / f"horizon-launcher-{tag.removeprefix('launcher-v')}-linux-x86_64.tar.gz")
    result = subprocess.run(["makepkg", "--printsrcinfo"], cwd=ROOT, check=True, capture_output=True, text=True)
    (ROOT / ".SRCINFO").write_text(result.stdout)
    print(f"Pinned {tag}, SHA-256 {digest}")


if __name__ == "__main__":
    main()
