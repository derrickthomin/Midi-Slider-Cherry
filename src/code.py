import time
import board
import digitalio
import analogio
import microcontroller

from controller import MidiController
from lights import LightsManager

# Slider inputs
slider_pins = [
    analogio.AnalogIn(board.A0),
    analogio.AnalogIn(board.A1),
    analogio.AnalogIn(board.A2),
    analogio.AnalogIn(board.A3),
]

# Button inputs
button_pins = [
    digitalio.DigitalInOut(board.GP0),
    digitalio.DigitalInOut(board.GP1),
    digitalio.DigitalInOut(board.GP2),
    digitalio.DigitalInOut(board.GP3),
]

for pin in button_pins:
    pin.direction = digitalio.Direction.INPUT
    pin.pull = digitalio.Pull.UP

# Initialize controller and lights
midi_controller = MidiController(slider_pins, button_pins)
lights_manager = LightsManager()
lights_manager.startup_animation()

print(f"clock freq: {microcontroller.cpu.frequency}")

# Main loop
while True:
    prev_bank_group_idx = midi_controller.current_bank_group_idx

    midi_controller.update_inputs()
    midi_controller.process_inputs()

    bank_idx = midi_controller.current_bank_idx
    bank_group_idx = midi_controller.current_bank_group_idx
    locked_bank_idx = midi_controller.locked_bank_idx
    jump_mode_enabled = midi_controller.jump_mode_enabled
    sliders = midi_controller.sliders
    buttons = midi_controller.buttons

    # Update slider lights
    lights_manager.update_slider_lights(sliders, bank_idx, bank_group_idx)

    if locked_bank_idx != -1:
        lights_manager.indicate_locked_bank(bank_group_idx, locked_bank_idx)
    else:
        force_bank_indicator = (prev_bank_group_idx != bank_group_idx)
        lights_manager.update_buttons(buttons, bank_group_idx, locked_bank_idx, force_bank_indicator)

    lights_manager.indicate_jump_mode(jump_mode_enabled)
    lights_manager.show_pixels()
    time.sleep(0.0001)