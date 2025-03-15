import board
import neopixel
import neopixel_spi
import time
import busio
from midi import midi_manager
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
        self.top_pixel = self.pixels[self.indicator_pixel_index]

        # Default state
        self.clear()
        self.pixels[self.indicator_pixel_index] = cfg.REG_MODE_COLOR

    def clear(self):
        """
        Clears all the pixels (sets them to black/off).
        """
        self.pixels.fill((0, 0, 0))

    def update_slider_lights(self, sliders, bank_idx=0, bank_group_idx=0):
        """
        Updates the LEDs to reflect the current positions of the sliders.

        Args:
            sliders (list): A list of slider objects or their CC values (0-127).
            bank_idx (int): The current bank index (-1 for global).
            bank_group_idx (int): The current bank group index.
        """
        for slider_idx, slider in enumerate(sliders):
            # Obtain the CC value (0-127)
            slider_cc_value = slider.cc_value if hasattr(slider, 'cc_value') else slider

            last_sent_cc_value = midi_manager.get_last_cc_value_sent(slider.current_assigned_cc_number)
            if abs(slider_cc_value - last_sent_cc_value) > 4:
                cc_value = last_sent_cc_value
            else:
                cc_value = slider_cc_value

            num_pixels = len(self.slider_pixel_indices[slider_idx])
            lit_pixels = int((cc_value / 127) * num_pixels)
            pixel_indices = self.slider_pixel_indices[slider_idx]

            # Determine color based on bank/global
            if bank_idx == -1:
                color = cfg.GLOBAL_BANK_COLOR
            else:
                color = cfg.BANK_GROUPS_COLORS[bank_group_idx][bank_idx]

            # Light up pixels according to the CC value
            for i, pix_idx in enumerate(pixel_indices):
                self.pixels[pix_idx] = color if i < lit_pixels else (0, 0, 0)

    def update_buttons(self, buttons, bank_group_idx, locked_bank_idx, blink_bank_indicator=False):
        """
        Turns button LEDs on or off based on the button state.

        Args:
            buttons (list): List of button objects.
            bank_group_idx (int): Index of the current bank group.
            locked_bank_idx (int): Index of the locked bank (-1 if none).
            blink_bank_indicator (bool): Whether to blink the bank indicator (unused here).
        """
        if locked_bank_idx != -1:
            # If a bank is locked, its lighting is handled separately
            return
        
        show_bank_group_indicator = True

        for idx, button in enumerate(buttons):
            pixel_index = self.button_pixel_indices.get(idx)
            if button.pressed:
                self.pixels[pixel_index] = cfg.BANK_GROUPS_COLORS[bank_group_idx][idx]
                show_bank_group_indicator = False
            else:
                self.pixels[pixel_index] = (0, 0, 0)

        # If no button is pressed, light up the pixel representing the current bank group
        if show_bank_group_indicator:
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
        Plays a simple animation on startup.
        """
        for i in range(self.num_pixels):
            self.pixels[i] = (0, 0, 255)
            self.pixels.show()
            time.sleep(0.005)
        self.clear()

    def rainbow_animation(self, speed=0.01, cycles=3):
        """
        Creates a smooth rainbow animation that cycles across all pixels.
        
        Args:
            speed (float): Speed of the animation (lower is faster)
            cycles (int): Number of complete color cycles across the strip
        """
        import math
        
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
        
        try:
            while True:
                for j in range(256):
                    for i in range(self.num_pixels):
                        # Distribute the colors evenly across the strip with multiple cycles
                        # This creates a wave-like effect with multiple color transitions visible at once
                        position = (i * 256 * cycles // self.num_pixels + j) % 256
                        self.pixels[i] = wheel(position)
                    self.show_pixels()
                    time.sleep(speed)
        except KeyboardInterrupt:
            # Allow for clean exit with CTRL+C
            self.clear()
            self.show_pixels()
            print("Rainbow animation stopped")

# # ------ TESTING COLORS ----------#
# if __name__ == "__main__":
#     lights_manager = LightsManager()
#     colors = list(cfg.COLORS.items())
    
#     for i, (color_name, color_value) in enumerate(colors):
#         if i < lights_manager.num_pixels:
#             lights_manager.pixels[i] = color_value
#             lights_manager.show_pixels()
#             print(f"Displaying: {color_name} - {color_value}")
#             input("...")
    
#     while True:
#         time.sleep(1)  # Keep the lights on indefinitely

if __name__ == "__main__":
    lights = LightsManager()
    lights.rainbow_animation(speed=0.001, cycles=2)