# Loop Manager: 4 slots per CC set (global + pages); one global recording; layered multi-bank playback.
# Controller selects active set; slot ops resolve against it. Ported from DJBB Midi Loopster 2.

import gc

import constants as cfg
from looper import MidiLoop, ticks_ms, ticks_diff, _mem_free
from settings import settings

# Slot states (consumed by the controller and LightsManager)
SLOT_EMPTY = "empty"
SLOT_RECORDING = "recording"
SLOT_PLAYING = "playing"
SLOT_STOPPED = "stopped"

NUM_SLOTS = 4


class LoopManager:
    def __init__(self):
        # {set_idx: [MidiLoop|None] * NUM_SLOTS}; lazy-created, unused sets free.
        self.loops_by_set = {}
        self.active_set = 0
        # Global recording state: (set, slot) or (-1, -1) if none.
        self.recording_set = -1
        self.recording_slot = -1
        self.is_recording = False

    def _slots_for(self, set_idx):
        """Return set_idx's slot list, creating (empty) on first use."""
        slots = self.loops_by_set.get(set_idx)
        if slots is None:
            slots = [None] * NUM_SLOTS
            self.loops_by_set[set_idx] = slots
        return slots

    @property
    def loops(self):
        """Active set's slots; backward-compatible view (loops[slot] = active bank)."""
        return self._slots_for(self.active_set)

    def set_active_set(self, set_idx):
        """Select which set's slots are addressed by slot operations."""
        self.active_set = set_idx

    def iter_all_loops(self):
        """Yield all non-None loops across all sets (for playback pump and cleanup)."""
        for slots in self.loops_by_set.values():
            for loop in slots:
                if loop is not None:
                    yield loop

    # ==================== Queries ====================

    def slot_has_loop(self, slot_idx):
        return self.loops[slot_idx] is not None

    def get_recording_loop(self):
        if self.recording_set == -1:
            return None
        return self.loops_by_set[self.recording_set][self.recording_slot]

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
        """Start recording on an empty slot in the active set. If a recording is
        already running on another slot/set, finalize it first (keep it if it
        has events, silently remove it if empty). cc_set_idx is stamped on the
        loop for its slot LED color.

        Returns True if recording started, or False if it was refused - the slot
        is occupied, OR free RAM is below START_RECORD_FLOOR (so the new loop
        couldn't safely grow to a full GUARANTEED_LOOP_EVENTS without risking a
        fragmentation crash). The controller turns a low-memory False into the
        triple-blink reject."""
        slots = self.loops_by_set.get(self.active_set)
        if slots is not None and slots[slot_idx] is not None:
            return False

        if self.is_recording:
            self.stop_recording()

        # Low-memory guard: refuse rather than start a recording we might not be
        # able to grow. Pure threshold check against live free RAM - reserves
        # nothing. _mem_free() returns a huge value off-device (CPython), so
        # unit tests are unaffected.
        gc.collect()
        if _mem_free() < cfg.START_RECORD_FLOOR:
            return False

        slots = self._slots_for(self.active_set)
        loop = MidiLoop(loop_type=settings.get_loop_type(), cc_set_idx=cc_set_idx)
        slots[slot_idx] = loop
        self.recording_set = self.active_set
        self.recording_slot = slot_idx
        self.is_recording = True
        loop.toggle_record_state(True)
        return True

    def stop_recording(self):
        """Finalize recording (manual/cap). Return slot index or -1."""
        if not self.is_recording or self.recording_slot == -1:
            return -1

        set_idx = self.recording_set
        slot_idx = self.recording_slot
        loop = self._slots_for(set_idx)[slot_idx]
        self.recording_set = -1
        self.recording_slot = -1
        self.is_recording = False

        loop.toggle_record_state(False)

        if not loop.has_events():
            self._remove(set_idx, slot_idx)
            return slot_idx

        if loop.loop_type == "hold":
            loop.toggle_playstate(False)
        else:
            loop.toggle_playstate(True)
        return slot_idx

    def check_recording_limits(self):
        """Auto-stop at event/memory/time caps; return slot index or -1."""
        if not self.is_recording or self.recording_slot == -1:
            return -1

        loop = self.loops_by_set[self.recording_set][self.recording_slot]
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

    def _remove(self, set_idx, slot_idx):
        """Clear/drop a slot; clear recording state if it's recording."""
        slots = self.loops_by_set.get(set_idx)
        if slots is None or slots[slot_idx] is None:
            return
        if self.recording_set == set_idx and self.recording_slot == slot_idx:
            self.recording_set = -1
            self.recording_slot = -1
            self.is_recording = False
        slots[slot_idx].clear()
        slots[slot_idx] = None
        gc.collect()

    def delete_loop(self, slot_idx):
        """Delete loop in active set."""
        self._remove(self.active_set, slot_idx)

    def clear_all(self):
        """Clear all loops in all sets."""
        for slots in self.loops_by_set.values():
            for slot_idx in range(NUM_SLOTS):
                if slots[slot_idx] is not None:
                    slots[slot_idx].clear()
                    slots[slot_idx] = None
        self.recording_set = -1
        self.recording_slot = -1
        self.is_recording = False
        gc.collect()
