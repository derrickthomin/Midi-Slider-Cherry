"""
SliderWiggleDetector - Mapping Mode wiggle gesture (on-device MIDI learn)
==========================================================================
A "wiggle" is one slider passing through both extreme zones, 3 alternating
zone-entries within a time window. Pure logic, no hardware imports, so it
can be unit-tested off-device by feeding (cc_value, now) samples.
"""

import constants as cfg


class SliderWiggleDetector:
    """Tracks one slider's wiggle gesture.

    arm(cc_value, now) seeds the detector from the slider's current
    position: if it's already inside a zone, that counts as hit 1 (timer
    starts then). update(cc_value, now) feeds a new sample and returns True
    the instant the 3rd alternating zone-entry lands within
    MAPPING_WIGGLE_WINDOW_S of the 1st hit. If the window expires before 3
    hits, the detector re-seeds from the current sample.
    """

    def __init__(self):
        self._hits = 0
        self._first_hit_time = 0.0
        self._last_zone = None  # "LOW", "HIGH", or None

    @staticmethod
    def _zone_for(cc_value):
        if cc_value <= cfg.MAPPING_LOW_THRESH:
            return "LOW"
        if cc_value >= cfg.MAPPING_HIGH_THRESH:
            return "HIGH"
        return None

    def arm(self, cc_value, now):
        """Seed the detector from the slider's current position."""
        zone = self._zone_for(cc_value)
        if zone is not None:
            self._hits = 1
            self._first_hit_time = now
            self._last_zone = zone
        else:
            self._hits = 0
            self._first_hit_time = 0.0
            self._last_zone = None

    def disarm(self):
        """Clear all state back to idle."""
        self._hits = 0
        self._first_hit_time = 0.0
        self._last_zone = None

    def update(self, cc_value, now):
        """Feed a new (cc_value, now) sample.

        Returns:
            bool: True the instant the wiggle completes (3rd alternating
                zone-entry within the window).
        """
        if self._hits > 0 and (now - self._first_hit_time) > cfg.MAPPING_WIGGLE_WINDOW_S:
            self.arm(cc_value, now)
            return False

        zone = self._zone_for(cc_value)
        if zone is None or zone == self._last_zone:
            return False

        if self._hits == 0:
            self._hits = 1
            self._first_hit_time = now
            self._last_zone = zone
            return False

        self._hits += 1
        self._last_zone = zone
        return self._hits >= cfg.MAPPING_WIGGLE_HITS
