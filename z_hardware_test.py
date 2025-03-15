import time
import board
import neopixel

# Configuration
PIXEL_PIN = board.GP15   # GPIO pin connected to the NeoPixels (GPIO 15)
NUM_PIXELS = 69          # Number of NeoPixels

# Create the NeoPixel object
pixels = neopixel.NeoPixel(PIXEL_PIN, NUM_PIXELS, auto_write=False)

def wheel(pos):
    """Generate rainbow colors across 0-255 positions."""
    if pos < 0 or pos > 255:
        return (0, 0, 0)
    if pos < 85:
        return (255 - pos * 3, pos * 3, 0)
    elif pos < 170:
        pos -= 85
        return (0, 255 - pos * 3, pos * 3)
    else:
        pos -= 170
        return (pos * 3, 0, 255 - pos * 3)

while True:
    for j in range(255):
        for i in range(NUM_PIXELS):
            pixel_index = (i * 256 // NUM_PIXELS) + j
            pixels[i] = wheel(pixel_index & 255)
        pixels.show()
        time.sleep(0.01)