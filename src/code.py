# Version 1.20

import time
import board
import digitalio
import analogio

from controller import MidiController
from lights import LightsManager
from midi import midi_manager
from serial_config import serial_config

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

# Initialize serial config handler
serial_config.set_controller(midi_controller)
serial_config.set_midi_manager(midi_manager)

# Main loop
while True:
    midi_controller.update_inputs()
    midi_controller.process_inputs()
    serial_config.update()

    bank_idx = midi_controller.current_bank_idx
    page_idx = midi_controller.current_page_idx
    locked_bank_idx = midi_controller.locked_bank_idx
    jump_mode_enabled = midi_controller.jump_mode_enabled
    sliders = midi_controller.sliders
    buttons = midi_controller.buttons
    held_button_order = midi_controller.held_button_order
    page_just_changed = midi_controller.page_just_changed
    page_change_feedback = midi_controller.update_page_change_feedback()

    # Update slider lights
    lights_manager.update_slider_lights(sliders, bank_idx, page_idx, held_button_order, page_just_changed)

    if locked_bank_idx != -1:
        lights_manager.indicate_locked_bank(page_idx, locked_bank_idx)
    else:
        lights_manager.update_buttons(buttons, page_idx, locked_bank_idx, page_just_changed, page_change_feedback)

    lights_manager.indicate_jump_mode(jump_mode_enabled)
    lights_manager.show_pixels()
    time.sleep(0.0001)