"""
LumaFader - CC/AT Loop Engine (Record Mode)
============================================
Ported from the DJBB Midi Loopster 2 looper.py, stripped down to what the
LumaFader needs:

- CC + Channel Aftertouch events only (no notes, no arp, no oneshot).
- Pure wall-clock millisecond timebase (no MIDI clock, no BPM, no quantize).
- RAM-only storage (no flash streaming / persistence) - loops are session-only.
- Loop types: "loop" (repeat) and "hold" (gate playback: the controller plays
  the loop only while its pad is held; the engine parks on the sweep's final
  values once it completes within a hold).

The engine has no hardware dependencies, so it can be unit-tested off-device.
All MIDI sending is done by the caller (controller / playback pump).
"""

import array
import gc
import time

import constants as cfg
from settings import settings

# supervisor.ticks_ms() wraps at 2**29 ms (~6.2 days); use the standard
# wrap-aware diff. time.monotonic() is NOT used because CircuitPython's float
# monotonic loses ms precision after a few hours of uptime.
_TICKS_PERIOD = 1 << 29
_TICKS_HALFPERIOD = 1 << 28

try:
    from supervisor import ticks_ms
except ImportError:
    # Off-device (CPython) fallback for unit testing
    def ticks_ms():
        return (time.monotonic_ns() // 1000000) % _TICKS_PERIOD


def ticks_diff(ticks1, ticks2):
    """Wrap-aware difference between two ticks_ms() values."""
    return (ticks1 - ticks2 + _TICKS_HALFPERIOD) % _TICKS_PERIOD - _TICKS_HALFPERIOD


def _mem_free():
    try:
        return gc.mem_free()
    except AttributeError:
        # CPython (off-device testing) has no gc.mem_free()
        return 1 << 30


# Storage timestamps are array('H') (unsigned 16-bit); MAX_LOOP_MS (60000)
# keeps every recorded offset below this hard ceiling.
MAX_TIMESTAMP_MS = 65535


class ArrayBasedCCStorage:
    """Array-based MIDI CC/AT event storage for memory efficiency (~5 bytes/event)."""

    def __init__(self):
        self.cc_nums = array.array('B', [])        # CC numbers (0-127); 0 for aftertouch
        self.values = array.array('B', [])         # CC values / AT pressure (0-127)
        self.timestamps_ms = array.array('H', [])  # ms offsets from loop start (0-65535)
        self.midi_channels = array.array('B', [])  # MIDI channels (0-15)

    def add_event(self, cc_num, value, ms, midi_channel=0):
        if ms < 0:
            ms = 0
        elif ms > MAX_TIMESTAMP_MS:
            ms = MAX_TIMESTAMP_MS

        self.cc_nums.append(cc_num)
        self.values.append(value)
        self.timestamps_ms.append(ms)
        self.midi_channels.append(midi_channel)

    def get_event(self, idx):
        if idx < 0:
            idx = len(self.cc_nums) + idx
        return (self.cc_nums[idx], self.values[idx],
                self.timestamps_ms[idx], self.midi_channels[idx])

    def __len__(self):
        return len(self.cc_nums)

    def __getitem__(self, idx):
        return self.get_event(idx)

    def clear(self):
        self.cc_nums = array.array('B', [])
        self.values = array.array('B', [])
        self.timestamps_ms = array.array('H', [])
        self.midi_channels = array.array('B', [])


class MidiLoop:
    """A single CC/AT loop: recording, playback position tracking, event queues."""

    def __init__(self, loop_type="loop", cc_set_idx=0):
        self.loop_type = loop_type    # "loop" or "hold"
        self.cc_set_idx = cc_set_idx  # CC set active at record start (drives slot LED color)

        # Timing (ms timebase)
        self.start_timestamp = 0      # ticks_ms() at record/playback start; 0 = idle
        self.total_loop_ms = 0        # loop length; 0 until a recording is finalized

        # Event storage
        self.cc_events = ArrayBasedCCStorage()
        self.aftertouch_events = ArrayBasedCCStorage()

        # Recording value caches (O(1) change detection). Kept after recording
        # stops - they double as the loop's (cc, ch) inventory for the
        # cc_reset ("bounce back") scan.
        self._last_cc_values = {}   # {(cc_num, midi_channel): value}
        self._last_at_values = {}   # {midi_channel: pressure}

        # First recorded value per (cc, ch) / per ch - feeds the cc_reset
        # snap-back (return to where the parameter was when the loop's sweep
        # began). Kept after recording stops, like the _last_* dicts above.
        self._first_cc_values = {}  # {(cc_num, midi_channel): value}
        self._first_at_values = {}  # {midi_channel: pressure}

        # Playback queue indices
        self.queue_index_cc = 0
        self.queue_index_at = 0

        # State flags
        self.loop_is_playing = False
        self.is_recording = False
        self.cc_sweep_complete = False  # Hold mode: has the CC sweep played through once?
        self.at_sweep_complete = False
        self.max_events_reached = False

        # cc_resolution cached at record start (avoids settings lookups in the hot path)
        self._cc_resolution = 0

    # ==================== State ====================

    def reset(self):
        """Reset playback to the top of the loop."""
        self.queue_index_cc = 0
        self.queue_index_at = 0
        self.cc_sweep_complete = False
        self.at_sweep_complete = False
        self.start_timestamp = ticks_ms()

    def reset_timing(self):
        self.start_timestamp = 0

    def toggle_playstate(self, on_or_off=None):
        self.loop_is_playing = on_or_off if on_or_off is not None else not self.loop_is_playing
        if self.loop_is_playing:
            self.reset()
        else:
            self.reset_timing()

    def toggle_record_state(self, on_or_off=None):
        new_state = on_or_off if on_or_off is not None else not self.is_recording
        if new_state == self.is_recording:
            return
        self.is_recording = new_state

        # --- STARTING RECORDING ---
        if self.is_recording:
            gc.collect()
            self._cc_resolution = settings.get_cc_resolution()
            # Loop is "playing" while recording; get_new_events() returns None
            # for it because total_loop_ms is still 0.
            self.toggle_playstate(True)

        # --- STOPPING RECORDING ---
        else:
            self.max_events_reached = False
            if self.start_timestamp != 0:
                elapsed = ticks_diff(ticks_ms(), self.start_timestamp)
                self.total_loop_ms = min(max(elapsed, 1), cfg.MAX_LOOP_MS)
                if settings.get_trim_silence():
                    self._trim_silence_start()
            # NOTE: _last_cc_values/_last_at_values are intentionally KEPT
            # (unlike the Loopster) - they feed the cc_reset scan.
            gc.collect()

    def clear(self):
        self.cc_events.clear()
        self.aftertouch_events.clear()
        self._last_cc_values.clear()
        self._last_at_values.clear()
        self._first_cc_values.clear()
        self._first_at_values.clear()
        self.queue_index_cc = 0
        self.queue_index_at = 0
        self.total_loop_ms = 0
        self.start_timestamp = 0
        self.loop_is_playing = False
        self.is_recording = False
        self.cc_sweep_complete = False
        self.at_sweep_complete = False
        self.max_events_reached = False
        gc.collect()

    def has_events(self):
        return len(self.cc_events) > 0 or len(self.aftertouch_events) > 0

    def count_events(self):
        return len(self.cc_events) + len(self.aftertouch_events)

    # ==================== Recording ====================

    def _check_recording_guards(self, events_length):
        """Shared add_cc/add_aftertouch guards. Returns the event's ms offset,
        or None if the event must not be recorded."""
        if not self.is_recording or self.start_timestamp == 0:
            return None

        if events_length >= cfg.MAX_LOOP_EVENTS:
            self.max_events_reached = True
            return None

        ms = ticks_diff(ticks_ms(), self.start_timestamp)
        if ms >= cfg.MAX_LOOP_MS:
            self.max_events_reached = True
            return None

        # Memory check every 100 events - stop recording before crashing
        if events_length > 0 and events_length % 100 == 0:
            gc.collect()
            if _mem_free() < cfg.MEMORY_CRITICAL_THRESHOLD:
                self.max_events_reached = True
                return None

        return ms

    def add_cc(self, cc_num, cc_value, midi_channel=0):
        """Record a CC event. Only records if the value changed by more than cc_resolution."""
        cache_key = (cc_num, midi_channel)
        last_cc_value = self._last_cc_values.get(cache_key)
        if last_cc_value is not None and abs(cc_value - last_cc_value) <= self._cc_resolution:
            return

        ms = self._check_recording_guards(len(self.cc_events))
        if ms is None:
            return

        if cache_key not in self._first_cc_values:
            self._first_cc_values[cache_key] = cc_value
        self._last_cc_values[cache_key] = cc_value
        self.cc_events.add_event(cc_num, cc_value, ms, midi_channel)

    def add_aftertouch(self, pressure, midi_channel=0):
        """Record a Channel Aftertouch event (stored with cc_num=0)."""
        last_at_value = self._last_at_values.get(midi_channel)
        if last_at_value is not None and abs(pressure - last_at_value) <= self._cc_resolution:
            return

        ms = self._check_recording_guards(len(self.aftertouch_events))
        if ms is None:
            return

        if midi_channel not in self._first_at_values:
            self._first_at_values[midi_channel] = pressure
        self._last_at_values[midi_channel] = pressure
        self.aftertouch_events.add_event(0, pressure, ms, midi_channel)

    def _trim_silence_start(self):
        """Shift all events earlier so the loop starts on the first recorded event."""
        first_ms = None
        if len(self.cc_events) > 0:
            first_ms = self.cc_events.timestamps_ms[0]
        if len(self.aftertouch_events) > 0:
            at_first_ms = self.aftertouch_events.timestamps_ms[0]
            if first_ms is None or at_first_ms < first_ms:
                first_ms = at_first_ms

        if not first_ms:
            return

        for storage in (self.cc_events, self.aftertouch_events):
            for i in range(len(storage)):
                ms = storage.timestamps_ms[i]
                storage.timestamps_ms[i] = ms - first_ms if ms >= first_ms else 0

        self.total_loop_ms = max(self.total_loop_ms - first_ms, 1)

    # ==================== Playback ====================

    def _handle_loop_end(self):
        if self.loop_type == "hold":
            # Hold mode: sweep finishes, then freeze on the final values
            # (loop stays "playing"/parked until explicitly stopped).
            self.cc_sweep_complete = True
            self.at_sweep_complete = True
        else:
            self.reset()

    def _process_event_queue(self, current_ms, queue_index, event_storage, new_events):
        """Collect events due at current_ms. Returns the updated queue index."""
        events_len = len(event_storage)
        while queue_index < events_len:
            if event_storage.timestamps_ms[queue_index] <= current_ms:
                new_events.append((event_storage.cc_nums[queue_index],
                                   event_storage.values[queue_index],
                                   event_storage.midi_channels[queue_index]))
                queue_index += 1
            else:
                break
        return queue_index

    def get_new_events(self):
        """Get CC/AT events due at the current playback position.

        Returns:
            (new_cc, new_at) where each is a list of (cc_num, value, channel)
            tuples (cc_num is 0 for AT entries), or None if nothing is due.
            Safe to call unconditionally - a loop mid-first-recording returns
            None because its total length is still 0.
        """
        if self.total_loop_ms <= 0 or not self.loop_is_playing or self.is_recording:
            return None

        if not self.has_events():
            return None

        # Hold mode parked on final values: nothing more to play
        if self.loop_type == "hold" and self.cc_sweep_complete and self.at_sweep_complete:
            return None

        current_ms = ticks_diff(ticks_ms(), self.start_timestamp)

        new_cc = []
        new_at = []

        if current_ms >= self.total_loop_ms:
            # Drain any events that fell between the last poll and the loop
            # boundary before resetting/parking.  Without this a gc.collect()
            # pause at the wrong moment can cause a hold loop to park without
            # ever sending its final values, leaving the synth at the wrong
            # position (skeleton A.1 in Record Mode Review Notes).
            drain_ms = self.total_loop_ms
            if not (self.loop_type == "hold" and self.cc_sweep_complete):
                self.queue_index_cc = self._process_event_queue(
                    drain_ms, self.queue_index_cc, self.cc_events, new_cc)
            if not (self.loop_type == "hold" and self.at_sweep_complete):
                self.queue_index_at = self._process_event_queue(
                    drain_ms, self.queue_index_at, self.aftertouch_events, new_at)
            self._handle_loop_end()
            return (new_cc, new_at) if (new_cc or new_at) else None

        if not (self.loop_type == "hold" and self.cc_sweep_complete):
            self.queue_index_cc = self._process_event_queue(
                current_ms, self.queue_index_cc, self.cc_events, new_cc)

        if not (self.loop_type == "hold" and self.at_sweep_complete):
            self.queue_index_at = self._process_event_queue(
                current_ms, self.queue_index_at, self.aftertouch_events, new_at)

        if new_cc or new_at:
            return new_cc, new_at
        return None
