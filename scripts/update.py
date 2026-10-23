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
from urllib.parse import quote
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
    match = re.fullmatch(r"launcher(?:-v|@)(\d+)\.(\d+)\.(\d+)", tag)
    return tuple(map(int, match.groups())) if match else None


def release_key(tag):
    parsed = version(tag)
    if parsed is None:
        raise ValueError("Use a stable tag such as launcher@0.2.1 or launcher-v0.17.0")
    # Upstream reset 0.17.0 to 0.2.0 when switching to launcher@ tags.
    return (1 if tag.startswith("launcher@") else 0, parsed)


def package_key(text):
    current = re.search(r"^pkgver=(\d+\.\d+\.\d+)$", text, re.M)
    if not current:
        raise ValueError("Unsupported PKGBUILD version field")
    epoch = re.search(r"^epoch=(\d+)$", text, re.M)
    return (int(epoch[1]) if epoch else 0, tuple(map(int, current[1].split("."))))


def is_newer(text, tag):
    incoming, current = release_key(tag), package_key(text)
    if incoming < current:
        raise ValueError("Refusing to downgrade the package")
    return incoming > current


def newest_release(releases):
    stable = [r for r in releases if version(r["tag_name"]) is not None
              and not r.get("draft") and not r.get("prerelease")]
    if not stable:
        raise ValueError("No stable launcher@X.Y.Z or launcher-vX.Y.Z release found")
    return max(stable, key=lambda r: release_key(r["tag_name"]))


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
        release_key(tag)
        release = json.loads(fetch(f"{base}/tags/{quote(tag, safe='')}"))
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
    expected_url = f"https://github.com/{UPSTREAM}/releases/download/{quote(release['tag_name'], safe='')}/{ASSET}"
    if asset["browser_download_url"] != expected_url:
        raise ValueError("Unexpected release download URL")
    data = fetch(expected_url)
    digest = hashlib.sha256(data).hexdigest()
    published = asset.get("digest")
    if published and published != f"sha256:{digest}":
        raise ValueError("Downloaded archive differs from GitHub's published digest")
    return data, digest


def updated_pkgbuild(text, tag, checksums):
    if is_newer(text, tag):
        text = re.sub(r"^pkgver=.*$", f"pkgver={'.'.join(map(str, version(tag)))}", text, flags=re.M)
        text = re.sub(r"^pkgrel=.*$", "pkgrel=1", text, flags=re.M)
    if release_key(tag)[0] == 1:
        if re.search(r"^epoch=", text, re.M):
            text = re.sub(r"^epoch=.*$", "epoch=1", text, flags=re.M)
        else:
            text = re.sub(r"^pkgver=", "epoch=1\npkgver=", text, flags=re.M)
    if re.search(r"^_tag=", text, re.M):
        text = re.sub(r"^_tag=.*$", f"_tag={tag}", text, flags=re.M)
    else:
        text = re.sub(r"^(pkgrel=.*)$", rf"\1\n_tag={tag}", text, flags=re.M)
    text = text.replace("releases/download/launcher-v${pkgver}/", "releases/download/${_tag}/")
    sums = "sha256sums=(\n" + "".join(f"    '{s}'\n" for s in checksums) + ")"
    text, count = re.subn(r"^sha256sums=\(.*?^\)", sums, text, flags=re.M | re.S)
    if count != 1:
        raise ValueError("Expected one checksum array")
    return text


def release_status(text, release):
    tag = release["tag_name"]
    newer = is_newer(text, tag)
    ready = any(asset["name"] == ASSET for asset in release.get("assets", []))
    return {
        "current": ".".join(map(str, package_key(text)[1])),
        "tag": tag,
        "changed": newer and ready,
        "status": "update-available" if newer and ready else
                  "waiting-for-linux-asset" if newer else "up-to-date",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", help="Pin a specific stable launcher tag")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--refresh", action="store_true", help="Refresh assets/checksums at the current version")
    mode.add_argument("--check", action="store_true", help="Check release metadata without downloading or modifying the package")
    args = parser.parse_args()
    release = find_release(args.tag)
    tag = release["tag_name"]
    pkgbuild = ROOT / "PKGBUILD"
    old_text = pkgbuild.read_text()
    if args.check:
        status = release_status(old_text, release)
        print(json.dumps(status, sort_keys=True))
        if output := os.environ.get("GITHUB_OUTPUT"):
            with open(output, "a") as stream:
                stream.write(f"changed={str(status['changed']).lower()}\ntag={tag}\n")
        return
    if not is_newer(old_text, tag) and not args.refresh:
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
    archive_version = ".".join(map(str, version(tag)))
    archive_temp.replace(ROOT / f"horizon-launcher-{archive_version}-linux-x86_64.tar.gz")
    result = subprocess.run(["makepkg", "--printsrcinfo"], cwd=ROOT, check=True, capture_output=True, text=True)
    (ROOT / ".SRCINFO").write_text(result.stdout)
    print(f"Pinned {tag}, SHA-256 {digest}")


if __name__ == "__main__":
    main()
