"""
Off-device unit tests for the Record Mode loop engine (looper.py +
loopmanager.py). The engine has no hardware dependencies, so this runs under
plain CPython with a fake millisecond clock.

Run from the repo:
    cd "Code - Production/src" && python3 ../scripts/test_record_engine.py
"""

import os
import sys

# Run with src/ as cwd so settings.json resolves; allow running from anywhere
SRC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
os.chdir(SRC_DIR)
sys.path.insert(0, SRC_DIR)

import looper
import loopmanager
import constants as cfg
from settings import settings
from loopmanager import (LoopManager, SLOT_EMPTY, SLOT_RECORDING,
                         SLOT_PLAYING, SLOT_STOPPED)


# ---------- Fake clock ----------

class FakeClock:
    def __init__(self):
        self.now = 1000

    def __call__(self):
        return self.now

    def advance(self, ms):
        self.now += ms


clock = FakeClock()
# Both modules bound ticks_ms at import time; patch both
looper.ticks_ms = clock
loopmanager.ticks_ms = clock


PASS = 0


def check(condition, label):
    global PASS
    assert condition, "FAIL: " + label
    PASS += 1
    print("  ok -", label)


def fresh_manager(loop_type="loop"):
    settings.settings["LOOP_TYPE"] = loop_type
    settings.settings["CC_RESOLUTION"] = 0
    settings.settings["TRIM_SILENCE"] = True
    return LoopManager()


def drain(loop):
    """Collect one get_new_events() result as a flat list."""
    events = loop.get_new_events()
    if not events:
        return [], []
    return events


# ---------- Tests ----------

def test_record_play_stop():
    print("record -> play -> wrap -> stop")
    mgr = fresh_manager()
    check(mgr.get_slot_state(0) == SLOT_EMPTY, "slot starts empty")

    check(mgr.start_recording(0, cc_set_idx=2), "recording starts")
    check(mgr.get_slot_state(0) == SLOT_RECORDING, "slot state is recording")
    loop = mgr.loops[0]
    check(loop.cc_set_idx == 2, "loop remembers its CC set")
    check(loop.get_new_events() is None, "no playback while first recording (total=0)")

    clock.advance(500)
    loop.add_cc(10, 64, 0)
    clock.advance(250)
    loop.add_cc(10, 70, 0)
    loop.add_cc(10, 70, 0)  # same value: filtered by the change cache
    clock.advance(250)
    loop.add_aftertouch(99, 1)
    check(len(loop.cc_events) == 2, "duplicate CC value not recorded")
    check(len(loop.aftertouch_events) == 1, "AT recorded")

    clock.advance(500)  # recording length: 1500 ms
    mgr.stop_recording()
    check(mgr.get_slot_state(0) == SLOT_PLAYING, "loop plays after stop-recording")
    # trim_silence: first event was at 500 ms -> shifted to 0, total 1500-500=1000
    check(loop.total_loop_ms == 1000, "trim_silence shifted loop length")
    check(loop.cc_events.timestamps_ms[0] == 0, "first event trimmed to 0")
    check(loop.aftertouch_events.timestamps_ms[0] == 500, "AT timestamp shifted")
    check((10, 0) in loop._last_cc_values, "cc inventory kept after recording stops")
    check(1 in loop._last_at_values, "at inventory kept after recording stops")

    # playback: at t=0 the first event is due
    clock.advance(1)
    cc, at = drain(loop)
    check(cc == [(10, 64, 0)], "first CC due at loop start")
    clock.advance(250)
    cc, at = drain(loop)
    check(cc == [(10, 70, 0)] and at == [], "second CC at 250ms")
    clock.advance(250)
    cc, at = drain(loop)
    check(at == [(0, 99, 1)], "AT event at 500ms")
    # wrap: cross the 1000ms boundary, loop resets, events replay
    clock.advance(600)
    check(loop.get_new_events() is None, "loop end returns None and resets")
    clock.advance(1)
    cc, at = drain(loop)
    check(cc == [(10, 64, 0)], "loop wrapped and replays from start")

    mgr.toggle_playstate(0, False)
    check(mgr.get_slot_state(0) == SLOT_STOPPED, "loop stops")
    check(loop.get_new_events() is None, "stopped loop yields nothing")


def test_empty_recording_removed():
    print("stopping an empty recording deletes the slot")
    mgr = fresh_manager()
    mgr.start_recording(1)
    clock.advance(800)
    mgr.stop_recording()
    check(mgr.get_slot_state(1) == SLOT_EMPTY, "empty recording removed")


def test_switch_recording():
    print("switching recording to another empty slot finalizes the first")
    mgr = fresh_manager()
    mgr.start_recording(0)
    clock.advance(100)
    mgr.loops[0].add_cc(5, 50, 0)
    clock.advance(400)
    mgr.start_recording(2)  # switch: slot 0 finalized, slot 2 records
    check(mgr.get_slot_state(0) == SLOT_PLAYING, "old slot finalized and playing")
    check(mgr.get_slot_state(2) == SLOT_RECORDING, "new slot recording")
    check(mgr.recording_slot == 2, "recording_slot moved")
    # empty old recording is silently removed instead
    mgr.start_recording(3)
    check(mgr.get_slot_state(2) == SLOT_EMPTY, "empty old recording removed on switch")
    mgr.stop_recording()


