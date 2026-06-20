"""
Unit tests for the Record Mode loop engine (looper.py + loopmanager.py). The
engine has no hardware dependencies, so it runs both ON-DEVICE (CircuitPython,
e.g. copy to the Pico and run in Thonny) and OFF-DEVICE (plain CPython) with a
fake millisecond clock.

Off-device (CPython):
    cd "Code - Production/src" && python3 ../scripts/test_record_engine.py
On-device (CircuitPython / Thonny):
    copy this file to the device alongside looper.py etc. and run it
    (or: >>> import test_record_engine)
"""

import sys

# Off-device (CPython) only: add src/ to the path and cd into it so
# settings.json resolves. CircuitPython's os has no path/chdir and the engine
# modules are already importable from the device root, so skip this there.
try:
    import os
    SRC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
    os.chdir(SRC_DIR)
    sys.path.insert(0, SRC_DIR)
except (AttributeError, NameError):
    pass  # CircuitPython: no os.path/os.chdir/__file__ - imports resolve directly

import looper
import loopmanager
import constants as cfg
from settings import settings
from loopmanager import (LoopManager, SLOT_EMPTY, SLOT_RECORDING,
                         SLOT_PLAYING, SLOT_STOPPED)
from wiggle import SliderWiggleDetector


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


def test_first_value_tracking():
    print("first recorded value per (cc, ch) / channel feeds cc_reset snap-back")
    mgr = fresh_manager()
    mgr.start_recording(0)
    loop = mgr.loops[0]

    clock.advance(10)
    loop.add_cc(10, 40, 0)   # first value for (10, 0)
    clock.advance(10)
    loop.add_cc(10, 90, 0)   # later value: first stays 40
    clock.advance(10)
    loop.add_cc(10, 20, 3)   # different channel: separate first-value entry
    clock.advance(10)
    loop.add_aftertouch(30, 1)  # first AT for channel 1
    clock.advance(10)
    loop.add_aftertouch(110, 1)  # later AT: first stays 30
    clock.advance(100)
    mgr.stop_recording()

    check(loop._first_cc_values[(10, 0)] == 40, "first CC value retained, not overwritten")
    check(loop._first_cc_values[(10, 3)] == 20, "first value tracked per channel")
    check(loop._last_cc_values[(10, 0)] == 90, "last value still tracks most recent")
    check(loop._first_at_values[1] == 30, "first AT value retained, not overwritten")
    check(loop._last_at_values[1] == 110, "last AT value still tracks most recent")

    mgr.delete_loop(0)
    check(loop._first_cc_values == {} and loop._first_at_values == {}, "clear() empties first-value dicts")


def test_first_value_respects_resolution_filter():
    print("values filtered by cc_resolution don't become 'first' values")
    settings.settings["CC_RESOLUTION"] = 5
    mgr = LoopManager()
    mgr.start_recording(0)
    loop = mgr.loops[0]
    clock.advance(10)
    loop.add_cc(70, 64, 0)   # recorded: first value
    clock.advance(10)
    loop.add_cc(70, 66, 0)   # delta 2 <= 5: filtered, must not change first value
    clock.advance(10)
    loop.add_cc(70, 80, 0)   # delta 16 > 5: recorded, but first value unchanged
    clock.advance(100)
    mgr.stop_recording()

    check(loop._first_cc_values[(70, 0)] == 64, "filtered intermediate value did not become 'first'")
    check(loop._last_cc_values[(70, 0)] == 80, "last value reflects the latest recorded change")
    settings.settings["CC_RESOLUTION"] = 0
    mgr.delete_loop(0)


def test_wiggle_zone_boundaries():
    print("wiggle: zone thresholds are inclusive (<=3 / >=125)")
    check(SliderWiggleDetector._zone_for(cfg.MAPPING_LOW_THRESH) == "LOW", "low threshold is in the LOW zone")
    check(SliderWiggleDetector._zone_for(cfg.MAPPING_LOW_THRESH + 1) is None, "just above low threshold is no zone")
    check(SliderWiggleDetector._zone_for(cfg.MAPPING_HIGH_THRESH) == "HIGH", "high threshold is in the HIGH zone")
    check(SliderWiggleDetector._zone_for(cfg.MAPPING_HIGH_THRESH - 1) is None, "just below high threshold is no zone")


def test_wiggle_seeded_in_zone_counts_as_hit_one():
    print("wiggle: arming inside a zone counts as hit 1")
    det = SliderWiggleDetector()
    det.arm(2, 0.0)  # seed inside LOW zone -> hit 1
    check(det.update(125, 0.5) is False, "hit 2 (HIGH) does not complete")
    check(det.update(2, 1.0) is True, "hit 3 (LOW) completes the wiggle")


