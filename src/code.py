import adafruit_ticks as ticks
from settings import settings
import inputs 
import constants
from looper import setup_midi_loops, MidiLoop
from chordmanager import chord_manager
from menus import Menu
from debug import debug, print_debug
from playmenu import get_midi_note_name_text
from clock import clock
from midi import setup_midi, send_midi_note_on, send_midi_note_off, get_midi_messages_in, process_cc_message
from display import (
    check_show_display,pixels_process_blinks,
    pixel_set_note_on,pixel_set_note_off,
    pixel_set_encoder_button_on, pixel_set_encoder_button_off,
    clear_pixels,display_startup_screen,
)
import useraddons
from utils import free_memory

clear_pixels()
setup_midi()
setup_midi_loops()
display_startup_screen()
Menu.initialize()

# Timing
polling_time_prev = ticks.ticks_ms()
if debug.DEBUG_MODE:
    debug_time_prev = ticks.ticks_ms()

cc_event_count = 0
def process_midi_messages(midi_messages): # ((note on), (note off), (cc))
    global cc_event_count
    for idx, msg in enumerate(midi_messages):
        # print (f"idx: {idx} msg: {msg}")
        # print("message bool: ", bool(msg))
        # print("message length: ", len(msg))
        if not msg or len(msg) < 2:
            continue

        if idx < 2:
            note_val, velocity, padidx = msg
            print_debug(f"MIDI IN: {get_midi_note_name_text(note_val)} ({note_val}) vel: {velocity} padidx: {padidx}")
            if idx == 0:  # ON
                pixel_set_encoder_button_on()
                record_midi_event(note_val, velocity, padidx, True,"all")
            else:  # OFF
                pixel_set_encoder_button_off()
                record_midi_event(note_val, velocity, padidx, False,"all")
        if idx == 2:
            cc_num, cc_val = msg
            padidx = 0
            print_debug(f"MIDI IN: CC {cc_num} val: {cc_val} padidx: {padidx}")
            # DJT - add flag for CC on or off
            record_midi_event(cc_num, cc_val, padidx, True,"all", type="cc")
            cc_event_count += 1 #djt - remove all of these
            free_memory()
            print("CC EVENT COUNT: ", cc_event_count)

def record_midi_event(note_val, velocity, padidx, is_on, record, type="note"):
    if MidiLoop.current_loop.is_recording and record in ["loop", "all"]:
        if type == "note":
            MidiLoop.current_loop.add_loop_note(note_val, velocity, padidx, is_on) # record note
        else:
            MidiLoop.current_loop.add_loop_cc(note_val, velocity, padidx)          # record CC
    if chord_manager.is_recording and record in ["chord", "all"]:
        if type == "note":
            chord_manager.pad_chords[chord_manager.recording_pad_idx].add_loop_note(note_val, velocity, padidx, is_on)
        else:
            chord_manager.pad_chords[chord_manager.recording_pad_idx].add_loop_cc(note_val, velocity, padidx)

def process_notes(notes, is_on, record="all"): # record = "loop", "chord", "all", False
    for note in notes:
        note_val, velocity, padidx = note
        if is_on:
            print_debug(f"NOTE ON: {get_midi_note_name_text(note_val)} ({note_val}) vel: {velocity}")
            send_midi_note_on(note_val, velocity)
            pixel_set_note_on(padidx, velocity)
        else:
            print_debug(f"NOTE OFF: {get_midi_note_name_text(note_val)} ({note_val}) vel: {velocity}")
            send_midi_note_off(note_val)
            pixel_set_note_off(padidx)
            useraddons.handle_new_notes_off(note_val, velocity, padidx)
        if record:
            record_midi_event(note_val, velocity, padidx, is_on, record)

def process_cc_messages(cc_messages, record="loop"):
    for cc in cc_messages:
        cc_num, cc_val, padidx = cc
        # djt - logic here to only send cc if it's different from the last one

        process_cc_message(cc_num, cc_val)
        print("-------- JUST SENT CC MESSAGE ---------")
        # if record:
        #     record_midi_event(cc_num, cc_val, padidx, True, record)
# -------------------- Main loop --------------------
while True:
    # Slower input processing
    timenow = ticks.ticks_ms()
    if ticks.ticks_diff(timenow, polling_time_prev) > constants.NAV_BUTTONS_POLL_S * 1000:  # Convert seconds to milliseconds
        inputs.process_inputs_slow()
        check_show_display()
        Menu.display_clear_notifications()
        pixels_process_blinks()
        debug.check_display_debug()
        polling_time_prev = timenow
        useraddons.check_addons_slow()

    # Fast input processing
    inputs.process_inputs_fast()

    # ------------------ New Notes / Midi IN ------------------

    # Send MIDI notes off
    process_notes(inputs.new_notes_off, is_on=False)

    # Record MIDI In to loops and chords
    midi_messages = get_midi_messages_in()
    if (MidiLoop.current_loop.is_recording or chord_manager.is_recording) and midi_messages:
        process_midi_messages(midi_messages)

    # Send MIDI notes on
    process_notes(inputs.new_notes_on, is_on=True)


    # ------------------ MIDI Loop and Chord Mode ------------------

    # Loop Notes
    if MidiLoop.current_loop.loop_is_playing:
        new_notes = MidiLoop.current_loop.get_new_notes()
        if new_notes:
            loop_notes_on, loop_notes_off, cc_messages = new_notes
            process_notes(loop_notes_on, is_on=True, record=False)
            process_notes(loop_notes_off, is_on=False, record=False)
            process_cc_messages(cc_messages, record=False)

    # Chord Mode Notes
    if settings.midi_sync:
        if clock.is_playing:
            chord_manager.process_chord_on_queue()
        else:
            chord_manager.stop_all_chords()

    for chord in chord_manager.pad_chords:
        if chord == "":
            continue
        new_notes = chord.get_new_notes()  # chord is a loop object
        if new_notes:
            loop_notes_on, loop_notes_off, cc_messages = new_notes
            process_notes(loop_notes_on, is_on=True, record="loop")
            process_notes(loop_notes_off, is_on=False, record="loop")
            process_cc_messages(cc_messages, record="loop")