def test_hold_loop():
    print("hold loops start stopped, play the sweep once, then park")
    mgr = fresh_manager(loop_type="hold")
    mgr.start_recording(0)
    loop = mgr.loops[0]
    clock.advance(10)
    loop.add_cc(20, 10, 0)
    clock.advance(500)
    loop.add_cc(20, 120, 0)
    clock.advance(100)
    mgr.stop_recording()
    check(mgr.get_slot_state(0) == SLOT_STOPPED, "hold loop ends recording stopped")

    mgr.toggle_playstate(0, True)
    clock.advance(1)
    cc, at = drain(loop)
    check(cc == [(20, 10, 0)], "hold sweep first event")
    clock.advance(500)
    cc, at = drain(loop)
    check(cc == [(20, 120, 0)], "hold sweep final event")
    clock.advance(200)  # past loop end
    check(loop.get_new_events() is None, "hold loop reaches end")
    check(loop.cc_sweep_complete and loop.at_sweep_complete, "hold sweep parked")
    check(loop.loop_is_playing, "parked hold loop still counts as playing")
    clock.advance(1000)
    check(loop.get_new_events() is None, "parked hold loop emits nothing")
    mgr.toggle_playstate(0, False)
    check(mgr.get_slot_state(0) == SLOT_STOPPED, "hold loop stops")


def test_delete():
    print("delete clears the slot")
    mgr = fresh_manager()
    mgr.start_recording(0)
    clock.advance(10)
    mgr.loops[0].add_cc(1, 1, 0)
    clock.advance(100)
    mgr.stop_recording()
    mgr.delete_loop(0)
    check(mgr.get_slot_state(0) == SLOT_EMPTY, "deleted slot is empty")


def test_event_cap_autostop():
    print("event cap auto-stops recording like a manual stop")
    mgr = fresh_manager()
    mgr.start_recording(0)
    loop = mgr.loops[0]
    for i in range(cfg.MAX_LOOP_EVENTS + 10):
        clock.advance(5)
        loop.add_cc(30, i % 128, 0)
    check(len(loop.cc_events) == cfg.MAX_LOOP_EVENTS, "events capped at MAX_LOOP_EVENTS")
    check(loop.max_events_reached, "cap flag set")
    stopped = mgr.check_recording_limits()
    check(stopped == 0, "check_recording_limits auto-stopped the slot")
    check(mgr.get_slot_state(0) == SLOT_PLAYING, "auto-stop behaves like manual stop")
    mgr.delete_loop(0)


def test_time_cap_autostop():
    print("60s time cap auto-stops recording")
    mgr = fresh_manager()
    mgr.start_recording(0)
    loop = mgr.loops[0]
    clock.advance(10)
    loop.add_cc(40, 5, 0)
    clock.advance(cfg.MAX_LOOP_MS)  # well past the cap
    stopped = mgr.check_recording_limits()
    check(stopped == 0, "time cap auto-stopped the slot")
    check(loop.total_loop_ms <= cfg.MAX_LOOP_MS, "loop length clamped to MAX_LOOP_MS")
    check(mgr.get_slot_state(0) == SLOT_PLAYING, "loop plays after time-cap stop")
    mgr.delete_loop(0)


def test_cc_resolution_filter():
    print("cc_resolution filters small deltas")
    settings.settings["CC_RESOLUTION"] = 2
    mgr = LoopManager()
    mgr.start_recording(0)
    loop = mgr.loops[0]
    clock.advance(10)
    loop.add_cc(50, 60, 0)
    loop.add_cc(50, 61, 0)  # delta 1 <= 2: filtered
    loop.add_cc(50, 62, 0)  # delta 2 <= 2: filtered
    loop.add_cc(50, 63, 0)  # delta 3 > 2: recorded
    check(len(loop.cc_events) == 2, "resolution filter applied")
    settings.settings["CC_RESOLUTION"] = 0
    mgr.delete_loop(0)


def test_multichannel_events():
    print("per-event channels are preserved through playback")
    mgr = fresh_manager()
    mgr.start_recording(0)
    loop = mgr.loops[0]
    clock.advance(10)
    loop.add_cc(7, 100, 0)
    loop.add_cc(7, 100, 3)  # same CC, different channel: separate cache entry
    clock.advance(100)
    mgr.stop_recording()
    check(len(loop.cc_events) == 2, "per-channel cache keys")
    clock.advance(1)
    cc, at = drain(loop)
    channels = sorted(event[2] for event in cc)
    check(channels == [0, 3], "channels preserved in playback")
    mgr.delete_loop(0)


def test_ticks_wraparound():
    print("ms timebase survives supervisor.ticks_ms wraparound")
    mgr = fresh_manager()
    clock.now = (1 << 29) - 200  # 200ms before the wrap point
    mgr.start_recording(0)
    loop = mgr.loops[0]
    clock.advance(50)
    loop.add_cc(60, 10, 0)
    clock.now = (clock.now + 300) % (1 << 29)  # cross the wrap
    loop.add_cc(60, 90, 0)
    check(loop.cc_events.timestamps_ms[1] == 350, "event offset correct across wrap")
    mgr.stop_recording()
    check(loop.total_loop_ms == 300, "loop length correct across wrap (trimmed)")
    mgr.delete_loop(0)


if __name__ == "__main__":
    test_record_play_stop()
    test_empty_recording_removed()
    test_switch_recording()
    test_hold_loop()
    test_delete()
    test_event_cap_autostop()
    test_time_cap_autostop()
    test_cc_resolution_filter()
    test_multichannel_events()
    test_ticks_wraparound()
    print(f"\nAll {PASS} checks passed.")
