#!/usr/bin/env python3
"""Build and publish a LumaFader release.

Releases are immutable. Each publish picks a version, commits the bump to
src/version.txt, tags that commit, and builds the firmware zip straight from
the tagged commit via `git archive`. Building from the tag (not the working
tree) guarantees a release can never contain uncommitted local edits, so the
version on a flashed device always maps back to an exact commit.

Each release carries three assets so the initializer can flash a clean device
entirely from it: the firmware zip plus the two UF2 files.

Usage:
    python scripts/release.py            # pick a version and publish a new release
    python scripts/release.py --dry-run  # walk the whole flow, mutate nothing
    python scripts/release.py --clobber  # re-publish assets to an existing tag
"""

import os
import re
import shutil
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
SRC_DIR = os.path.join(REPO_ROOT, "src")
VERSION_FILE = os.path.join(SRC_DIR, "version.txt")
UF2_DIR = os.path.join(REPO_ROOT, "uf2 current")
RELEASES_DIR = os.path.join(SCRIPT_DIR, "releases")

GH_REPO = "derrickthomin/Midi-Slider-Cherry"

# UF2 assets bundled into every release (sourced from uf2 current/).
UF2_ASSETS = [
    "flash_nuke.uf2",
    "adafruit-circuitpython-raspberry_pi_pico-en_US-8.2.6.uf2",
]

VERSION_RE = re.compile(r"^\d+(\.\d+)+$")


# ------ shell helpers ------

def run(args, capture=False, check=True):
    """Run a command in the repo root."""
    return subprocess.run(
        args,
        cwd=REPO_ROOT,
        check=check,
        text=True,
        capture_output=capture,
    )


def git_out(args):
    """Return stripped stdout of a git command."""
    return run(["git", *args], capture=True).stdout.strip()


def mutate(args, dry_run, capture=False):
    """Run a state-changing command, or just print it under --dry-run."""
    print("  $ " + " ".join(args))
    if dry_run:
        return None
    return run(args, capture=capture)


# ------ prerequisites ------

def fail(msg):
    print("ERROR: " + msg)
    sys.exit(1)


def ensure_prereqs():
    if run(["git", "rev-parse", "--is-inside-work-tree"], capture=True, check=False).returncode != 0:
        fail(f"{REPO_ROOT} is not a git repository.")
    if shutil.which("gh") is None:
        fail("GitHub CLI (gh) not found on PATH.")
    if run(["gh", "auth", "status"], capture=True, check=False).returncode != 0:
        fail("gh is not authenticated. Run `gh auth login`.")
    if not os.path.isdir(SRC_DIR):
        fail(f"src directory not found: {SRC_DIR}")
    for name in UF2_ASSETS:
        if not os.path.isfile(os.path.join(UF2_DIR, name)):
            fail(f"Missing UF2 asset: {os.path.join(UF2_DIR, name)}")


def confirm(prompt):
    return input(prompt + " (y/N): ").strip().lower() == "y"


def check_tree_clean():
    """Warn if uncommitted changes exist, since releases ship committed code only."""
    dirty = [
        line for line in git_out(["status", "--porcelain"]).splitlines()
        # the version.txt bump is made by this script, so ignore it here
        if line[3:].strip() != "src/version.txt"
    ]
    if not dirty:
        return
    print("\nYou have uncommitted changes:")
    for line in dirty:
        print("  " + line)
    print("Releases are built from committed code only, so these will NOT be included.")
    if not confirm("Continue and release only committed code?"):
        fail("Aborted. Commit or stash your changes first.")


# ------ versioning ------

def read_version():
    try:
        with open(VERSION_FILE) as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def latest_tag():
    out = git_out(["tag", "--sort=-v:refname"])
    return out.splitlines()[0] if out else ""


def suggest_next(ref):
    """Suggest the next patch version from a tag/version string like v1.3 or 1.3.1."""
    base = ref.lstrip("vV") if ref else "0.0.0"
    parts = base.split(".")
    if len(parts) < 3:
        parts = parts + ["0"] * (3 - len(parts))
        parts[2] = "1"  # 1.3 -> 1.3.1
    else:
        parts[-1] = str(int(parts[-1]) + 1)  # 1.3.1 -> 1.3.2
    return ".".join(parts)


