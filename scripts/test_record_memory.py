"""
LumaFader - Record Mode Memory Budget Report (ON-DEVICE)
========================================================
Sizes the *new* "4 pads per bank" record model. Old model: 4 global pads
shared across every CC set. New model: each CC set (1 global + 4 banks per
page = NUM_RECORD_CC_SETS sets) gets its own 4 pads, so up to
NUM_RECORD_CC_SETS * 4 pads can hold loops at once. Only pads you record
into cost RAM, so the real limit is a pure RAM budget:

    free_ram - safety_floor  >=  sum_over_pads( per_pad_overhead + bytes_per_event * events )

To pick "how many pads" and "how many events per pad" we need three measured
numbers, not just the old "fill 4 pads and see":
    F  = usable free RAM in this context
    O  = fixed overhead of one allocated pad (object + empty arrays + the
         per-(cc,ch) dicts a real 4-slider recording fills in)
    b  = amortized bytes per recorded event (incl. array realloc slack)
Everything else (max pads, max events/pad, dynamic shared cap) is arithmetic
on those three, which this script measures and then tabulates.

This MUST run on the Pico (CircuitPython) - gc.mem_free() only returns real
numbers there. Off-device CPython has no gc.mem_free(), so the script exits.

How to run on the device:
    1. Open the serial REPL (e.g. screen / the Mu/Thonny REPL / `tio`).
    2. Press Ctrl-C to stop code.py and drop to the REPL.
    3. >>> import test_record_memory
    (re-run with: >>> import supervisor; supervisor.reload())

Phases:
  A  Per-pad fixed overhead O  - allocate empty 4-slider pads, diff RAM.
  B  Bytes per event b         - fill one pad, diff RAM over a known event
                                 delta (cancels object overhead).
  C  Realistic multi-pad fill  - emulate the new model: keep adding 4-slider
                                 pads filled to PAD_FILL_EVENTS until the
                                 memory floor; reports how many pads survive.
  E  Random real-world fill    - each new pad gets a RANDOM event count
                                 (250-1500) until the floor; reports total
                                 pads handled. Re-run to build a distribution.
  F  Churn fragmentation       - delete/re-record pads over many cycles and
                                 probe the largest contiguous block vs total
                                 free; the gap is fragmentation. Decides whether
                                 storage pre-sizing is needed (plan 4a).
  D  Tradeoff table            - from F, O, b: max events/pad for a range of
                                 pad counts, plus a dynamic shared-pool total.

Tweak the CONFIG block below and re-run to explore different per-pad sizes.
"""

import gc
import random
import time

import constants as cfg
from looper import MidiLoop, ArrayBasedCCStorage
from loopmanager import LoopManager, NUM_SLOTS
from settings import settings

# ----------------------------- CONFIG -----------------------------
# Sliders recorded per pad. A LumaFader bank is 4 faders, so a real pad
# captures up to 4 distinct (cc, channel) streams -> 4 keys in each cache dict.
SLIDERS_PER_PAD = 4

# Per-pad event target for the realistic fill (Phase C). This is "events for
# the WHOLE pad" (all sliders combined), matching how MAX_LOOP_EVENTS is
# counted. Set below MAX_LOOP_EVENTS to model smaller loops, or to
# MAX_LOOP_EVENTS to model worst-case full loops.
PAD_FILL_EVENTS = 1500

# How many empty pads to allocate when measuring fixed overhead (Phase A).
OVERHEAD_SAMPLE_PADS = 12

# Event delta used to measure bytes/event (Phase B). Larger = less noise.
BYTES_PER_EVENT_DELTA = 2000

# Pad counts to tabulate in the tradeoff table (Phase D).
PAD_COUNTS = (4, 8, 12, 16, 20, 24, 32, NUM_SLOTS * cfg.NUM_RECORD_CC_SETS)

# Max pads any one set can hold (the controller's per-set pad count).
PADS_PER_SET = NUM_SLOTS

