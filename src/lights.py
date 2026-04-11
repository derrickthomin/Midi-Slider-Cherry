import board
import storage
import neopixel
import time
from midi import midi_manager
from settings import settings
import constants as cfg

class LightsManager:
    """
    Manages the NeoPixel LEDs on the MIDI controller.

    - Pixel index 0 is next to the bottom-left button.
    - Pixel index 4 is the bottom pixel next to slider 1.
    - Pixel index 68 is the single pixel above all of the sliders (indicator pixel).

    This class provides methods to update LEDs based on slider positions,
    button states, and other functionalities.
    """

    def __init__(self, num_pixels=69, pixel_pin=board.GP15, brightness=0.2):
        self.num_pixels = num_pixels
        self.pixel_pin = pixel_pin
        self.brightness = brightness

        # Initialize NeoPixel strip
        self.pixels = neopixel.NeoPixel(
            self.pixel_pin, self.num_pixels, brightness=self.brightness, auto_write=False
        )
        self.pixels.fill((0, 0, 0))
        self.pixels.show()

        # Button-to-pixel mapping
        self.button_pixel_indices = {
            0: 0,   # Bottom-left button
            1: 1,
            2: 2,
            3: 3,   # Buttons mapped to pixels 0-3
        }

        # Slider-to-pixel mapping
        self.slider_pixel_indices = {
            0: list(range(4, 20)),   # Slider 1 pixels (4-19) - total 16
            1: list(range(20, 36)),  # Slider 2 pixels (20-35) - total 16
            2: list(range(36, 52)),  # Slider 3 pixels (36-51) - total 16
            3: list(range(52, 68)),  # Slider 4 pixels (52-67) - total 16
        }

        # Indicator pixel above sliders
        self.indicator_pixel_index = 68

        # Multi-bank morphing state
        self.morph_start_time = 0
        self.morph_cycle_duration = 3.0  # seconds for full cycle through all colors
        self.was_multi_bank = False  # Track for snap-back detection

        # Default state
        self.clear()
        self.pixels[self.indicator_pixel_index] = cfg.REG_MODE_COLOR

    def clear(self):
        """
        Clears all the pixels (sets them to black/off).
        """
        self.pixels.fill((0, 0, 0))

    def update_slider_lights(self, sliders, bank_idx=0, bank_group_idx=0, held_button_order=None, bank_group_just_changed=False):
        """
        Updates the LEDs to reflect the current positions of the sliders.

        Args:
            sliders (list): A list of slider objects or their CC values (0-127).
            bank_idx (int): The current bank index (-1 for global).
            bank_group_idx (int): The current bank group index.
            held_button_order (list): List of button indices in press order (for multi-bank morphing).
            bank_group_just_changed (bool): Whether bank group was just changed (disables morphing).
        """
        if held_button_order is None:
            held_button_order = []
        
        # Determine the channel for looking up last sent values
        if bank_idx == -1:
            channel = settings.get_global_channel()
        else:
            channel = settings.get_resolved_channel(bank_group_idx, bank_idx)
        
        # Check for multi-bank mode and handle morphing
        # Disable morphing during bank group navigation to avoid false triggers
        is_multi_bank = len(held_button_order) > 1 and not bank_group_just_changed
        
        # Reset morph timer when entering multi-bank mode
        if is_multi_bank and not self.was_multi_bank:
            self.morph_start_time = time.monotonic()
        
        self.was_multi_bank = is_multi_bank
        
        # Get color (morphed if multi-bank, solid otherwise)
        morphed_color = self._get_morphed_color(held_button_order, bank_group_idx) if is_multi_bank else None
        
        for slider_idx, slider in enumerate(sliders):
            # Obtain the CC value (0-127)
            slider_cc_value = slider.cc_value if hasattr(slider, 'cc_value') else slider

            last_sent_cc_value = midi_manager.get_last_cc_value_sent(slider.current_assigned_cc_number, channel)
            if abs(slider_cc_value - last_sent_cc_value) > 4:
                cc_value = last_sent_cc_value
            else:
                cc_value = slider_cc_value

            num_pixels = len(self.slider_pixel_indices[slider_idx])
            lit_pixels = int((cc_value / 127) * num_pixels)
            pixel_indices = self.slider_pixel_indices[slider_idx]

            # Determine color based on bank/global/multi-bank morph
            if morphed_color is not None:
                color = morphed_color
            elif bank_idx == -1:
                color = cfg.GLOBAL_BANK_COLOR
            else:
                color = cfg.BANK_GROUPS_COLORS[bank_group_idx][bank_idx]

            # Light up pixels according to the CC value
            for i, pix_idx in enumerate(pixel_indices):
                self.pixels[pix_idx] = color if i < lit_pixels else (0, 0, 0)

    def _get_morphed_color(self, held_button_order, bank_group_idx):
        """
        Returns an interpolated color when multiple buttons are held.
        
        Args:
            held_button_order (list): Button indices in press order.
            bank_group_idx (int): Current bank group index.
            
        Returns:
            tuple: RGB color tuple, or None if not in multi-bank mode.
        """
        if len(held_button_order) <= 1:
            return None
        
        # Get all active colors in press order
        colors = [cfg.BANK_GROUPS_COLORS[bank_group_idx][idx] for idx in held_button_order]
        num_colors = len(colors)
        
        # Calculate where we are in the cycle (time-based)
        elapsed = time.monotonic() - self.morph_start_time
        cycle_progress = (elapsed % self.morph_cycle_duration) / self.morph_cycle_duration
        
        # Which color pair are we interpolating between?
        segment_duration = 1.0 / num_colors
        segment_idx = int(cycle_progress / segment_duration)
        segment_progress = (cycle_progress % segment_duration) / segment_duration
        
        color1 = colors[segment_idx % num_colors]
        color2 = colors[(segment_idx + 1) % num_colors]
        
        # Linear interpolate RGB
        return (
            int(color1[0] + (color2[0] - color1[0]) * segment_progress),
            int(color1[1] + (color2[1] - color1[1]) * segment_progress),
            int(color1[2] + (color2[2] - color1[2]) * segment_progress),
        )

    def update_buttons(self, buttons, bank_group_idx, locked_bank_idx, bank_group_just_changed=False):
        """
        Turns button LEDs on or off based on the button state.

        Args:
            buttons (list): List of button objects.
            bank_group_idx (int): Index of the current bank group.
            locked_bank_idx (int): Index of the locked bank (-1 if none).
            bank_group_just_changed (bool): Whether bank group was just changed (show indicator while navigating).
        """
        if locked_bank_idx != -1:
            # If a bank is locked, its lighting is handled separately
            return
        
        any_button_pressed = False
        pressed_button_indices = set()

        for idx, button in enumerate(buttons):
            pixel_index = self.button_pixel_indices.get(idx)
            if button.pressed:
                self.pixels[pixel_index] = cfg.BANK_GROUPS_COLORS[bank_group_idx][idx]
                any_button_pressed = True
                pressed_button_indices.add(idx)
            else:
                self.pixels[pixel_index] = (0, 0, 0)

        # Show bank group indicator if:
        # - No buttons are pressed, OR
        # - Bank group was just changed (navigating between bank groups)
        # But don't overwrite a pressed button's pixel
        if not any_button_pressed or bank_group_just_changed:
            if bank_group_idx not in pressed_button_indices:
                self.pixels[bank_group_idx] = cfg.BANK_GROUP_INDICATOR_COLOR

    def indicate_locked_bank(self, bank_group_idx, locked_bank_idx):
        """
        Lights the button LED for the locked bank.

        Args:
            bank_group_idx (int): The current bank group index.
            locked_bank_idx (int): The locked bank index.
        """
        for idx, pix_idx in self.button_pixel_indices.items():
            if idx == locked_bank_idx:
                self.pixels[pix_idx] = cfg.BANK_GROUPS_COLORS[bank_group_idx][locked_bank_idx]
            else:
                self.pixels[pix_idx] = (0, 0, 0)

    def indicate_jump_mode(self, enabled):
        """
        Lights up the indicator pixel to show jump mode status.

        Args:
            enabled (bool): True if jump mode is enabled, False otherwise.
        """
        self.pixels[self.indicator_pixel_index] = cfg.JUMP_MODE_COLOR if enabled else cfg.REG_MODE_COLOR

    def show_pixels(self):
        """
        Writes the current pixel state to the NeoPixel strip (makes changes visible).
        """
        self.pixels.show()

    def startup_animation(self):
        """
        Plays a brief but eye-catching rainbow animation on startup.
        Limits the animation to approximately 1 second.
        """
        readonly = storage.getmount("/").readonly
        if readonly:
            # Blink all pixels red 3 times before starting the animation
            for _ in range(3):
                self.pixels.fill((255, 0, 0))
                self.pixels.show()
                time.sleep(0.2)
                self.pixels.fill((0, 0, 0))
                self.pixels.show()
                time.sleep(0.2)

        # Simply call the rainbow animation with a 1-second duration limit
        self.rainbow_animation(speed=0.002, cycles=2, duration=2.0)

    def rainbow_animation(self, speed=0.01, cycles=3, duration=None):
        """
        Creates a smooth rainbow animation that cycles across all pixels.
        
        Args:
            speed (float): Speed of the animation (lower is faster)
            cycles (int): Number of complete color cycles across the strip
            duration (float, optional): If provided, animation stops after this many seconds
        """
        def wheel(pos):
            """
            Generate rainbow colors across 0-255 positions.
            """
            if pos < 85:
                return (255 - pos * 3, pos * 3, 0)
            elif pos < 170:
                pos -= 85
                return (0, 255 - pos * 3, pos * 3)
            else:
                pos -= 170
                return (pos * 3, 0, 255 - pos * 3)
        
        start_time = time.monotonic()
        try:
            while True:
                # Check if we've exceeded the time limit
                if duration is not None and (time.monotonic() - start_time) > duration:
                    break
                    
                for j in range(256):
                    # Check time limit within the inner loop too
                    if duration is not None and (time.monotonic() - start_time) > duration:
                        break
                        
                    for i in range(self.num_pixels):
                        # Distribute the colors evenly across the strip with multiple cycles
                        position = (i * 256 * cycles // self.num_pixels + j) % 256
                        self.pixels[i] = wheel(position)
                    self.show_pixels()
                    time.sleep(speed)
        except KeyboardInterrupt:
            pass
            
        # Clean up after animation ends
        self.clear()
        self.show_pixels()

if __name__ == "__main__":
    lights = LightsManager()
    lights.rainbow_animation(speed=0.001, cycles=2)