import storage
import board
import digitalio
import time
import microcontroller

# Overclock the CPU to 120 MHz
microcontroller.cpu.frequency = 270_000_000

# Check if all buttons are pressed during boot
def check_all_buttons_pressed():
    # Define the button pins
    button_pins = [
        board.GP0,
        board.GP1,
        board.GP2,
        board.GP3,
    ]

    # Initialize all buttons
    buttons = []
    for pin in button_pins:
        button = digitalio.DigitalInOut(pin)
        button.direction = digitalio.Direction.INPUT
        button.pull = digitalio.Pull.UP
        buttons.append(button)
    
    # Wait a moment for things to settle
    time.sleep(0.1)
    
    # Check if all buttons are pressed (LOW because of pull-up resistors)
    all_pressed = all(not button.value for button in buttons)
    
    # De-initialize all buttons to not interfere with main program
    for button in buttons:
        button.deinit()
    
    return all_pressed

# Set the filesystem to read-only if all buttons are pressed
storage.remount("/", readonly=check_all_buttons_pressed())

# Print a message to the console for debugging
if storage.getmount("/").readonly:
    print("Filesystem is READ-ONLY mode! (All buttons were held during boot)")
else:
    print("Filesystem is in READ-WRITE mode (Normal operation)")