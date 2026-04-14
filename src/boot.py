import storage
import board
import digitalio
import microcontroller
import supervisor

supervisor.set_usb_identification(manufacturer="DerrickThomin", product="LumaFader")
microcontroller.cpu.frequency = 270_000_000  # RP2040 Safe to 2X overclock

storage.remount("/", readonly=False)

m = storage.getmount("/")
m.label = "LUMAFADER"

# Set up all 4 buttons
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

# All buttons pressed = all values are False (LOW due to pull-up)
all_pressed = not btn0.value and not btn1.value and not btn2.value and not btn3.value

# readonly=True when buttons pressed (all_pressed=True becomes readonly=True? No, we want opposite)
# When all_pressed is True, we want USB drive ON and readonly=True
# When all_pressed is False, we want USB drive OFF and readonly=False
storage.remount("/", readonly=all_pressed)

if all_pressed:
    storage.enable_usb_drive()
else:
    storage.disable_usb_drive()