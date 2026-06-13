"""
LumaFader - Loop Manager (Record Mode)
=======================================
Ported from the DJBB Midi Loopster 2 loopmanager.py and resized to the
LumaFader's 4 buttons = 4 loop slots. No display, no MIDI sync, no
persistence; all LED feedback is owned by the controller / LightsManager
via get_slot_state().
"""

import gc

import constants as cfg
from looper import MidiLoop, ticks_ms, ticks_diff
from settings import settings

# Slot states (consumed by the controller and LightsManager)
SLOT_EMPTY = "empty"
SLOT_RECORDING = "recording"
SLOT_PLAYING = "playing"
SLOT_STOPPED = "stopped"

NUM_SLOTS = 4


class LoopManager:
    """Manages the 4 loop slots: recording orchestration and play/stop state."""

    def __init__(self):
        self.loops = [None] * NUM_SLOTS
        self.recording_slot = -1
        self.is_recording = False

    # ==================== Queries ====================

    def slot_has_loop(self, slot_idx):
        return self.loops[slot_idx] is not None

    def get_recording_loop(self):
        if self.recording_slot == -1:
            return None
        return self.loops[self.recording_slot]

    def get_slot_state(self, slot_idx):
        loop = self.loops[slot_idx]
        if loop is None:
            return SLOT_EMPTY
        if loop.is_recording:
            return SLOT_RECORDING
        if loop.loop_is_playing:
            return SLOT_PLAYING
        return SLOT_STOPPED

    # ==================== Recording ====================

    def start_recording(self, slot_idx, cc_set_idx=0):
        """Start recording on an empty slot. If a recording is already running
        on another slot, finalize it first (keep it if it has events, silently
        remove it if empty). Returns True if recording started."""
        if self.loops[slot_idx] is not None:
            return False

        if self.is_recording:
            self.stop_recording()

        gc.collect()
        loop = MidiLoop(loop_type=settings.get_loop_type(), cc_set_idx=cc_set_idx)
        self.loops[slot_idx] = loop
        self.recording_slot = slot_idx
        self.is_recording = True
        loop.toggle_record_state(True)
        return True

    def stop_recording(self):
        """Finalize the current recording (manual stop, switch, cap hit, or
        Record-Mode exit). Empty loops are removed; "hold" loops end stopped;
        "loop" loops start playing. Returns the finalized slot index, or -1."""
        if not self.is_recording or self.recording_slot == -1:
            return -1

        slot_idx = self.recording_slot
        loop = self.loops[slot_idx]
        self.recording_slot = -1
        self.is_recording = False

        loop.toggle_record_state(False)

        if not loop.has_events():
            self.delete_loop(slot_idx)
            return slot_idx

        if loop.loop_type == "hold":
            loop.toggle_playstate(False)
        else:
            # Restart playback cleanly from the top of the finalized loop
            loop.toggle_playstate(True)
        return slot_idx

    def check_recording_limits(self):
        """Auto-stop the active recording at the event/memory/time caps,
        exactly like a manual stop. Must be polled every main-loop iteration.
        Returns the auto-stopped slot index, or -1."""
        if not self.is_recording or self.recording_slot == -1:
            return -1

        loop = self.loops[self.recording_slot]
        hit_time_cap = (loop.start_timestamp != 0 and
                        ticks_diff(ticks_ms(), loop.start_timestamp) >= cfg.MAX_LOOP_MS)
        if loop.max_events_reached or hit_time_cap:
            return self.stop_recording()
        return -1

    # ==================== Playback / removal ====================

    def toggle_playstate(self, slot_idx, on_or_off=None):
        loop = self.loops[slot_idx]
        if loop is None or loop.is_recording:
            return
        loop.toggle_playstate(on_or_off)

    def delete_loop(self, slot_idx):
        loop = self.loops[slot_idx]
        if loop is None:
            return
        if self.recording_slot == slot_idx:
            self.recording_slot = -1
            self.is_recording = False
        loop.clear()
        self.loops[slot_idx] = None
        gc.collect()
