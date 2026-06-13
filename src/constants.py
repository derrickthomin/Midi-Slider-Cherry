from settings import settings

# Thresholds
LONG_HOLD_THRESH_S = 0.5
DOUBLE_PRESS_TIME = 0.3  # Time in seconds to detect double press

# Smoothing factors
SLOW_SMOOTHING_FACTOR = 0.2
FAST_SMOOTHING_FACTOR = 0.85
MOVEMENT_THRESHOLD = 1000

# Middle Range Noise Reduction
MIDDLE_RANGE_START = 30000
MIDDLE_RANGE_END = 40000
MIDDLE_RANGE_SMOOTHING_FACTOR = 0.05

# CC Threshold
CC_THRESHOLD = 2

# Adaptive Smoothing Constants
ADAPTIVE_BUFFER_SIZE = 5
ADAPTIVE_STABLE_THRESHOLD_CC = 3  # CC threshold when in stable mode
ADAPTIVE_MOVING_THRESHOLD_CC = 1  # CC threshold when in moving mode
ADAPTIVE_STABILITY_RANGE = 3      # Max range in buffer to consider "stable"
ADAPTIVE_HOLD_DURATION = 1.0      # Time to wait before switching to stable mode (seconds)
ADAPTIVE_MIN_MOVING_DURATION = 0.2  # Minimum time in moving mode (seconds)
ADAPTIVE_SMOOTHING_FACTOR = 0.3   # Exponential smoothing factor for raw values
ADAPTIVE_RAW_TO_CC_DIVISOR = 512  # 65536 / 128 = 512 (ADC range / CC range)

# CC Value Range
MIN_CC_VALUE = 0
MAX_CC_VALUE = 127

# Record Mode (firmware constants, not settings)
RECORD_MODE_HOLD_S = 3.0        # Hold all four buttons this long to toggle Record Mode
RECORD_MODE_HOLD_STEP_S = 0.75  # One button pixel of red fill per step (4 * 0.75 = 3.0)
DELETE_CONFIRM_WINDOW_S = 1.5   # Armed delete cancels after this long with no confirm
MAX_LOOP_EVENTS = 512           # Per-loop CC/AT event cap (Loopster CC_RAM_LIMIT)
MAX_LOOP_MS = 60000             # Per-loop length cap (forced by 'H' array timestamp width)
MEMORY_CRITICAL_THRESHOLD = 10000  # gc.mem_free() floor; recording auto-stops below this
NUM_RECORD_CC_SETS = 5          # global bank + page 1's 4 banks

# Global CC Bank and Pages from settings
GLOBAL_CC_BANK = settings.get_global_cc_bank()
PAGES = settings.get_all_pages()

# Colors
GLOBAL_BANK_COLOR = (200, 155, 55)  # A separate color for the global bank
JUMP_MODE_COLOR = (255, 165, 0)     # Orange for jump mode
REG_MODE_COLOR = (0, 255, 0)        # Green for regular mode
PAGE_INDICATOR_COLOR = (255, 255, 255)  # White for page indicator

# Record Mode colors / timing
RECORD_RECORDING_COLOR = (255, 0, 0)   # Solid red while recording (also hold-fill color)
RECORD_PLAYING_COLOR = (0, 255, 0)     # Green while a loop plays
RECORD_DELETE_BLINK_S = 0.15           # Delete-armed red blink phase length
RECORD_SET_FLASH_S = 0.25              # CC-set switch white flash duration
RECORD_SET_FLASH_COLOR = (255, 255, 255)

COLORS = {
    "WHITE": (255, 255, 255),
    "RED": (255, 0, 0),
    "GREEN": (0, 255, 0),
    "BLUE": (0, 0, 255),
    "CYAN": (0, 255, 255),
    "MAGENTA": (255, 0, 255),
    "ORANGE": (255, 140, 0),
    "LIME": (0, 255, 0),
    "TEAL": (0, 128, 128),
    "NAVY": (0, 0, 128),
    "BROWN": (165, 42, 42),
    "GOLD": (255, 200, 0),
    "YELLOW": (255, 255, 0),
    "INDIGO": (75, 0, 130),
    "CORAL": (255, 127, 80),
    "FUCHSIA": (255, 0, 255),
    "TOMATO": (255, 85, 65),
}
PAGE_COLORS = [
    [COLORS["RED"], COLORS["GREEN"], COLORS["BLUE"], COLORS["YELLOW"]],
    [COLORS["CYAN"], COLORS["MAGENTA"], COLORS["ORANGE"], COLORS["LIME"]],
    [COLORS["TEAL"], COLORS["NAVY"], COLORS["BROWN"], COLORS["GOLD"]],
    [COLORS["INDIGO"], COLORS["CORAL"], COLORS["FUCHSIA"], COLORS["TOMATO"]],
]