# Random per-pad event range for the real-world simulation (Phase E). Each
# new pad gets a random size in [RANDOM_MIN_EVENTS, RANDOM_MAX_EVENTS] to
# model that users record loops of varying length. Re-run to resample.
RANDOM_MIN_EVENTS = 250
RANDOM_MAX_EVENTS = 1500

# Churn simulation (Phase F). Models real use: record some pads, then over many
# cycles delete a random subset and re-record them at new random sizes. This is
# the worst case for heap fragmentation (create/delete/create), which the
# grow-only phases never exercise. CHURN_POOL_PADS pads are kept live; each
# cycle deletes ~CHURN_DELETE_FRACTION of them and re-records.
CHURN_POOL_PADS = 12
CHURN_CYCLES = 40
CHURN_DELETE_FRACTION = 0.4

# Free-RAM reserve to keep AT ALL TIMES (Phase D budgeting). gc.mem_free()
# reports total free, but array-growth reallocs need a CONTIGUOUS block, so
# the heap fragments and MemoryError fires well above 0 free. On-device runs
# crashed with ~38 KB nominally free, so the real safe floor is far higher
# than MEMORY_CRITICAL_THRESHOLD (15000). Keep a fat reserve. Tune from the
# Phase C crash point: reserve >= crash_free + a couple array-growth cycles.
SAFE_FREE_FLOOR = 50000
# -------------------------------------------------------------------


def _mem():
    try:
        return gc.mem_free()
    except AttributeError:
        return None


def _fmt(n):
    return "n/a" if n is None else str(n)


def _banner(title):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def _fill_pad(loop, target_events, midi_channel_base=0):
    """Record `target_events` events into `loop` spread across SLIDERS_PER_PAD
    distinct (cc, channel) streams, via the normal add_cc path (respects
    MAX_LOOP_EVENTS / the memory floor). Returns events actually recorded."""
    i = 0
    while loop.count_events() < target_events and not loop.max_events_reached:
        slider = i % SLIDERS_PER_PAD
        # distinct cc per slider; value varies so the change-cache keeps it
        loop.add_cc(20 + slider, i % 128, midi_channel=midi_channel_base + slider)
        i += 1
        if i > cfg.MAX_LOOP_EVENTS + 500:
            break  # safety
    return loop.count_events()


def _largest_contiguous_block():
    """Probe the largest single contiguous block we can allocate right now, in
    bytes. gc.mem_free() reports TOTAL free; this reports the biggest CHUNK,
    which is what an array realloc actually needs. The gap between the two IS
    the fragmentation. Binary-searches an array('B', bytes(n)) allocation.
    Returns the largest n that succeeded (approx, to ~256 bytes)."""
    if _mem() is None:
        return None
    gc.collect()
    # Upper bound: can't exceed total free. Grow lo by doubling, then bisect.
    lo = 0
    hi = 256
    ceiling = _mem()
    # find an hi that FAILS (or caps at total free)
    while hi < ceiling:
        try:
            b = bytearray(hi)
            del b
            lo = hi
            hi *= 2
        except MemoryError:
            break
    # bisect between lo (ok) and hi (fail)
    while hi - lo > 256:
        mid = (lo + hi) // 2
        try:
            b = bytearray(mid)
            del b
            lo = mid
        except MemoryError:
            hi = mid
    gc.collect()
    return lo


def phase_a_pad_overhead():
    """Measure O: RAM cost of one allocated pad with empty event storage but
    realistic per-(cc,ch) cache dicts (SLIDERS_PER_PAD keys), no events."""
    _banner("PHASE A - fixed overhead per allocated pad (O)")
    gc.collect()
    before = _mem()
    print("free before:          ", _fmt(before))

    pads = []
    for _ in range(OVERHEAD_SAMPLE_PADS):
        loop = MidiLoop(loop_type="loop", cc_set_idx=0)
        loop.toggle_record_state(True)
        # Seed the caches/dicts as a real recording would (first value per
        # slider) without growing the event arrays meaningfully.
        for slider in range(SLIDERS_PER_PAD):
            loop._first_cc_values[(20 + slider, slider)] = 0
            loop._last_cc_values[(20 + slider, slider)] = 0
        pads.append(loop)

    gc.collect()
    after = _mem()
    print("free after %2d pads:    %s" % (OVERHEAD_SAMPLE_PADS, _fmt(after)))
    o_per_pad = None
    if before is not None and after is not None:
        used = before - after
        o_per_pad = used / OVERHEAD_SAMPLE_PADS
        print("RAM for %d empty pads: %d bytes" % (OVERHEAD_SAMPLE_PADS, used))
        print("overhead per pad (O):  %.1f bytes" % o_per_pad)
    # release
    for p in pads:
        p.clear()
    pads = None
    gc.collect()
    return o_per_pad


