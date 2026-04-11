import analogio
import digitalio
import time
from adafruit_debouncer import Debouncer
import constants as cfg

class MidiSlider:
    def __init__(self, analog_pin, slider_index):
        """
        Represents a single MIDI slider with smoothing logic and CC value handling.

        Args:
            analog_pin (analogio.AnalogIn): The analog pin attached to the slider.
            slider_index (int): The index of this slider.
        """
        self.analog_pin = analog_pin
        self.last_value = 0
        self.current_value = 0
        self.smoothed_value = 0
        self.cc_value = 0
        self.last_cc_value = -1
        self.cc_value_changed = False
        self.index = slider_index
        self.current_assigned_cc_number = -1
        self.additional_assigned_cc_numbers = []
        self.crossing_cc_value = -1        # Set this whenever bank changes (last CC value sent).
        self.has_crossed_last_cc_value = False

        # Smoothing factors
        self.slow_smoothing_factor = cfg.SLOW_SMOOTHING_FACTOR
        self.fast_smoothing_factor = cfg.FAST_SMOOTHING_FACTOR
        self.movement_threshold = cfg.MOVEMENT_THRESHOLD

        # Middle Range Noise Reduction
        self.middle_range_start = cfg.MIDDLE_RANGE_START
        self.middle_range_end = cfg.MIDDLE_RANGE_END
        self.middle_range_smoothing_factor = cfg.MIDDLE_RANGE_SMOOTHING_FACTOR

        # CC Threshold
        self.cc_threshold = cfg.CC_THRESHOLD

        # Adaptive Smoothing State
        self.adaptive_enabled = True
        self.adaptive_state = "CHANGING"  # "STABLE" or "CHANGING"
        self.adaptive_buffer = []  # Circular buffer for recent CC values
        self.adaptive_last_state_change = time.monotonic()
        self.adaptive_last_cc_sent = -1  # Initialize to invalid value to force first send
        self.adaptive_last_cc_send_time = time.monotonic()  # Track when we last sent a CC
        self.adaptive_smoothed_raw = 0  # Exponentially smoothed raw value

    def update(self):
        """
        Reads the current analog value, applies smoothing, and calculates the resulting CC value.
        Sets cc_value_changed to True if the new CC value is different from the old one.

        Returns:
            bool: True if cc_value_changed, otherwise False.
        """
        self.current_value = 65536 - self.analog_pin.value
        
        # Apply exponential smoothing to raw values for adaptive smoothing
        if self.adaptive_enabled:
            if self.adaptive_smoothed_raw == 0:  # Initialize on first read
                self.adaptive_smoothed_raw = self.current_value
            else:
                self.adaptive_smoothed_raw = (
                    cfg.ADAPTIVE_SMOOTHING_FACTOR * self.current_value
                    + (1 - cfg.ADAPTIVE_SMOOTHING_FACTOR) * self.adaptive_smoothed_raw
                )
            
            # Convert smoothed raw value to CC for adaptive logic
            adaptive_cc_value = int(self.adaptive_smoothed_raw / cfg.ADAPTIVE_RAW_TO_CC_DIVISOR)
            adaptive_cc_value = max(0, min(127, adaptive_cc_value))  # Clamp to valid range
            
            # Update adaptive state and check if we should send CC
            cc_should_update = self._update_adaptive_state(adaptive_cc_value)
            if cc_should_update:
                self.cc_value = adaptive_cc_value
                self.cc_value_changed = True
                self.adaptive_last_cc_sent = adaptive_cc_value
                self.adaptive_last_cc_send_time = time.monotonic()
            else:
                self.cc_value_changed = False
        else:
            # Original smoothing logic (fallback)
            value_difference = abs(self.current_value - self.last_value)
            smoothing_factor = self.get_smoothing_factor(value_difference)
            self.smoothed_value = (
                smoothing_factor * self.current_value
                + (1 - smoothing_factor) * self.smoothed_value
            )

            calculated_cc_value = int(self.smoothed_value / 512)

            if calculated_cc_value != self.cc_value:
                self.cc_value = calculated_cc_value
                self.cc_value_changed = True
                # Keep adaptive state in sync when not using adaptive smoothing
                self.adaptive_last_cc_sent = calculated_cc_value
                self.adaptive_last_cc_send_time = time.monotonic()
            else:
                self.cc_value_changed = False

        self.last_value = self.current_value
        return self.cc_value_changed

    def get_smoothing_factor(self, value_difference):
        """
        Calculates the smoothing factor based on the value difference and the current value.

        If value_difference exceeds movement_threshold, returns fast_smoothing_factor;
        otherwise, returns slow_smoothing_factor. If current_value is within the 
        [middle_range_start, middle_range_end] range, the factor is limited to 
        middle_range_smoothing_factor.

        Args:
            value_difference (float): Absolute difference between current and previous values.

        Returns:
            float: The calculated smoothing factor.
        """
        if value_difference > self.movement_threshold:
            factor = self.fast_smoothing_factor
        else:
            factor = self.slow_smoothing_factor

        if self.middle_range_start <= self.current_value <= self.middle_range_end:
            factor = min(factor, self.middle_range_smoothing_factor)

        return factor

    def _update_adaptive_state(self, cc_value):
        """
        Updates the adaptive smoothing state and determines if a CC message should be sent.
        
        Args:
            cc_value (int): Current CC value (0-127)
            
        Returns:
            bool: True if a CC message should be sent, False otherwise
        """
        current_time = time.monotonic()
        
        # Add current CC value to buffer
        self.adaptive_buffer.append(cc_value)
        if len(self.adaptive_buffer) > cfg.ADAPTIVE_BUFFER_SIZE:
            self.adaptive_buffer.pop(0)
        
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
                self.adaptive_last_state_change = current_time
        elif self.adaptive_state == "STABLE":
            # Switch to CHANGING immediately when we need to send a CC message
            if should_send_cc:
                self.adaptive_state = "CHANGING"
                self.adaptive_last_state_change = current_time
        
        return should_send_cc
    
    def _is_readings_stable(self):
        """
        Checks if recent readings in the buffer are stable (low variation).
        
        Returns:
            bool: True if readings are stable, False otherwise
        """
        if len(self.adaptive_buffer) < cfg.ADAPTIVE_BUFFER_SIZE:
            return False
        
        min_val = min(self.adaptive_buffer)
        max_val = max(self.adaptive_buffer)
        range_val = max_val - min_val
        
        return range_val <= cfg.ADAPTIVE_STABILITY_RANGE
    
    def set_adaptive_smoothing(self, enabled):
        """
        Enable or disable adaptive smoothing for this slider.
        
        Args:
            enabled (bool): True to enable adaptive smoothing, False to use original logic
        """
        self.adaptive_enabled = enabled
        if enabled:
            # Reset adaptive state when enabling
            self.adaptive_state = "CHANGING"
            self.adaptive_buffer = []
            self.adaptive_last_state_change = time.monotonic()
            self.adaptive_last_cc_send_time = time.monotonic()
            self.adaptive_last_cc_sent = self.cc_value

