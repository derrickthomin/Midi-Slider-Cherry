import analogio
import digitalio
import board
import time
from adafruit_debouncer import Button, Debouncer
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

    def update(self):
        """
        Reads the current analog value, applies smoothing, and calculates the resulting CC value.
        Sets cc_value_changed to True if the new CC value is different from the old one.

        Returns:
            bool: True if cc_value_changed, otherwise False.
        """
        self.current_value = 65536 - self.analog_pin.value
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