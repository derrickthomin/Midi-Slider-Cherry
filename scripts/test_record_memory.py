"""
LumaFader - Record Mode Memory Stress / Measurement (ON-DEVICE)
================================================================
Answers "how many CC/AT events can we actually hold with all 4 loops?" and
prints lots of RAM data so we can pick a safe global event cap.

This MUST run on the Pico (CircuitPython) - gc.mem_free() only returns real
numbers there. Off-device CPython has no gc.mem_free(), so the script just
says so and exits.

How to run on the device:
    1. Open the serial REPL (e.g. screen / the Mu/Thonny REPL / `tio`).
    2. Press Ctrl-C to stop code.py and drop to the REPL.
    3. >>> import test_record_memory
    (re-run with: >>> import supervisor; supervisor.reload())

Phase A fills all 4 loop slots through the normal recording path (respects
MAX_LOOP_EVENTS, the per-100-event memory check, etc.) and snapshots RAM.
Phase B bypasses the per-loop cap on a scratch storage to find the raw event
ceiling - i.e. how conservative MAX_LOOP_EVENTS really is.
"""

import gc
import time

import constants as cfg
from looper import ArrayBasedCCStorage
from loopmanager import LoopManager, NUM_SLOTS
from settings import settings


def _mem():
    try:
        return gc.mem_free()
    except AttributeError:
        return None


def _fmt(n):
    return "n/a" if n is None else str(n)


def _banner(title):
    print("\n" + "=" * 56)
    print(title)
    print("=" * 56)


def phase_a_fill_all_slots():
    """Record up to MAX_LOOP_EVENTS into every slot via the normal path,
    snapshotting RAM as we go."""
    _banner("PHASE A - fill all 4 slots via the recording path")
    settings.settings["CC_RESOLUTION"] = 0      # record every change
    settings.settings["TRIM_SILENCE"] = False   # don't reshape timestamps

    gc.collect()
    start_free = _mem()
    print("free at start:        ", _fmt(start_free))

    mgr = LoopManager()
    per_slot_events = []

    for slot in range(NUM_SLOTS):
        mgr.start_recording(slot, cc_set_idx=slot)
        loop = mgr.loops[slot]
        i = 0
        # add_cc self-limits at MAX_LOOP_EVENTS / the memory floor.
        while not loop.max_events_reached:
            # vary value so the change-cache doesn't dedupe it away
            loop.add_cc(20 + slot, i % 128, midi_channel=slot)
            i += 1
            if i % 100 == 0:
                gc.collect()
                print("  slot %d  events=%4d  free=%s"
                      % (slot, loop.count_events(), _fmt(_mem())))
            if i > cfg.MAX_LOOP_EVENTS + 200:
                break  # safety: should never hit with the cap working
        mgr.stop_recording()
        n = loop.count_events()
        per_slot_events.append(n)
        gc.collect()
        print("  slot %d DONE events=%4d  total_ms=%5d  free=%s"
              % (slot, n, loop.total_loop_ms, _fmt(_mem())))

    gc.collect()
    end_free = _mem()
    total_events = sum(per_slot_events)
    print("-" * 56)
    print("per-slot event counts:", per_slot_events)
    print("total events held:    ", total_events)
    print("free at end:          ", _fmt(end_free))
    if start_free is not None and end_free is not None:
        used = start_free - end_free
        print("RAM used by 4 loops:  ", used, "bytes")
        if total_events:
            print("bytes / event (incl. overhead): %.2f" % (used / total_events))
    return mgr  # keep a reference alive so it isn't GC'd before we report


def phase_b_raw_ceiling():
    """Bypass the per-loop cap: keep appending to one storage until RAM runs
    out (or hits MEMORY_CRITICAL_THRESHOLD), to see how conservative the
    per-loop MAX_LOOP_EVENTS cap really is."""
    _banner("PHASE B - raw event ceiling on a single storage")
    gc.collect()
    start_free = _mem()
    print("free before fill:     ", _fmt(start_free))
    if start_free is None:
        print("(no gc.mem_free here - skipping)")
        return

    storage = ArrayBasedCCStorage()
    count = 0
    floor = cfg.MEMORY_CRITICAL_THRESHOLD
    try:
        while True:
            storage.add_event(20, count % 128, count % 60000, count % 16)
            count += 1
            if count % 250 == 0:
                free = _mem()
                if count % 1000 == 0:
                    print("  events=%6d  free=%s" % (count, _fmt(free)))
                if free is not None and free < floor:
                    print("  hit MEMORY_CRITICAL_THRESHOLD (%d) at %d events"
                          % (floor, count))
                    break
    except MemoryError:
        print("  MemoryError after %d events" % count)

    gc.collect()
    print("-" * 56)
    print("single-storage event ceiling (~): ", count)
    print("MAX_LOOP_EVENTS (per loop):       ", cfg.MAX_LOOP_EVENTS)
    print("worst-case 4-loop total now:      ", cfg.MAX_LOOP_EVENTS * NUM_SLOTS)
    storage.clear()
    gc.collect()
    print("free after cleanup:   ", _fmt(_mem()))


def main():
    if _mem() is None:
        print("gc.mem_free() unavailable - run this ON THE DEVICE (CircuitPython).")
        return
    print("LumaFader record-mode memory report")
    print("MAX_LOOP_EVENTS=%d  MAX_LOOP_MS=%d  MEMORY_CRITICAL_THRESHOLD=%d"
          % (cfg.MAX_LOOP_EVENTS, cfg.MAX_LOOP_MS, cfg.MEMORY_CRITICAL_THRESHOLD))
    t0 = time.monotonic()
    mgr = phase_a_fill_all_slots()
    phase_b_raw_ceiling()
    # release the phase-A loops only after phase B (so phase A's RAM is held
    # while we report it).
    for slot in range(NUM_SLOTS):
        mgr.delete_loop(slot)
    gc.collect()
    _banner("DONE  (%.1fs)  free now: %s" % (time.monotonic() - t0, _fmt(_mem())))


main()