def phase_b_bytes_per_event():
    """Measure b: amortized bytes per recorded event, by diffing RAM across a
    known event delta on a single pad (object overhead cancels out)."""
    _banner("PHASE B - bytes per recorded event (b)")
    settings.settings["CC_RESOLUTION"] = 0
    settings.settings["TRIM_SILENCE"] = False

    loop = MidiLoop(loop_type="loop", cc_set_idx=0)
    loop.toggle_record_state(True)

    # Prime past the early small-array reallocs so we measure steady state.
    _fill_pad(loop, 200)
    gc.collect()
    before = _mem()
    n0 = loop.count_events()

    # add_cc self-limits at MAX_LOOP_EVENTS; target a delta below the cap.
    target = min(n0 + BYTES_PER_EVENT_DELTA, cfg.MAX_LOOP_EVENTS)
    _fill_pad(loop, target)
    gc.collect()
    after = _mem()
    n1 = loop.count_events()

    b = None
    delta = n1 - n0
    print("events %d -> %d (delta %d)" % (n0, n1, delta))
    print("free %s -> %s" % (_fmt(before), _fmt(after)))
    if before is not None and after is not None and delta > 0:
        used = before - after
        b = used / delta
        print("bytes / event (b):     %.3f" % b)
    loop.clear()
    loop = None
    gc.collect()
    return b


def phase_c_realistic_fill():
    """Emulate the new model: keep allocating 4-slider pads filled to
    PAD_FILL_EVENTS until the memory floor. Shows how many real-sized pads
    actually coexist and where the floor bites."""
    _banner("PHASE C - realistic multi-pad fill (%d events/pad, %d sliders)"
            % (PAD_FILL_EVENTS, SLIDERS_PER_PAD))
    settings.settings["CC_RESOLUTION"] = 0
    settings.settings["TRIM_SILENCE"] = False

    gc.collect()
    start_free = _mem()
    print("free at start:        ", _fmt(start_free))
    print("memory floor:         ", cfg.MEMORY_CRITICAL_THRESHOLD)

    max_pads = NUM_SLOTS * cfg.NUM_RECORD_CC_SETS
    pads = []
    total_events = 0
    stopped_reason = "reached max possible pads (%d)" % max_pads
    crash_free = None  # gc.mem_free() reading just before a MemoryError

    for pad_idx in range(max_pads):
        gc.collect()
        # IMPORTANT: gc.mem_free() reports TOTAL free, not the largest
        # contiguous block. Array growth reallocs need a contiguous block, so
        # MemoryError can fire with tens of KB nominally free (heap
        # fragmentation). We catch it and treat that as the true ceiling.
        try:
            loop = MidiLoop(loop_type="loop", cc_set_idx=0)
            loop.toggle_record_state(True)
            recorded = _fill_pad(loop, PAD_FILL_EVENTS)
            loop.toggle_record_state(False)
        except MemoryError:
            crash_free = _mem()
            stopped_reason = ("MemoryError allocating pad %d (fragmentation) - "
                              "%s bytes nominally free" % (pad_idx + 1, _fmt(crash_free)))
            loop = None
            gc.collect()
            break
        pads.append(loop)
        total_events += recorded
        gc.collect()
        free = _mem()
        print("  pad %2d  events=%4d  cum_events=%6d  free=%s%s"
              % (pad_idx + 1, recorded, total_events, _fmt(free),
                 "  <-- SHORT FILL" if recorded < PAD_FILL_EVENTS else ""))
        if loop.max_events_reached and recorded < PAD_FILL_EVENTS:
            stopped_reason = "memory floor hit mid-fill at pad %d" % (pad_idx + 1)
            break

    print("-" * 60)
    print("pads that fully filled:", len(pads))
    print("total events held:    ", total_events)
    print("stop reason:          ", stopped_reason)
    if start_free is not None:
        gc.collect()
        end_free = _mem()
        used = start_free - end_free
        print("RAM used (settled):   ", used, "bytes")
    if crash_free is not None:
        print("*** Fragmentation ceiling: died with %d bytes free but no"
              % crash_free)
        print("    contiguous block. Usable RAM << gc.mem_free(). The")
        print("    MEMORY_CRITICAL_THRESHOLD (%d) floor is too low to catch this."
              % cfg.MEMORY_CRITICAL_THRESHOLD)
    # release after reporting
    for p in pads:
        p.clear()
    pads = None
    gc.collect()