def test_wiggle_requires_alternation():
    print("wiggle: repeated entries into the same zone don't count")
    det = SliderWiggleDetector()
    det.arm(2, 0.0)  # hit 1 (LOW)
    check(det.update(2, 0.2) is False, "staying in LOW doesn't add a hit")
    check(det.update(125, 0.5) is False, "HIGH is hit 2")
    check(det.update(125, 0.7) is False, "staying in HIGH doesn't add a hit")
    check(det.update(2, 1.0) is True, "LOW is hit 3 - completes")


def test_wiggle_mid_travel_seed_is_zero_hits():
    print("wiggle: arming mid-travel starts at zero hits")
    det = SliderWiggleDetector()
    det.arm(64, 0.0)  # mid-travel: no hit yet
    check(det.update(64, 0.5) is False, "still no zone reached")
    check(det.update(3, 1.0) is False, "LOW is hit 1 (fresh timer)")
    check(det.update(125, 1.5) is False, "HIGH is hit 2")
    check(det.update(3, 2.0) is True, "LOW is hit 3 - completes")


def test_wiggle_window_expiry_reseeds():
    print("wiggle: window expiry re-seeds from the current sample")
    det = SliderWiggleDetector()
    det.arm(0, 0.0)  # hit 1 (LOW) @ t=0
    check(det.update(127, 1.0) is False, "hit 2 (HIGH) @ t=1")
    # window (3.0s) expires before hit 3 lands
    check(det.update(0, 4.0) is False, "expired window re-seeds as hit 1 (LOW) @ t=4")
    check(det.update(127, 4.5) is False, "hit 2 (HIGH) @ t=4.5, within the new window")
    check(det.update(0, 5.0) is True, "hit 3 (LOW) @ t=5 completes within the re-seeded window")


def test_wiggle_completes_at_exact_window_boundary():
    print("wiggle: completing exactly at the window boundary counts")
    det = SliderWiggleDetector()
    det.arm(0, 0.0)  # hit 1 @ t=0
    check(det.update(127, 1.0) is False, "hit 2 @ t=1")
    check(det.update(0, 3.0) is True, "hit 3 @ t=3.0 == window boundary - still completes")


def test_wiggle_disarm_clears_state():
    print("wiggle: disarm clears hits/zone")
    det = SliderWiggleDetector()
    det.arm(0, 0.0)  # hit 1
    det.disarm()
    check(det.update(127, 0.1) is False, "after disarm, HIGH is treated as hit 1, not hit 2")
    check(det.update(0, 0.2) is False, "...so LOW here is only hit 2")
    check(det.update(127, 0.3) is True, "hit 3 completes from the post-disarm baseline")


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


def test_per_set_isolation():
    print("each CC set has its own 4 pads (per-bank pads)")
    mgr = fresh_manager()

    # Record into set 0, slot 0
    mgr.set_active_set(0)
    mgr.start_recording(0, cc_set_idx=0)
    clock.advance(10)
    mgr.get_recording_loop().add_cc(1, 10, 0)
    clock.advance(100)
    mgr.stop_recording()
    check(mgr.get_slot_state(0) == SLOT_PLAYING, "set 0 slot 0 has a loop")

    # Navigate to set 1: its slot 0 is a FRESH, empty pad
    mgr.set_active_set(1)
    check(mgr.get_slot_state(0) == SLOT_EMPTY, "set 1 slot 0 is fresh/empty")
    mgr.start_recording(0, cc_set_idx=1)
    clock.advance(10)
    mgr.get_recording_loop().add_cc(2, 20, 0)
    clock.advance(100)
    mgr.stop_recording()
    check(mgr.get_slot_state(0) == SLOT_PLAYING, "set 1 slot 0 now has its own loop")
    check(mgr.loops[0].cc_set_idx == 1, "set 1 loop stamped with its cc_set_idx")

    # Back to set 0: its loop is still there and distinct
    mgr.set_active_set(0)
    check(mgr.get_slot_state(0) == SLOT_PLAYING, "set 0 loop survived navigation")
    check(mgr.loops[0].cc_set_idx == 0, "set 0 loop is the original one")
    mgr.clear_all()


def test_iter_all_loops_spans_sets():
    print("iter_all_loops / playback spans every set (layered looper)")
    mgr = fresh_manager()
    for set_idx in (0, 2, 5):
        mgr.set_active_set(set_idx)
        mgr.start_recording(0, cc_set_idx=set_idx)
        clock.advance(10)
        mgr.get_recording_loop().add_cc(set_idx + 1, 30, 0)
        clock.advance(100)
        mgr.stop_recording()
    all_loops = list(mgr.iter_all_loops())
    check(len(all_loops) == 3, "iter_all_loops sees loops from all 3 sets")
    sets_seen = sorted(l.cc_set_idx for l in all_loops)
    check(sets_seen == [0, 2, 5], "loops from every recorded set are yielded")