def tag_exists(tag):
    return run(["git", "rev-parse", "--verify", "--quiet", tag],
               capture=True, check=False).returncode == 0


def prompt_version(current, latest, suggested):
    print(f"\nCurrent src/version.txt: {current or '(empty)'}")
    print(f"Latest git tag:          {latest or '(none)'}")
    entered = input(f"Version to release [{suggested}]: ").strip()
    version = (entered or suggested).lstrip("vV")
    if not VERSION_RE.match(version):
        fail(f"Invalid version '{version}'. Use digits and dots, e.g. 1.3.1")
    return version


# ------ build & publish ------

def build_zip(treeish, tag, out_dir):
    """Build LumaFader-<tag>.zip from <treeish>:src via git archive."""
    os.makedirs(out_dir, exist_ok=True)
    zip_path = os.path.join(out_dir, f"LumaFader-{tag}.zip")
    run(["git", "archive", "--format=zip", "-o", zip_path, f"{treeish}:src"])
    return zip_path


def copy_uf2s(out_dir):
    paths = []
    for name in UF2_ASSETS:
        dst = os.path.join(out_dir, name)
        shutil.copy2(os.path.join(UF2_DIR, name), dst)
        paths.append(dst)
    return paths


def release_exists(tag):
    return run(["gh", "release", "view", tag, "--repo", GH_REPO],
               capture=True, check=False).returncode == 0


def publish(tag, assets, dry_run):
    if release_exists(tag):
        print(f"\nRelease {tag} exists; re-uploading assets with --clobber.")
        mutate(["gh", "release", "upload", tag, *assets, "--clobber",
                "--repo", GH_REPO], dry_run)
    else:
        print(f"\nCreating GitHub release {tag}.")
        mutate(["gh", "release", "create", tag, *assets, "--repo", GH_REPO,
                "--title", f"LumaFader {tag}", "--generate-notes"], dry_run)


def main():
    dry_run = "--dry-run" in sys.argv
    clobber = "--clobber" in sys.argv

    ensure_prereqs()
    if dry_run:
        print("=== DRY RUN: no commits, tags, pushes, or releases will be made ===")

    check_tree_clean()

    current = read_version()
    latest = latest_tag()
    version = prompt_version(current, latest, suggest_next(latest or current))
    tag = "v" + version

    exists = tag_exists(tag)
    if exists and not clobber:
        fail(f"Tag {tag} already exists. Releases are immutable; pick a new "
             f"version, or pass --clobber to re-publish assets to {tag}.")

    if exists:
        # Re-publishing an existing tag: don't move the tag or bump the version.
        print(f"\n--clobber: re-publishing existing tag {tag} (no version bump).")
        if not confirm(f"Overwrite the release assets on {tag}?"):
            fail("Aborted.")
        treeish = tag
    else:
        # New release: bump version.txt, commit, tag, push.
        print(f"\nReleasing {tag}.")
        if not dry_run:
            with open(VERSION_FILE, "w") as f:
                f.write(version + "\n")
        else:
            print(f"  (would write {version} to src/version.txt)")
        if git_out(["status", "--porcelain", "src/version.txt"]) or dry_run:
            mutate(["git", "add", "src/version.txt"], dry_run)
            mutate(["git", "commit", "-m", f"Release {tag}"], dry_run)
        mutate(["git", "tag", tag], dry_run)
        mutate(["git", "push", "origin", "HEAD"], dry_run)
        mutate(["git", "push", "origin", tag], dry_run)
        # Under --dry-run the tag isn't created, so preview the zip from HEAD.
        treeish = "HEAD" if dry_run else tag

    out_dir = os.path.join(RELEASES_DIR, tag)
    print(f"\nBuilding release assets in {out_dir}")
    zip_path = build_zip(treeish, tag, out_dir)
    assets = [zip_path] + copy_uf2s(out_dir)
    for a in assets:
        print(f"  {os.path.basename(a)} ({os.path.getsize(a)} bytes)")

    publish(tag, assets, dry_run)

    print(f"\nDone. {tag} "
          + ("previewed (dry run)." if dry_run
             else f"published: https://github.com/{GH_REPO}/releases/tag/{tag}"))


if __name__ == "__main__":
    main()
