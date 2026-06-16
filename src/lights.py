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

    def update_slider_lights(self, sliders, bank_idx=0, page_idx=0, held_button_order=None, page_just_changed=False):
        """
        Updates the LEDs to reflect the current positions of the sliders.

        Args:
            sliders (list): A list of slider objects or their CC values (0-127).
            bank_idx (int): The current bank index (-1 for global).
            page_idx (int): The current page index.
            held_button_order (list): List of button indices in press order (for multi-bank morphing).
            page_just_changed (bool): Whether page was just changed (disables morphing).
        """
        if held_button_order is None:
            held_button_order = []
        
        # Message type remains bank/page/global scoped; channel lookup is per-slider.
        if bank_idx == -1:
            message_type = settings.get_global_message_type()
        else:
            message_type = settings.get_resolved_message_type(page_idx, bank_idx)
        
        # Check for multi-bank mode and handle morphing
        # Disable morphing during page navigation to avoid false triggers
        is_multi_bank = len(held_button_order) > 1 and not page_just_changed
        
        # Reset morph timer when entering multi-bank mode
        if is_multi_bank and not self.was_multi_bank:
            self.morph_start_time = time.monotonic()
        
        self.was_multi_bank = is_multi_bank
        
        # Get color (morphed if multi-bank, solid otherwise)
        morphed_color = self._get_morphed_color(held_button_order, page_idx) if is_multi_bank else None
        
        for slider_idx, slider in enumerate(sliders):
            # Obtain the CC value (0-127)
            slider_cc_value = slider.cc_value if hasattr(slider, 'cc_value') else slider

            # Get last sent value based on message type (per-slider for AT)
            if message_type == "AT":
                last_sent_cc_value = midi_manager.get_last_at_value_per_slider(slider_idx, page_idx, bank_idx)
            else:
                if bank_idx == -1:
                    channel = settings.get_resolved_global_slider_channels(slider_idx)[0]
                else:
                    channel = settings.get_resolved_slider_channels(page_idx, bank_idx, slider_idx)[0]
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
                color = cfg.PAGE_COLORS[page_idx][bank_idx]

            # Light up pixels according to the CC value
            for i, pix_idx in enumerate(pixel_indices):
                self.pixels[pix_idx] = color if i < lit_pixels else (0, 0, 0)

    def _get_morphed_color(self, held_button_order, page_idx):
        """
        Returns an interpolated color when multiple buttons are held.
        
        Args:
            held_button_order (list): Button indices in press order.
            page_idx (int): Current page index.
            
        Returns:
            tuple: RGB color tuple, or None if not in multi-bank mode.
        """
        if len(held_button_order) <= 1:
            return None
        
        # Get all active colors in press order
        colors = [cfg.PAGE_COLORS[page_idx][idx] for idx in held_button_order]
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

    def update_buttons(self, buttons, page_idx, locked_bank_idx, page_just_changed=False, page_change_feedback=None):
        """
        Turns button LEDs on or off based on the button state.

        Args:
            buttons (list): List of button objects.
            page_idx (int): Index of the current page.
            locked_bank_idx (int): Index of the locked bank (-1 if none).
            page_just_changed (bool): Whether page was just changed (show indicator while navigating).
            page_change_feedback (dict): Optional feedback state with:
                - 'page_change_mode': If True, hide all button colors (only show page indicator)
                - 'blink_button_idx': Button to blink when at limit
                - 'blink_off': Whether we're in the "off" phase of the blink
        """
        if locked_bank_idx != -1:
            # If a bank is locked, its lighting is handled separately
            return
        
        if page_change_feedback is None:
            page_change_feedback = {'page_change_mode': False, 'blink_button_idx': -1, 'blink_off': False}
        
        page_change_mode = page_change_feedback.get('page_change_mode', False)
        blink_idx = page_change_feedback.get('blink_button_idx', -1)
        blink_off = page_change_feedback.get('blink_off', False)
        
        any_button_pressed = False
        pressed_button_indices = set()

        for idx, button in enumerate(buttons):
            pixel_index = self.button_pixel_indices.get(idx)
            if button.pressed:
                # In page change mode, hide all button colors
                if page_change_mode:
                    self.pixels[pixel_index] = (0, 0, 0)
                else:
                    self.pixels[pixel_index] = cfg.PAGE_COLORS[page_idx][idx]
                any_button_pressed = True
                pressed_button_indices.add(idx)
            else:
                self.pixels[pixel_index] = (0, 0, 0)

        # Show page indicator if:
        # - No buttons are pressed, OR
        # - Page was just changed (navigating between pages)
        # In page change mode, always show indicator (button colors are hidden)
        if not any_button_pressed or page_just_changed or page_change_mode:
            indicator_idx = page_idx
            # In page change mode, always show the indicator regardless of which buttons pressed
            show_indicator = page_change_mode or indicator_idx not in pressed_button_indices
            
            if show_indicator:
                # Check if we should blink this pixel (at page limit)
                if indicator_idx == blink_idx and blink_off:
                    self.pixels[indicator_idx] = (0, 0, 0)
                else:
                    self.pixels[indicator_idx] = cfg.PAGE_INDICATOR_COLOR

    def indicate_locked_bank(self, page_idx, locked_bank_idx):
        """
        Lights the button LED for the locked bank.

        Args:
            page_idx (int): The current page index.
            locked_bank_idx (int): The locked bank index.
        """
        for idx, pix_idx in self.button_pixel_indices.items():
            if idx == locked_bank_idx:
                self.pixels[pix_idx] = cfg.PAGE_COLORS[page_idx][locked_bank_idx]
            else:
                self.pixels[pix_idx] = (0, 0, 0)

    def update_record_mode_buttons(self, slot_states, set_flash=-1):
        """
        Draws the Record Mode loop-slot states on the button pixels (replaces
        update_buttons/indicate_locked_bank while Record Mode is active).

        Args:
            slot_states (list): 4 (state, color) tuples from
                controller.get_record_slot_states(). States: "empty",
                "recording", "playing", "stopped", "delete_armed"; color is the
                bank color for "stopped" slots.
            set_flash (int): landed CC set index to flash (-1 = no flash). Sets
                1+ flash that set's bank pixel ((set-1)%4) in the page's color
                (RECORD_PAGE_FLASH_COLORS[(set-1)//4]); set 0 (global) briefly
                blanks all four button pixels. The button position encodes the
                bank and the color the page, so navigating up lands on bank 1
                (bottom) and walks up, down lands on bank 4 (top) and walks down.
        """
        now = time.monotonic()
        for idx, (state, color) in enumerate(slot_states):
            pixel_index = self.button_pixel_indices[idx]
            if state == "recording":
                self.pixels[pixel_index] = cfg.RECORD_RECORDING_COLOR
            elif state == "delete_armed":
                blink_on = int(now / cfg.RECORD_DELETE_BLINK_S) % 2 == 0
                self.pixels[pixel_index] = cfg.RECORD_RECORDING_COLOR if blink_on else (0, 0, 0)
            elif state == "playing":
                self.pixels[pixel_index] = cfg.RECORD_PLAYING_COLOR
            elif state == "stopped":
                self.pixels[pixel_index] = color if color is not None else (0, 0, 0)
            else:  # empty
                self.pixels[pixel_index] = (0, 0, 0)

        # CC-set navigation flash (overlays the slot states): light the landed
        # set's bank button in the page color; the global set blanks all four.
        if set_flash == 0:
            for idx in range(4):
                self.pixels[self.button_pixel_indices[idx]] = (0, 0, 0)
        elif set_flash > 0:
            bank = (set_flash - 1) % 4
            page = (set_flash - 1) // 4
            self.pixels[self.button_pixel_indices[bank]] = cfg.RECORD_PAGE_FLASH_COLORS[page]

    def update_mapping_mode(self, target_slider_idx, confirm_slider_idx, confirm_active,
                            confirm_failed, bank_button_idx=-1, bank_page_idx=0):
        """
        Draws Mapping Mode (on-device MIDI learn, §2j): replaces
        update_slider_lights / update_buttons / indicate_locked_bank /
        indicate_jump_mode while Mapping Mode is active.

        Args:
            target_slider_idx (int): Current learn target slider's 16 pixels
                blink blue (-1 = idle, nothing blinks).
            confirm_slider_idx (int): Slider showing the confirm flash
                (-1 = none).
            confirm_active (bool): True while the confirm flash is showing -
                overrides the target's blink with a solid color.
            confirm_failed (bool): True -> red flash (save failed),
                False -> green (saved).
            bank_button_idx (int): For bank-scope mapping, the locked bank's
                button to keep lit at its normal color so the user can see which
                bank they're assigning. -1 = global scope (all buttons dark).
            bank_page_idx (int): Page index used for that button's normal color.
        """
        self.clear()

        blink_on = int(time.monotonic() / cfg.MAPPING_BLINK_S) % 2 == 0

        if target_slider_idx != -1:
            color = cfg.MAPPING_COLOR if blink_on else (0, 0, 0)
            for pix_idx in self.slider_pixel_indices[target_slider_idx]:
                self.pixels[pix_idx] = color

        if confirm_active and confirm_slider_idx != -1:
            confirm_color = cfg.MAPPING_FAIL_COLOR if confirm_failed else cfg.MAPPING_CONFIRM_COLOR
            for pix_idx in self.slider_pixel_indices[confirm_slider_idx]:
                self.pixels[pix_idx] = confirm_color

        # Bank scope keeps the locked bank's button solid at its normal color;
        # global scope leaves all four dark (handled by bank_button_idx == -1).
        for idx in range(4):
            if idx == bank_button_idx:
                self.pixels[self.button_pixel_indices[idx]] = cfg.PAGE_COLORS[bank_page_idx][idx]
            else:
                self.pixels[self.button_pixel_indices[idx]] = (0, 0, 0)

        # Indicator pixel ("top LED") blinks blue in sync for the whole session.
        self.pixels[self.indicator_pixel_index] = cfg.MAPPING_COLOR if blink_on else (0, 0, 0)

    def update_mode_hold_progress(self, pixels_lit):
        """
        Overlays the hold-all-four-buttons progress fill: button pixels fill
        red one at a time, bottom to top. Draw after the normal button-pixel
        pass in either mode.

        Args:
            pixels_lit (int): Number of pixels to light (0-4).
        """
        for idx in range(min(pixels_lit, 4)):
            self.pixels[self.button_pixel_indices[idx]] = cfg.RECORD_RECORDING_COLOR

    def record_mode_toggle_animation(self, entering):
        """
        Brief blocking confirmation animation when Record Mode toggles
        (~300 ms): a red sweep up the button pixels on enter, down on exit.

        Args:
            entering (bool): True if Record Mode was just entered.
        """
        order = [0, 1, 2, 3] if entering else [3, 2, 1, 0]
        for idx in range(4):
            self.pixels[self.button_pixel_indices[idx]] = (0, 0, 0)
        self.pixels.show()
        for idx in order:
            self.pixels[self.button_pixel_indices[idx]] = cfg.RECORD_RECORDING_COLOR
            self.pixels.show()
            time.sleep(0.06)
        time.sleep(0.06)
        for idx in range(4):
            self.pixels[self.button_pixel_indices[idx]] = (0, 0, 0)
        self.pixels.show()

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