def test_recording_global_single_across_sets():
    print("recording is global-single: switching sets finalizes the prior one")
    mgr = fresh_manager()
    mgr.set_active_set(0)
    mgr.start_recording(0, cc_set_idx=0)
    clock.advance(10)
    mgr.get_recording_loop().add_cc(1, 50, 0)
    clock.advance(50)
    check(mgr.recording_set == 0 and mgr.recording_slot == 0, "recording in set 0")

    # Navigate + start recording in set 1: set 0's recording is finalized
    mgr.set_active_set(1)
    mgr.start_recording(0, cc_set_idx=1)
    check(mgr.recording_set == 1, "recording moved to set 1")
    check(not mgr.is_recording or mgr.recording_set == 1, "only one recording at a time")
    mgr.set_active_set(0)
    check(mgr.get_slot_state(0) == SLOT_PLAYING, "set 0's loop was finalized + playing")
    mgr.clear_all()


def test_clear_all_empties_every_set():
    print("clear_all removes loops from every set")
    mgr = fresh_manager()
    for set_idx in (0, 3):
        mgr.set_active_set(set_idx)
        mgr.start_recording(1, cc_set_idx=set_idx)
        clock.advance(10)
        mgr.get_recording_loop().add_cc(9, 9, 0)
        clock.advance(50)
        mgr.stop_recording()
    mgr.clear_all()
    check(list(mgr.iter_all_loops()) == [], "no loops remain after clear_all")
    check(not mgr.is_recording, "clear_all resets recording state")
    mgr.set_active_set(3)
    check(mgr.get_slot_state(1) == SLOT_EMPTY, "set 3 slot is empty after clear_all")


def test_delete_only_active_set():
    print("delete_loop only touches the active set")
    mgr = fresh_manager()
    mgr.set_active_set(0)
    mgr.start_recording(0, cc_set_idx=0)
    clock.advance(10)
    mgr.get_recording_loop().add_cc(1, 1, 0)
    clock.advance(50)
    mgr.stop_recording()
    mgr.set_active_set(1)
    mgr.start_recording(0, cc_set_idx=1)
    clock.advance(10)
    mgr.get_recording_loop().add_cc(2, 2, 0)
    clock.advance(50)
    mgr.stop_recording()

    # Delete set 1's pad; set 0's must survive
    mgr.delete_loop(0)
    check(mgr.get_slot_state(0) == SLOT_EMPTY, "active set (1) pad deleted")
    mgr.set_active_set(0)
    check(mgr.get_slot_state(0) == SLOT_PLAYING, "other set's pad untouched by delete")
    mgr.clear_all()


def test_total_events_cap():
    print("event cap counts cc + at together (plan 4g)")
    mgr = fresh_manager()
    mgr.start_recording(0)
    loop = mgr.loops[0]
    # Alternate CC and AT so both storages grow; total must cap at MAX_LOOP_EVENTS
    for i in range(cfg.MAX_LOOP_EVENTS + 50):
        clock.advance(2)
        if i % 2 == 0:
            loop.add_cc(30, i % 128, 0)
        else:
            loop.add_aftertouch(i % 128, 1)
    total = len(loop.cc_events) + len(loop.aftertouch_events)
    check(total == cfg.MAX_LOOP_EVENTS, "cc+at total capped at MAX_LOOP_EVENTS, not 2x")
    check(loop.max_events_reached, "cap flag set on total")
    mgr.delete_loop(0)


def test_low_memory_reject():
    print("start_recording refuses below START_RECORD_FLOOR (memory guard)")
    saved = loopmanager._mem_free
    try:
        # Pretend free RAM is just under the floor: start must be refused.
        loopmanager._mem_free = lambda: cfg.START_RECORD_FLOOR - 1
        mgr = fresh_manager()
        check(mgr.start_recording(0) is False, "refused when free < START_RECORD_FLOOR")
        check(mgr.get_slot_state(0) == SLOT_EMPTY, "no loop created on refusal")
        check(not mgr.is_recording, "recording state untouched on refusal")
        # Plenty of RAM: start is allowed again.
        loopmanager._mem_free = lambda: cfg.START_RECORD_FLOOR + 100000
        check(mgr.start_recording(0) is True, "allowed when free >= START_RECORD_FLOOR")
        mgr.clear_all()
    finally:
        loopmanager._mem_free = saved


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
    test_first_value_tracking()
    test_first_value_respects_resolution_filter()
    test_wiggle_zone_boundaries()
    test_wiggle_seeded_in_zone_counts_as_hit_one()
    test_wiggle_requires_alternation()
    test_wiggle_mid_travel_seed_is_zero_hits()
    test_wiggle_window_expiry_reseeds()
    test_wiggle_completes_at_exact_window_boundary()
    test_wiggle_disarm_clears_state()
    test_ticks_wraparound()
    # Per-set ("4 pads per bank") refactor
    test_per_set_isolation()
    test_iter_all_loops_spans_sets()
    test_recording_global_single_across_sets()
    test_clear_all_empties_every_set()
    test_delete_only_active_set()
    test_total_events_cap()
    test_low_memory_reject()
    print(f"\nAll {PASS} checks passed.")