def phase_e_random_fill():
    """Real-world simulation: each new pad records a RANDOM number of events
    in [RANDOM_MIN_EVENTS, RANDOM_MAX_EVENTS], modeling loops of varying
    length. Keep adding pads until a MemoryError / floor stops us, then report
    how many pads and total events the device actually handled. Run this
    repeatedly (supervisor.reload()) to build a distribution."""
    _banner("PHASE E - random real-world fill (%d-%d events/pad)"
            % (RANDOM_MIN_EVENTS, RANDOM_MAX_EVENTS))
    settings.settings["CC_RESOLUTION"] = 0
    settings.settings["TRIM_SILENCE"] = False

    gc.collect()
    start_free = _mem()
    print("free at start:        ", _fmt(start_free))

    max_pads = NUM_SLOTS * cfg.NUM_RECORD_CC_SETS
    pads = []
    total_events = 0
    short_fills = 0
    stopped_reason = "reached max possible pads (%d)" % max_pads
    crash_free = None

    for pad_idx in range(max_pads):
        gc.collect()
        target = random.randint(RANDOM_MIN_EVENTS, RANDOM_MAX_EVENTS)
        try:
            loop = MidiLoop(loop_type="loop", cc_set_idx=0)
            loop.toggle_record_state(True)
            recorded = _fill_pad(loop, target)
            loop.toggle_record_state(False)
        except MemoryError:
            crash_free = _mem()
            stopped_reason = ("MemoryError on pad %d (fragmentation) - %s bytes "
                              "nominally free" % (pad_idx + 1, _fmt(crash_free)))
            loop = None
            gc.collect()
            break
        pads.append(loop)
        total_events += recorded
        gc.collect()
        free = _mem()
        short = recorded < target
        if short:
            short_fills += 1
        print("  pad %2d  target=%4d  events=%4d  cum_events=%6d  free=%s%s"
              % (pad_idx + 1, target, recorded, total_events, _fmt(free),
                 "  <-- SHORT (floor)" if short else ""))
        if loop.max_events_reached and short:
            stopped_reason = "memory floor hit mid-fill at pad %d" % (pad_idx + 1)
            break

    print("-" * 60)
    print("PADS HANDLED:         ", len(pads))
    print("total events held:    ", total_events)
    if pads:
        print("avg events/pad:        %d" % (total_events // len(pads)))
    print("short (floor-capped):  %d" % short_fills)
    print("stop reason:          ", stopped_reason)
    if start_free is not None:
        gc.collect()
        print("RAM used (settled):   ", start_free - _mem(), "bytes")
    if crash_free is not None:
        print("(fragmentation: %d bytes free at crash)" % crash_free)
    for p in pads:
        p.clear()
    pads = None
    gc.collect()


def phase_f_churn():
    """Fragmentation stress: keep CHURN_POOL_PADS pads live, then over
    CHURN_CYCLES cycles delete a random subset and re-record them at new random
    sizes - the create/delete/create pattern the grow-only phases never hit.
    After churn, probe the largest contiguous block and compare it to total
    free; the GAP is the fragmentation. If the largest block stays well above a
    full GUARANTEED loop (~7.5 KB), churn is a non-issue and the simple
    grow-as-you-go shared pool is safe. If it collapses, pre-sizing is needed."""
    _banner("PHASE F - delete/re-record churn fragmentation (%d pads, %d cycles)"
            % (CHURN_POOL_PADS, CHURN_CYCLES))
    settings.settings["CC_RESOLUTION"] = 0
    settings.settings["TRIM_SILENCE"] = False

    gc.collect()
    start_free = _mem()
    start_block = _largest_contiguous_block()
    print("free at start:         %s" % _fmt(start_free))
    print("largest block at start:%s" % _fmt(start_block))

    guaranteed_bytes = RANDOM_MAX_EVENTS * 5  # ~one full loop's contiguous need
    pads = [None] * CHURN_POOL_PADS
    n_delete = max(1, int(CHURN_POOL_PADS * CHURN_DELETE_FRACTION))
    min_block = start_block if start_block is not None else 0
    crashed = False
    last_cycle = -1

    def _make(target):
        loop = MidiLoop(loop_type="loop", cc_set_idx=0)
        loop.toggle_record_state(True)
        _fill_pad(loop, target)
        loop.toggle_record_state(False)
        return loop

    try:
        # Initial fill
        for i in range(CHURN_POOL_PADS):
            pads[i] = _make(random.randint(RANDOM_MIN_EVENTS, RANDOM_MAX_EVENTS))

        for cycle in range(CHURN_CYCLES):
            last_cycle = cycle
            # delete a random subset
            victims = []
            idxs = list(range(CHURN_POOL_PADS))
            for _ in range(n_delete):
                v = idxs.pop(random.randint(0, len(idxs) - 1))
                victims.append(v)
            for v in victims:
                if pads[v] is not None:
                    pads[v].clear()
                    pads[v] = None
            gc.collect()
            # re-record them at new random sizes
            for v in victims:
                pads[v] = _make(random.randint(RANDOM_MIN_EVENTS, RANDOM_MAX_EVENTS))
            gc.collect()

            block = _largest_contiguous_block()
            free = _mem()
            if block is not None and block < min_block:
                min_block = block
            if cycle % 5 == 0 or cycle == CHURN_CYCLES - 1:
                gap = (free - block) if (free is not None and block is not None) else None
                print("  cycle %2d  free=%s  largest_block=%s  gap(frag)=%s"
                      % (cycle, _fmt(free), _fmt(block), _fmt(gap)))
    except MemoryError:
        crashed = True
        print("  *** MemoryError during churn at cycle ~%d, free=%s"
              % (last_cycle, _fmt(_mem())))

    gc.collect()
    end_free = _mem()
    end_block = _largest_contiguous_block()
    print("-" * 60)
    print("crashed during churn:  %s" % crashed)
    print("free at end:           %s" % _fmt(end_free))
    print("largest block at end:  %s" % _fmt(end_block))
    print("WORST largest block:   %s  (lowest seen across churn)" % _fmt(min_block))
    if end_free is not None and end_block is not None:
        print("end fragmentation gap: %d bytes (free - largest_block)"
              % (end_free - end_block))
    print("full-loop need (~):    %d bytes (%d events * 5)"
          % (guaranteed_bytes, RANDOM_MAX_EVENTS))
    if min_block is not None:
        verdict = ("OK - churn safe, grow-as-you-go fine"
                   if min_block > guaranteed_bytes * 1.5
                   else "WARNING - churn shrinks contiguous space near/below a "
                        "full loop; pre-sizing recommended (plan 4a)")
        print("VERDICT:               %s" % verdict)
    for p in pads:
        if p is not None:
            p.clear()
    pads = None
    gc.collect()


def phase_d_tradeoff(o_per_pad, b):
    """Turn the measured numbers into a pads vs events/pad table plus a
    dynamic shared-pool figure."""
    _banner("PHASE D - tradeoff table")
    gc.collect()
    free = _mem()
    print("free now:             ", _fmt(free))
    print("hard floor (crash):    %d  (MEMORY_CRITICAL_THRESHOLD - too low, see Phase C)"
          % cfg.MEMORY_CRITICAL_THRESHOLD)
    print("SAFE_FREE_FLOOR used:  %d  (fragmentation reserve)" % SAFE_FREE_FLOOR)
    if free is None or o_per_pad is None or b is None:
        print("(missing a measurement - cannot tabulate)")
        return

    budget = free - SAFE_FREE_FLOOR
    print("usable budget:         %d bytes  (free - SAFE_FREE_FLOOR)" % budget)
    print("overhead/pad (O):      %.1f bytes" % o_per_pad)
    print("bytes/event (b):       %.3f bytes" % b)
    print("est. ms per event:     ~ (loop_ms / events) - depends on fader activity")
    print("-" * 60)
    print("STATIC per-pad cap (every pad sized equally, all allocated):")
    print("  %-6s %-14s %-16s" % ("pads", "max ev/pad", "~per-pad note"))
    for p in PAD_COUNTS:
        avail = budget - p * o_per_pad
        if avail <= 0:
            print("  %-6d %-14s (overhead alone exceeds budget)" % (p, "0"))
            continue
        ev_per_pad = int(avail / b / p)
        capped = min(ev_per_pad, cfg.MAX_LOOP_EVENTS)
        note = ""
        if ev_per_pad > cfg.MAX_LOOP_EVENTS:
            note = "RAM allows >%d; capped by MAX_LOOP_EVENTS" % cfg.MAX_LOOP_EVENTS
        print("  %-6d %-14d %s" % (p, capped, note))

    print("-" * 60)
    print("DYNAMIC shared pool (one event budget, any distribution across the")
    print("16 pads you actually use; pads cost O only when allocated):")
    for allocated in (16, NUM_SLOTS * cfg.NUM_RECORD_CC_SETS):
        avail = budget - allocated * o_per_pad
        total_ev = int(avail / b) if avail > 0 else 0
        print("  if %2d pads allocated: %d total events to share"
              % (allocated, total_ev))
    print("-" * 60)
    print("Target check: 16 pads ->")
    avail16 = budget - 16 * o_per_pad
    if avail16 > 0:
        print("  even split:  %d events/pad" % int(avail16 / b / 16))
        print("  shared pool: %d events total" % int(avail16 / b))
    else:
        print("  16 pads' overhead alone exceeds budget")


def main():
    if _mem() is None:
        print("gc.mem_free() unavailable - run this ON THE DEVICE (CircuitPython).")
        return
    print("LumaFader record-mode memory budget report")
    print("MAX_LOOP_EVENTS=%d  MAX_LOOP_MS=%d  MEMORY_CRITICAL_THRESHOLD=%d"
          % (cfg.MAX_LOOP_EVENTS, cfg.MAX_LOOP_MS, cfg.MEMORY_CRITICAL_THRESHOLD))
    print("NUM_RECORD_CC_SETS=%d  PADS_PER_SET=%d  -> up to %d pads possible"
          % (cfg.NUM_RECORD_CC_SETS, PADS_PER_SET,
             cfg.NUM_RECORD_CC_SETS * PADS_PER_SET))
    print("SLIDERS_PER_PAD=%d  PAD_FILL_EVENTS=%d"
          % (SLIDERS_PER_PAD, PAD_FILL_EVENTS))
    t0 = time.monotonic()

    o_per_pad = phase_a_pad_overhead()
    b = phase_b_bytes_per_event()
    phase_c_realistic_fill()
    phase_e_random_fill()
    phase_f_churn()
    phase_d_tradeoff(o_per_pad, b)

    gc.collect()
    _banner("DONE  (%.1fs)  free now: %s"
            % (time.monotonic() - t0, _fmt(_mem())))


main()