class BankButton:
    def __init__(self, digital_pin):
        """
        Represents a single bank button with state debouncing, hold/double-press detection.

        Args:
            digital_pin (digitalio.DigitalInOut): The digital pin attached to the button.
        """
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
        """
        Updates the button state and detects new presses, releases, holds, and double-press events.

        Returns:
            bool: True if the button's state changed (pressed or released), otherwise False.
        """
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
        """
        Indicates if the button is currently pressed.

        Returns:
            bool: True if pressed, otherwise False.
        """
        return not self.button.value

    @property
    def hold_time(self):
        """
        The duration for which the button has been held (if pressed).

        Returns:
            float: The current hold time in seconds.
        """
        return self._hold_time

    @property
    def is_long_held(self):
        """
        Indicates if the button was held longer than cfg.LONG_HOLD_THRESH_S.

        Returns:
            bool: True if long-held, otherwise False.
        """
        return self._is_long_held

    @property
    def was_long_held(self):
        """
        Indicates if the button had been held longer than cfg.LONG_HOLD_THRESH_S 
        prior to the last release.

        Returns:
            bool: True if it was long-held, otherwise False.
        """
        return self._was_long_held

    @property
    def was_double_pressed(self):
        """
        Indicates if a double press was detected since the last press.

        Returns:
            bool: True if double-pressed, otherwise False.
        """
        return self._double_press_detected

    @property
    def last_press_time(self):
        """
        The timestamp of the most recent button press.

        Returns:
            float: The time of the last press event, in seconds.
        """
        return self._last_press_time