import digitalio
import time
from adafruit_debouncer import Debouncer
import constants as cfg

class MidiSlider:
    def __init__(self, analog_pin, slider_index):
        self.analog_pin = analog_pin
        self.current_value = 0
        self.cc_value = 0
        self.cc_value_changed = False
        self.index = slider_index
        self.current_assigned_cc_number = -1
        self.additional_assigned_cc_numbers = []
        self.crossing_cc_value = -1        # Set this whenever bank changes (last CC value sent).
        self.has_crossed_last_cc_value = False

        # Adaptive Smoothing State
        self.adaptive_state = "CHANGING"  # "STABLE" or "CHANGING"
        self.adaptive_last_cc_sent = -1  # Initialize to invalid value to force first send
        self.adaptive_last_cc_send_time = time.monotonic()  # Track when we last sent a CC
        self.adaptive_smoothed_raw = 0  # Exponentially smoothed raw value

    def update(self):
        """Read analog, apply adaptive smoothing, calculate CC. Return True if changed."""
        self.current_value = 65536 - self.analog_pin.value

        # Apply exponential smoothing to the raw value
        if self.adaptive_smoothed_raw == 0:  # Initialize on first read
            self.adaptive_smoothed_raw = self.current_value
        else:
            self.adaptive_smoothed_raw = (
                cfg.ADAPTIVE_SMOOTHING_FACTOR * self.current_value
                + (1 - cfg.ADAPTIVE_SMOOTHING_FACTOR) * self.adaptive_smoothed_raw
            )

        # Convert smoothed raw value to CC
        adaptive_cc_value = int(self.adaptive_smoothed_raw / cfg.ADAPTIVE_RAW_TO_CC_DIVISOR)
        adaptive_cc_value = max(0, min(127, adaptive_cc_value))  # Clamp to valid range

        # Update adaptive state and check if we should send CC
        if self._update_adaptive_state(adaptive_cc_value):
            self.cc_value = adaptive_cc_value
            self.cc_value_changed = True
            self.adaptive_last_cc_sent = adaptive_cc_value
            self.adaptive_last_cc_send_time = time.monotonic()
        else:
            self.cc_value_changed = False

        return self.cc_value_changed

    def _update_adaptive_state(self, cc_value):
        """Update adaptive state; return True if CC should be sent."""
        current_time = time.monotonic()

        # Determine threshold based on current state
        if self.adaptive_state == "STABLE":
            threshold = cfg.ADAPTIVE_STABLE_THRESHOLD_CC
        else:
            threshold = cfg.ADAPTIVE_MOVING_THRESHOLD_CC

        # Check if we should send CC message
        cc_diff = abs(cc_value - self.adaptive_last_cc_sent)
        should_send_cc = cc_diff >= threshold

        # State machine logic - base transitions on actual CC message activity
        if self.adaptive_state == "CHANGING":
            # Switch to STABLE only if we haven't sent a CC message for the hold duration
            time_since_last_cc = current_time - self.adaptive_last_cc_send_time
            if time_since_last_cc >= cfg.ADAPTIVE_HOLD_DURATION:
                self.adaptive_state = "STABLE"
        elif self.adaptive_state == "STABLE":
            # Switch to CHANGING immediately when we need to send a CC message
            if should_send_cc:
                self.adaptive_state = "CHANGING"

        return should_send_cc

class BankButton:
    def __init__(self, digital_pin):
        self.digital_pin = digital_pin
        self.digital_pin.direction = digitalio.Direction.INPUT
        self.digital_pin.pull = digitalio.Pull.UP
        self.button = Debouncer(self.digital_pin)
        self._last_press_time = 0
        self._hold_time = 0
        self._is_long_held = False
        self._was_long_held = False
        self._double_press_detected = False
        self._last_release_time = 0
        self.detected_new_release = False
        self.detected_new_press = False

    def update(self):
        """Update button state; detect presses, releases, holds, double-press. Return True if changed."""
        self.button.update()
        state_changed = False
        self.detected_new_release = False
        self.detected_new_press = False
        self._double_press_detected = False
        self._was_long_held = False
        current_time = time.monotonic()

        new_press = self.button.fell
        new_release = self.button.rose
        currently_pressed = not self.button.value

        # Button just pressed
        if new_press:
            if (current_time - self._last_press_time) <= cfg.DOUBLE_PRESS_TIME:
                self._double_press_detected = True
            else:
                self._double_press_detected = False
            self._last_press_time = current_time
            self._hold_time = 0.01
            state_changed = True
            self.detected_new_press = True

        elif new_release:
            self._hold_time = 0
            self._last_release_time = current_time
            state_changed = True
            self.detected_new_release = True
            self._was_long_held = self._is_long_held
            self._is_long_held = False

        # Button state did not change
        else:
            if currently_pressed:
                self._hold_time = current_time - self._last_press_time
                if self._hold_time >= cfg.LONG_HOLD_THRESH_S and not self._is_long_held:
                    self._is_long_held = True
            else:
                self._hold_time = 0
                self._is_long_held = False
                self._double_press_detected = False

        return state_changed

    @property
    def pressed(self):
        """True if button is currently pressed."""
        return not self.button.value

    @property
    def hold_time(self):
        """Duration button has been held (seconds)."""
        return self._hold_time

    @property
    def was_long_held(self):
        """True if held longer than LONG_HOLD_THRESH_S before last release."""
        return self._was_long_held

    @property
    def was_double_pressed(self):
        """True if double-press detected since last press."""
        return self._double_press_detected