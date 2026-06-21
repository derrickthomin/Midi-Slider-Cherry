import storage
import board
import digitalio
import microcontroller
import supervisor

supervisor.set_usb_identification(manufacturer="DerrickThomin", product="LumaFader")
microcontroller.cpu.frequency = 270_000_000  # RP2040 Safe to 2X overclock

# Remount writable first so we can set the volume label below.
storage.remount("/", readonly=False)

m = storage.getmount("/")
m.label = "LUMAFADER"

btn0 = digitalio.DigitalInOut(board.GP0)
btn0.direction = digitalio.Direction.INPUT
btn0.pull = digitalio.Pull.UP

btn1 = digitalio.DigitalInOut(board.GP1)
btn1.direction = digitalio.Direction.INPUT
btn1.pull = digitalio.Pull.UP

btn2 = digitalio.DigitalInOut(board.GP2)
btn2.direction = digitalio.Direction.INPUT
btn2.pull = digitalio.Pull.UP

btn3 = digitalio.DigitalInOut(board.GP3)
btn3.direction = digitalio.Direction.INPUT
btn3.pull = digitalio.Pull.UP

# With pull-ups, a pressed button reads LOW (value = False)
all_pressed = not btn0.value and not btn1.value and not btn2.value and not btn3.value

# Hold all 4 buttons at boot to expose the USB drive for editing files.
# Held: device is read-only, USB drive visible to host.
# Not held: device has write access, USB drive hidden (normal operation).
storage.remount("/", readonly=all_pressed)

if all_pressed:
    storage.enable_usb_drive()
else:
    storage.disable_usb_drive()