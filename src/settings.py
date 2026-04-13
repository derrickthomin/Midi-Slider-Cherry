import json

class Settings:
    """
    Handles reading and validating settings from a JSON file.
    Provides default values if the settings file doesn't exist or contains invalid data.
    """
    
    # Default channel settings
    DEFAULT_GLOBAL_CHANNEL = 1  # 1-indexed for user-friendliness
    DEFAULT_GLOBAL_MESSAGE_TYPE = "CC"  # Default to Control Change
    
    # Valid message types
    VALID_MESSAGE_TYPES = ("CC", "AT")  # CC = Control Change, AT = Channel Aftertouch
    
    # Default CC bank settings
    DEFAULT_GLOBAL_CC_BANK = [0, 1, 2, 3]
    DEFAULT_PAGE_1_BANKS = [
        [4, 5, 6, 7],
        [8, 9, 10, 11],
        [12, 13, 14, 15],
        [16, 17, 18, 19]
    ]
    DEFAULT_PAGE_2_BANKS = [
        [20, 21, 22, 23],
        [24, 25, 26, 27],
        [28, 29, 30, 31],
        [32, 33, 34, 35]
    ]
    DEFAULT_PAGE_3_BANKS = [
        [36, 37, 38, 39],
        [40, 41, 42, 43],
        [44, 45, 46, 47],
        [48, 49, 50, 51]
    ]
    DEFAULT_PAGE_4_BANKS = [
        [52, 53, 54, 55],
        [56, 57, 58, 59],
        [60, 61, 62, 63],
        [64, 65, 66, 67]
    ]
    
    def __init__(self, settings_path="settings.json"):
        """
        Initialize Settings with path to settings file.
        
        Args:
            settings_path (str): Path to settings JSON file
        """
        self.settings_path = settings_path
        self.settings = {}
        self.load_settings()
        
    def load_settings(self):
        """
        Load settings from JSON file. If file doesn't exist or is invalid,
        use default values and create a new settings file.
        """
        try:
   
            with open(self.settings_path, 'r') as f:
                self.settings = json.load(f)
            
            # Validate the loaded settings
            if not self._validate_settings():
                print("Invalid settings in file. Using defaults.")
                self._use_defaults()
                #self._save_settings()
                
        except Exception as e:
            # Using a general Exception instead of specific JSONDecodeError
            print(f"Error loading settings: {str(e)}. Using defaults.")
            self._use_defaults()
            #self._save_settings()
    
    def _validate_settings(self):
        """
        Validate the loaded settings to ensure they have the correct structure.
        
        Returns:
            bool: True if valid, False otherwise
        """
        # Check if required keys exist
        required_keys = [
            "GLOBAL_CC_BANK", 
            "PAGE_1_BANKS", 
            "PAGE_2_BANKS", 
            "PAGE_3_BANKS", 
            "PAGE_4_BANKS"
        ]
        
        for key in required_keys:
            if key not in self.settings:
                print(f"Missing required setting: {key}")
                return False
        
        # Validate GLOBAL_CC_BANK (list of 4 integers between 0-127)
        if not self._validate_cc_list(self.settings["GLOBAL_CC_BANK"], 4):
            return False
            
        # Validate page banks (4x4 arrays of integers between 0-127)
        for page_key in ["PAGE_1_BANKS", "PAGE_2_BANKS", "PAGE_3_BANKS", "PAGE_4_BANKS"]:
            if not self._validate_page_banks(self.settings[page_key]):
                return False
                
        return True
    
    def _validate_cc_list(self, cc_list, expected_length):
        """
        Validate a list of CC values.
        
        Args:
            cc_list: The list to validate
            expected_length: Expected length of the list
            
        Returns:
            bool: True if valid, False otherwise
        """
        if not isinstance(cc_list, list) or len(cc_list) != expected_length:
            print(f"CC list must be a list of {expected_length} integers")
            return False
            
        for cc in cc_list:
            if not isinstance(cc, int) or cc < 0 or cc > 127:
                print(f"Invalid CC value: {cc}. Must be an integer between 0-127")
                return False
                
        return True
    
    def _validate_page_banks(self, banks):
        """
        Validate a 4x4 array of banks for a page.
        
        Args:
            banks: The banks to validate
            
        Returns:
            bool: True if valid, False otherwise
        """
        if not isinstance(banks, list) or len(banks) != 4:
            print("Page banks must be a list of 4 lists")
            return False
            
        for bank in banks:
            if not self._validate_cc_list(bank, 4):
                return False
                
        return True
    
    def _use_defaults(self):
        """
        Set settings to factory default values.
        Channel settings use None to inherit (bank→page→global).
        Type settings use None to inherit (bank→page→global), defaulting to "CC".
        """
        self.settings = {
            "GLOBAL_CHANNEL": self.DEFAULT_GLOBAL_CHANNEL,
            "GLOBAL_MESSAGE_TYPE": self.DEFAULT_GLOBAL_MESSAGE_TYPE,
            "GLOBAL_CC_BANK": self.DEFAULT_GLOBAL_CC_BANK,
            "PAGE_1_BANKS": self.DEFAULT_PAGE_1_BANKS,
            "PAGE_2_BANKS": self.DEFAULT_PAGE_2_BANKS,
            "PAGE_3_BANKS": self.DEFAULT_PAGE_3_BANKS,
            "PAGE_4_BANKS": self.DEFAULT_PAGE_4_BANKS,
            "PAGE_1_CHANNEL": None,
            "PAGE_2_CHANNEL": None,
            "PAGE_3_CHANNEL": None,
            "PAGE_4_CHANNEL": None,
            "PAGE_1_BANK_CHANNELS": None,
            "PAGE_2_BANK_CHANNELS": None,
            "PAGE_3_BANK_CHANNELS": None,
            "PAGE_4_BANK_CHANNELS": None,
            "PAGE_1_TYPE": None,
            "PAGE_2_TYPE": None,
            "PAGE_3_TYPE": None,
            "PAGE_4_TYPE": None,
            "PAGE_1_BANK_TYPES": None,
            "PAGE_2_BANK_TYPES": None,
            "PAGE_3_BANK_TYPES": None,
            "PAGE_4_BANK_TYPES": None,
        }
    
    def _is_empty_or_null(self, val):
        """
        Check if a value is empty/null (meaning "inherit from parent").
        
        Args:
            val: The value to check
            
        Returns:
            bool: True if value should inherit, False otherwise
        """
        return val is None or val == "" or val == "null"
    
    def _save_settings(self):
        """Save current settings to JSON file."""
        try:
            with open(self.settings_path, 'w') as f:
                json.dump(self.settings, f, indent=4)
        except Exception as e:
            print(f"Error saving settings: {str(e)}")
    
    def get_global_cc_bank(self):
        """Get the global CC bank settings."""
        return self.settings["GLOBAL_CC_BANK"]
    
    def get_page_1_banks(self):
        """Get the page 1 banks settings."""
        return self.settings["PAGE_1_BANKS"]
    
    def get_page_2_banks(self):
        """Get the page 2 banks settings."""
        return self.settings["PAGE_2_BANKS"]
    
    def get_page_3_banks(self):
        """Get the page 3 banks settings."""
        return self.settings["PAGE_3_BANKS"]
    
    def get_page_4_banks(self):
        """Get the page 4 banks settings."""
        return self.settings["PAGE_4_BANKS"]
    
    def get_all_pages(self):
        """Get all pages as a list (each page contains 4 banks)."""
        return [
            self.settings["PAGE_1_BANKS"],
            self.settings["PAGE_2_BANKS"],
            self.settings["PAGE_3_BANKS"],
            self.settings["PAGE_4_BANKS"]
        ]
    
    def _is_valid_single_channel(self, val):
        """
        Check if a value is a valid single MIDI channel number (1-16, user-indexed).
        Accepts both integers and string representations of integers.
        
        Args:
            val: The value to check
            
        Returns:
            bool: True if valid channel number, False otherwise
        """
        # Handle integer directly
        if isinstance(val, int):
            return 1 <= val <= 16
        # Handle string representation of integer
        if isinstance(val, str) and val.isdigit():
            return 1 <= int(val) <= 16
        return False
    
    def _is_valid_channel_value(self, val):
        """
        Check if a value is a valid channel specification.
        Accepts: int (1-16), "GLOBAL", "PAGE", "", null, or multi-channel string "1|2|3".
        
        Args:
            val: The value to check
            
        Returns:
            bool: True if valid, False otherwise
        """
        # Empty/null means inherit
        if self._is_empty_or_null(val):
            return True
        if val in ("GLOBAL", "PAGE"):
            return True
        if self._is_valid_single_channel(val):
            return True
        # Check for multi-channel format "1|2|3"
        if isinstance(val, str) and "|" in val:
            parts = val.split("|")
            return all(self._is_valid_single_channel(p.strip()) for p in parts)
        return False
    
    def _parse_channels(self, val):
        """
        Parse a channel value into a list of 0-indexed channel numbers.
        
        Supports:
        - Single int: 1 → [0]
        - String int: "1" → [0]
        - Multi-channel: "1|2|3" → [0, 1, 2]
        
        Note: For multi-channel setups, avoid overlapping channels between
        GLOBAL and bank/row settings. If overlap occurs, pickup mode may
        behave unexpectedly (uses first channel for crossing detection).
        
        Args:
            val: Channel value (int, string, or multi-channel string)
            
        Returns:
            list: List of 0-indexed channel numbers, or None if invalid
        """
        # Single integer
        if isinstance(val, int) and 1 <= val <= 16:
            return [val - 1]
        
        if isinstance(val, str):
            # Single string integer
            if val.isdigit() and 1 <= int(val) <= 16:
                return [int(val) - 1]
            
            # Multi-channel format "1|2|3"
            if "|" in val:
                parts = val.split("|")
                channels = []
                for p in parts:
                    p = p.strip()
                    if p.isdigit() and 1 <= int(p) <= 16:
                        channels.append(int(p) - 1)
                    else:
                        return None  # Invalid part
                return channels if channels else None
        
        return None
    
    def _validate_channel_value(self, val):
        """
        Validate a channel value ("GLOBAL", int 1-16, or multi-channel "1|2|3").
        
        Args:
            val: The value to validate
            
        Returns:
            bool: True if valid, False otherwise
        """
        return self._is_valid_channel_value(val)
    
    def _validate_bank_channels(self, bank_channels):
        """
        Validate a bank channels array (4 channel values).
        Accepts null/empty for entire array or individual elements.
        
        Args:
            bank_channels: The array to validate (can be None, empty, or list)
            
        Returns:
            bool: True if valid, False otherwise
        """
        # Null or empty array means inherit from page
        if self._is_empty_or_null(bank_channels):
            return True
        if not isinstance(bank_channels, list) or len(bank_channels) != 4:
            return False
        return all(self._validate_channel_value(ch) for ch in bank_channels)
    
    def _get_page_channels(self, page_idx):
        """
        Get the resolved MIDI channels for a page (not a specific bank).
        Falls back to global if page channel is empty/null/GLOBAL/PAGE.
        
        Args:
            page_idx (int): Page index (0-3)
            
        Returns:
            list: List of 0-indexed MIDI channels
        """
        page_num = page_idx + 1
        page_channel_key = f"PAGE_{page_num}_CHANNEL"
        page_ch = self.settings.get(page_channel_key)
        
        # Empty/null/GLOBAL/PAGE at page level all fall through to global
        if self._is_empty_or_null(page_ch) or page_ch in ("GLOBAL", "PAGE"):
            return self.get_global_channels()
        
        parsed = self._parse_channels(page_ch)
        if parsed is not None:
            return parsed
        
        # Invalid value, fall back to global
        print(f"Invalid {page_channel_key}: {page_ch}. Falling back to global.")
        return self.get_global_channels()
    
    def get_global_channels(self):
        """
        Get the global MIDI channels (0-indexed for internal use).
        Supports multi-channel format "1|2|3".
        Falls back to [0] (channel 1) if invalid.
        
        Returns:
            list: List of 0-indexed MIDI channels
        """
        ch = self.settings.get("GLOBAL_CHANNEL", self.DEFAULT_GLOBAL_CHANNEL)
        parsed = self._parse_channels(ch)
        if parsed is not None:
            return parsed
        print(f"Invalid GLOBAL_CHANNEL: {ch}. Falling back to channel 1.")
        return [0]  # Default to channel 1 (0-indexed)
    
    def get_resolved_channels(self, page_idx, bank_idx):
        """
        Get the resolved MIDI channels for a specific page and bank.
        
        Hierarchy (first valid value wins):
        - Bank Channel → if set to specific channel(s)
        - Page Channel → if bank is empty/null/"PAGE", or bank says "GLOBAL" and page has specific channel
        - Global Channel → ultimate fallback
        
        Keywords:
        - "" or null: Inherit from parent (bank→page, page→global)
        - "GLOBAL": Use global channel directly
        - "PAGE": Use page channel (only valid for bank channels)
        
        Supports multi-channel format "1|2|3" at any level.
        
        Args:
            page_idx (int): Page index (0-3)
            bank_idx (int): Bank index within the page (0-3)
            
        Returns:
            list: List of 0-indexed MIDI channels
        """
        page_num = page_idx + 1  # Convert to 1-indexed for settings keys
        
        # 1. Check bank-level override
        bank_channels_key = f"PAGE_{page_num}_BANK_CHANNELS"
        bank_channels = self.settings.get(bank_channels_key)
        
        # If bank_channels array exists and has this index
        if isinstance(bank_channels, list) and len(bank_channels) > bank_idx:
            bank_ch = bank_channels[bank_idx]
            
            # Empty/null or "PAGE" → use page channel
            if self._is_empty_or_null(bank_ch) or bank_ch == "PAGE":
                return self._get_page_channels(page_idx)
            
            # "GLOBAL" → skip page, go directly to global
            if bank_ch == "GLOBAL":
                return self.get_global_channels()
            
            # Try to parse as channel number(s)
            parsed = self._parse_channels(bank_ch)
            if parsed is not None:
                return parsed
            
            # Invalid value, fall through to page
            print(f"Invalid bank channel [{bank_idx}] in {bank_channels_key}: {bank_ch}. Using page channel.")
        
        # 2. Bank channels array is null/empty or missing this index → use page channel
        return self._get_page_channels(page_idx)
    
    # ==================== Message Type Methods ====================
    
    def _is_valid_message_type(self, val):
        """
        Check if a value is a valid message type.
        Accepts: "CC", "AT", "", or null (inherit).
        
        Args:
            val: The value to check
            
        Returns:
            bool: True if valid, False otherwise
        """
        if self._is_empty_or_null(val):
            return True
        return val in self.VALID_MESSAGE_TYPES
    
    def _validate_bank_types(self, bank_types):
        """
        Validate a bank types array (4 type values).
        Accepts null/empty for entire array or individual elements.
        
        Args:
            bank_types: The array to validate (can be None, empty, or list)
            
        Returns:
            bool: True if valid, False otherwise
        """
        if self._is_empty_or_null(bank_types):
            return True
        if not isinstance(bank_types, list) or len(bank_types) != 4:
            return False
        return all(self._is_valid_message_type(t) for t in bank_types)
    
    def get_global_message_type(self):
        """
        Get the global message type.
        Falls back to "CC" if invalid or missing.
        
        Returns:
            str: "CC" or "AT"
        """
        msg_type = self.settings.get("GLOBAL_MESSAGE_TYPE", self.DEFAULT_GLOBAL_MESSAGE_TYPE)
        if msg_type in self.VALID_MESSAGE_TYPES:
            return msg_type
        print(f"Invalid GLOBAL_MESSAGE_TYPE: {msg_type}. Falling back to CC.")
        return "CC"
    
    def _get_page_message_type(self, page_idx):
        """
        Get the resolved message type for a page (not a specific bank).
        Falls back to global if page type is empty/null.
        
        Args:
            page_idx (int): Page index (0-3)
            
        Returns:
            str: "CC" or "AT"
        """
        page_num = page_idx + 1
        page_type_key = f"PAGE_{page_num}_TYPE"
        page_type = self.settings.get(page_type_key)
        
        # Empty/null at page level falls through to global
        if self._is_empty_or_null(page_type):
            return self.get_global_message_type()
        
        if page_type in self.VALID_MESSAGE_TYPES:
            return page_type
        
        # Invalid value, fall back to global
        print(f"Invalid {page_type_key}: {page_type}. Falling back to global.")
        return self.get_global_message_type()
    
    def get_resolved_message_type(self, page_idx, bank_idx):
        """
        Get the resolved message type for a specific page and bank.
        
        Hierarchy (first valid value wins):
        - Bank Type → if set to "CC" or "AT"
        - Page Type → if bank is empty/null
        - Global Type → ultimate fallback
        
        Args:
            page_idx (int): Page index (0-3)
            bank_idx (int): Bank index within the page (0-3)
            
        Returns:
            str: "CC" or "AT"
        """
        page_num = page_idx + 1
        
        # 1. Check bank-level override
        bank_types_key = f"PAGE_{page_num}_BANK_TYPES"
        bank_types = self.settings.get(bank_types_key)
        
        # If bank_types array exists and has this index
        if isinstance(bank_types, list) and len(bank_types) > bank_idx:
            bank_type = bank_types[bank_idx]
            
            # Empty/null → use page type
            if self._is_empty_or_null(bank_type):
                return self._get_page_message_type(page_idx)
            
            # Valid type
            if bank_type in self.VALID_MESSAGE_TYPES:
                return bank_type
            
            # Invalid value, fall through to page
            print(f"Invalid bank type [{bank_idx}] in {bank_types_key}: {bank_type}. Using page type.")
        
        # 2. Bank types array is null/empty or missing this index → use page type
        return self._get_page_message_type(page_idx)

# Create a singleton instance
settings = Settings()