# Mapping Mode wiggle detector: 3 alternating zone-entries in a time window.
# Pure logic, unit-testable. Zones: low (<=MAPPING_LOW_THRESH), high (>=MAPPING_HIGH_THRESH).

import constants as cfg


class SliderWiggleDetector:

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
        """Seed detector from slider's current position."""
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
        """Reset to idle."""
        self._hits = 0
        self._first_hit_time = 0.0
        self._last_zone = None

    def update(self, cc_value, now):
        """Feed sample; return True when wiggle completes (3 alternating zone-entries within window)."""
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
