import shutil
import subprocess
import sys
import time
import os
import zipfile

# ------ USER SETTINGS (dev flashes) ------

NUKE = True  # If true, use nuke.uf2 first

NUKE_FP = "/Users/derrickthomin/Downloads/flash_nuke.uf2"
UF2_FP = "/Users/derrickthomin/📜Documents Local/📝Project Writeups/DJBB Midi Loopster SMD RGB/Code - Production/uf2 current/adafruit-circuitpython-raspberry_pi_pico-en_US-8.2.6.uf2"
SRC_FOLDER_FP = "/Users/derrickthomin/📜Documents Local/📝Project Writeups/Midi Sliders Cherry Sliders/Code - Production/src"
# -----------------------------------------

# Customer flashes pull an immutable release from GitHub instead of local src.
GH_REPO = "derrickthomin/Midi-Slider-Cherry"
RELEASES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "releases")

RPI_INIT_FP = "/Volumes/RPI-RP2"
RPI_CIRCUITPYTHON_PATHS = ["/Volumes/CIRCUITPY", "/Volumes/LUMAFADER", "/Volumes/LUMA"]
TIMEOUT_THRESHOLD = 80  # seconds

def flash_uf2(nuke_fp, uf2_fp, nuke=True):
    time_prev = time.monotonic()

    # Nuke if needed
    if nuke:
        try:
            shutil.copy(nuke_fp, RPI_INIT_FP)
        except Exception as e:
            print(f"no folder named RPI-RP2 found {e}")
            return False

        print("Nuking...")

    # Copy UF2 to device
    ready_for_copy = False
    print("Waiting for RPI-RP2 to mount...")
    while not ready_for_copy:
        try:
            shutil.copy(uf2_fp, RPI_INIT_FP)
            ready_for_copy = True
            print("copied uf2 to RPI-RP2")
            time_prev = time.monotonic()
        except:
            print("Retrying in 2s...")
            time.sleep(2)

        if time.monotonic() - time_prev > TIMEOUT_THRESHOLD:
            print("Timeout")
            return False

    time.sleep(10)
    return True

def find_circuitpy_path():
    for path in RPI_CIRCUITPYTHON_PATHS:
        if os.path.exists(path):
            return path
    return None

def copy_src_files(src_folder):
    # Copy src files to CIRCUITPY or LUMAFADER
    success = False
    print("Waiting for device volume to mount...")
    print(f"  Looking for: {RPI_CIRCUITPYTHON_PATHS}")
    print(f"  Current volumes: {os.listdir('/Volumes/')}")
    time_prev = time.monotonic()
    while not success:
        try:
            target = find_circuitpy_path()
            print(f"  find_circuitpy_path() returned: {target}")
            if target:
                print(f"  Copying files to {target}...")
                count = 0
                for root, dirs, files in os.walk(src_folder):
                    dirs[:] = [d for d in dirs if d != '__pycache__']
                    for f in files:
                        if f == '__pycache__':
                            continue
                        src_file = os.path.join(root, f)
                        rel_path = os.path.relpath(src_file, src_folder)
                        dst_file = os.path.join(target, rel_path)
                        os.makedirs(os.path.dirname(dst_file), exist_ok=True)
                        shutil.copy2(src_file, dst_file)
                        count += 1
                        print(f"    [{count}] {rel_path}")
                success = True
                print(f"Done! Copied {count} files to {target}")
                time_prev = time.monotonic()
            else:
                raise FileNotFoundError("No matching volume found")
        except Exception as e:
            print(f"Retrying in 2s... ({e})")
            time.sleep(2)

        if time.monotonic() - time_prev > TIMEOUT_THRESHOLD * 2:
            print("Timeout")
            return False

    return True

def get_latest_release_tag():
    result = subprocess.run(
        ["gh", "release", "view", "--repo", GH_REPO, "--json", "tagName", "-q", ".tagName"],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def ensure_release_cached(tag):
    """Download a release's assets to RELEASES_DIR/<tag> if not already cached.

    Releases are immutable, so a cached copy is always correct and we can skip
    the download (and work offline) once a version has been fetched.
    """
    dest = os.path.join(RELEASES_DIR, tag)
    os.makedirs(dest, exist_ok=True)
    zip_path = os.path.join(dest, f"LumaFader-{tag}.zip")
    if os.path.isfile(zip_path):
        print(f"Using cached release at {dest}")
    else:
        print(f"Downloading release {tag} from GitHub...")
        subprocess.run(
            ["gh", "release", "download", tag, "--repo", GH_REPO, "--dir", dest, "--clobber"],
            check=True,
        )
    return dest


def find_release_assets(dest, tag):
    """Locate the firmware zip and both UF2s in a cached release dir.

    The CircuitPython UF2 is matched as the .uf2 that isn't the nuke file, so a
    future CircuitPython version bump won't break this.
    """
    zip_path = os.path.join(dest, f"LumaFader-{tag}.zip")
    uf2s = [f for f in os.listdir(dest) if f.lower().endswith(".uf2")]
    nuke = next((f for f in uf2s if "nuke" in f.lower()), None)
    cpy = next((f for f in uf2s if "nuke" not in f.lower()), None)
    nuke_fp = os.path.join(dest, nuke) if nuke else None
    cpy_fp = os.path.join(dest, cpy) if cpy else None
    return zip_path, nuke_fp, cpy_fp


def extract_release_src(dest, zip_path):
    """Extract the firmware zip to a clean src/ folder under the cache dir."""
    src_dir = os.path.join(dest, "src")
    if os.path.exists(src_dir):
        shutil.rmtree(src_dir)
    os.makedirs(src_dir)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(src_dir)
    return src_dir


def flash_customer():
    """Flash a clean device entirely from the latest immutable GitHub release."""
    try:
        tag = get_latest_release_tag()
    except Exception as e:
        print(f"Could not reach GitHub to find the latest release: {e}")
        return False

    print(f"Latest release: {tag}")
    dest = ensure_release_cached(tag)
    zip_path, nuke_fp, cpy_fp = find_release_assets(dest, tag)
    if not (os.path.isfile(zip_path) and nuke_fp and cpy_fp):
        print(f"Release {tag} is missing expected assets (zip + 2 UF2s).")
        return False

    src_dir = extract_release_src(dest, zip_path)
    print(f"Flashing customer device with release {tag} (full clean flash)...")
    if not flash_uf2(nuke_fp, cpy_fp, nuke=True):
        return False
    return copy_src_files(src_dir)


def main():
    while True:
        print("Ready to flash a new device. Connect the device and press Enter to start...")
        input()  # Wait for user to press Enter

        customer = input("Flashing to customer device? (y/N): ").strip().lower() == "y"

        if customer:
            # Customer flash: always a full clean flash from the latest release.
            if flash_customer():
                print("Device flashed successfully. You can connect another device.")
            else:
                print("Customer flash failed. Please check the device and try again.")
            continue

        # Dev flash: load local src, optionally re-flash the UF2 first.
        do_uf2 = input("Flash UF2? (y/N): ").strip().lower() == "y"

        if do_uf2:
            if not flash_uf2(NUKE_FP, UF2_FP, nuke=NUKE):
                print("UF2 flashing failed. Please check the device and try again.")
                continue

        if copy_src_files(SRC_FOLDER_FP):
            print("Device flashed successfully. You can connect another device.")
        else:
            print("Copying src files failed. Please check the device and try again.")

if __name__ == "__main__":
    main()