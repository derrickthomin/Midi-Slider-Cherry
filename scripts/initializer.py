import shutil
import sys
import time
import os

# ------ USER SETTINGS ------

NUKE = True  # If true, use nuke.uf2 first

NUKE_FP = "/Users/derrickthomin/Downloads/flash_nuke.uf2"
UF2_FP = "/Users/derrickthomin/📜Documents Local/📝Project Writeups/DJBB Midi Loopster SMD RGB/Code - Production/uf2 current/adafruit-circuitpython-raspberry_pi_pico-en_US-8.2.6.uf2"
SRC_FOLDER_FP = "/Users/derrickthomin/📜Documents Local/📝Project Writeups/Midi Sliders Cherry Sliders/Code - Production/src"
# ---------------------------

RPI_INIT_FP = "/Volumes/RPI-RP2"
RPI_CIRCUITPYTHON_PATHS = ["/Volumes/CIRCUITPY", "/Volumes/LUMAFADER", "/Volumes/LUMA"]
TIMEOUT_THRESHOLD = 80  # seconds

def flash_uf2():
    time_prev = time.monotonic()

    # Nuke if needed
    if NUKE: 
        try:
            shutil.copy(NUKE_FP, RPI_INIT_FP)
        except Exception as e:
            print(f"no folder named RPI-RP2 found {e}")
            return False

        print("Nuking...")

    # Copy UF2 to device
    ready_for_copy = False
    print("Waiting for RPI-RP2 to mount...")
    while not ready_for_copy:
        try:
            shutil.copy(UF2_FP, RPI_INIT_FP)
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

def copy_src_files():
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
                for root, dirs, files in os.walk(SRC_FOLDER_FP):
                    for f in files:
                        src_file = os.path.join(root, f)
                        rel_path = os.path.relpath(src_file, SRC_FOLDER_FP)
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

def main():
    while True:
        print("Ready to flash a new device. Connect the device and press Enter to start...")
        input()  # Wait for user to press Enter

        do_uf2 = input("Flash UF2? (y/N): ").strip().lower() == "y"

        if do_uf2:
            if not flash_uf2():
                print("UF2 flashing failed. Please check the device and try again.")
                continue

        if copy_src_files():
            print("Device flashed successfully. You can connect another device.")
        else:
            print("Copying src files failed. Please check the device and try again.")

if __name__ == "__main__":
    main()