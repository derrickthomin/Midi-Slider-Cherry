# Version 1.3

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
    midi_controller.process_inputs()  # also runs the Record Mode timers + playback pump
    serial_config.update()

    # Record Mode enter/exit confirmation animation (brief, blocking)
    if midi_controller.record_mode_just_toggled:
        midi_controller.record_mode_just_toggled = False
        lights_manager.record_mode_toggle_animation(midi_controller.record_mode_active)

    jump_mode_enabled = midi_controller.jump_mode_enabled
    sliders = midi_controller.sliders
    buttons = midi_controller.buttons

    if midi_controller.mapping_mode_active:
        # Mapping Mode owns the whole strip (the normal update_slider_lights /
        # update_buttons / indicate_locked_bank calls would overwrite it every
        # frame, gotcha 8.3)
        lights_manager.update_mapping_mode(
            midi_controller.mapping_target_slider,
            midi_controller.mapping_confirm_slider,
            midi_controller.mapping_confirm_slider != -1,
            midi_controller.mapping_save_failed,
            midi_controller.mapping_bank_button_idx,
            midi_controller.mapping_bank_page_idx,
        )
    elif midi_controller.record_mode_active:
        # Record Mode owns the button pixels (the normal update_buttons /
        # indicate_locked_bank calls would overwrite them every frame)
        lights_manager.update_slider_lights(
            sliders, midi_controller.record_display_bank_idx,
            midi_controller.record_display_page_idx)
        lights_manager.update_record_mode_buttons(
            midi_controller.get_record_slot_states(),
            midi_controller.get_set_flash(),
            midi_controller.get_reject_blink())
    else:
        bank_idx = midi_controller.current_bank_idx
        page_idx = midi_controller.current_page_idx
        locked_bank_idx = midi_controller.locked_bank_idx
        held_button_order = midi_controller.held_button_order
        page_just_changed = midi_controller.page_just_changed
        page_change_feedback = midi_controller.update_page_change_feedback()

        # Update slider lights
        lights_manager.update_slider_lights(sliders, bank_idx, page_idx, held_button_order, page_just_changed)

        if locked_bank_idx != -1:
            lights_manager.indicate_locked_bank(page_idx, locked_bank_idx)
        else:
            lights_manager.update_buttons(buttons, page_idx, locked_bank_idx, page_just_changed, page_change_feedback)

    # Hold-all-four-buttons Record Mode toggle progress (red fill, both modes)
    hold_pixels_lit = midi_controller.mode_hold_pixels_lit
    if hold_pixels_lit > 0:
        lights_manager.update_mode_hold_progress(hold_pixels_lit)

    # Mapping Mode draws pixel 68 itself (the blue blink, §2j) - don't let
    # the normal jump-mode indicator overwrite it every frame.
    if not midi_controller.mapping_mode_active:
        lights_manager.indicate_jump_mode(jump_mode_enabled)
    lights_manager.show_pixels()
    time.sleep(0.0001)