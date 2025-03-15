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

# CC Value Range
MIN_CC_VALUE = 0
MAX_CC_VALUE = 127

# # Global CC Bank
# GLOBAL_CC_BANK = [0, 1, 2, 3]

# # CC Banks
# CC_BANKS_1 = [
#     [4, 5, 6, 7],
#     [8, 9, 10, 11],
#     [12, 13, 14, 15],
#     [16, 17, 18, 19],
# ]
# CC_BANKS_2 = [
#     [20, 21, 22, 23],
#     [24, 25, 26, 27],
#     [28, 29, 30, 31],
#     [32, 33, 34, 35],
# ]
# CC_BANKS_3 = [
#     [36, 37, 38, 39],
#     [40, 41, 42, 43],
#     [44, 45, 46, 47],
#     [48, 49, 50, 51],
# ]
# CC_BANKS_4 = [
#     [52, 53, 54, 55],
#     [56, 57, 58, 59],
#     [60, 61, 62, 63],
#     [64, 65, 66, 67],
# ]

# CC_BANK_GROUPS = [
#     CC_BANKS_1,
#     CC_BANKS_2,
#     CC_BANKS_3,
#     CC_BANKS_4,
# ]

# Global CC Bank and CC Banks from settings
GLOBAL_CC_BANK = settings.get_global_cc_bank()
CC_BANK_GROUPS = settings.get_all_cc_bank_groups()

# Colors
GLOBAL_BANK_COLOR = (200, 155, 55)  # A separate color for the global bank
JUMP_MODE_COLOR = (255, 165, 0)     # Orange for jump mode
REG_MODE_COLOR = (0, 255, 0)        # Green for regular mode
BANK_GROUP_INDICATOR_COLOR = (255, 255, 255)  # White for bank group indicator

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
BANK_GROUPS_COLORS = [
    [COLORS["RED"], COLORS["GREEN"], COLORS["BLUE"], COLORS["YELLOW"]],
    [COLORS["CYAN"], COLORS["MAGENTA"], COLORS["ORANGE"], COLORS["LIME"]],
    [COLORS["TEAL"], COLORS["NAVY"], COLORS["BROWN"], COLORS["GOLD"]],
    [COLORS["INDIGO"], COLORS["CORAL"], COLORS["FUCHSIA"], COLORS["TOMATO"]],
]