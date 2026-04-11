import json

class Settings:
    """
    Handles reading and validating settings from a JSON file.
    Provides default values if the settings file doesn't exist or contains invalid data.
    """
    
    # Default channel settings
    DEFAULT_GLOBAL_CHANNEL = 1  # 1-indexed for user-friendliness
    
    # Default CC bank settings
    DEFAULT_GLOBAL_CC_BANK = [0, 1, 2, 3]
    DEFAULT_CC_BANKS_1 = [
        [4, 5, 6, 7],
        [8, 9, 10, 11],
        [12, 13, 14, 15],
        [16, 17, 18, 19]
    ]
    DEFAULT_CC_BANKS_2 = [
        [20, 21, 22, 23],
        [24, 25, 26, 27],
        [28, 29, 30, 31],
        [32, 33, 34, 35]
    ]
    DEFAULT_CC_BANKS_3 = [
        [36, 37, 38, 39],
        [40, 41, 42, 43],
        [44, 45, 46, 47],
        [48, 49, 50, 51]
    ]
    DEFAULT_CC_BANKS_4 = [
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
            "CC_BANKS_1", 
            "CC_BANKS_2", 
            "CC_BANKS_3", 
            "CC_BANKS_4"
        ]
        
        for key in required_keys:
            if key not in self.settings:
                print(f"Missing required setting: {key}")
                return False
        
        # Validate GLOBAL_CC_BANK (list of 4 integers between 0-127)
        if not self._validate_cc_list(self.settings["GLOBAL_CC_BANK"], 4):
            return False
            
        # Validate CC_BANKS (4x4 arrays of integers between 0-127)
        for bank_key in ["CC_BANKS_1", "CC_BANKS_2", "CC_BANKS_3", "CC_BANKS_4"]:
            if not self._validate_cc_banks(self.settings[bank_key]):
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
    
    def _validate_cc_banks(self, banks):
        """
        Validate a 4x4 array of CC banks.
        
        Args:
            banks: The banks to validate
            
        Returns:
            bool: True if valid, False otherwise
        """
        if not isinstance(banks, list) or len(banks) != 4:
            print("CC banks must be a list of 4 lists")
            return False
            
        for bank in banks:
            if not self._validate_cc_list(bank, 4):
                return False
                
        return True
    
    def _use_defaults(self):
        """
        Set settings to factory default values.
        Channel settings use None to inherit (row→bank→global).
        """
        self.settings = {
            "GLOBAL_CHANNEL": self.DEFAULT_GLOBAL_CHANNEL,
            "GLOBAL_CC_BANK": self.DEFAULT_GLOBAL_CC_BANK,
            "CC_BANKS_1": self.DEFAULT_CC_BANKS_1,
            "CC_BANKS_2": self.DEFAULT_CC_BANKS_2,
            "CC_BANKS_3": self.DEFAULT_CC_BANKS_3,
            "CC_BANKS_4": self.DEFAULT_CC_BANKS_4,
            "CC_BANKS_1_CHANNEL": None,
            "CC_BANKS_2_CHANNEL": None,
            "CC_BANKS_3_CHANNEL": None,
            "CC_BANKS_4_CHANNEL": None,
            "CC_BANKS_1_ROW_CHANNELS": None,
            "CC_BANKS_2_ROW_CHANNELS": None,
            "CC_BANKS_3_ROW_CHANNELS": None,
            "CC_BANKS_4_ROW_CHANNELS": None,
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
    
    def get_cc_banks_1(self):
        """Get the CC banks 1 settings."""
        return self.settings["CC_BANKS_1"]
    
    def get_cc_banks_2(self):
        """Get the CC banks 2 settings."""
        return self.settings["CC_BANKS_2"]
    
    def get_cc_banks_3(self):
        """Get the CC banks 3 settings."""
        return self.settings["CC_BANKS_3"]
    
    def get_cc_banks_4(self):
        """Get the CC banks 4 settings."""
        return self.settings["CC_BANKS_4"]
    
    def get_all_cc_bank_groups(self):
        """Get all CC bank groups as a list."""
        return [
            self.settings["CC_BANKS_1"],
            self.settings["CC_BANKS_2"],
            self.settings["CC_BANKS_3"],
            self.settings["CC_BANKS_4"]
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
        Accepts: int (1-16), "GLOBAL", "BANK", "", null, or multi-channel string "1|2|3".
        
        Args:
            val: The value to check
            
        Returns:
            bool: True if valid, False otherwise
        """
        # Empty/null means inherit
        if self._is_empty_or_null(val):
            return True
        if val in ("GLOBAL", "BANK"):
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
    
    def _validate_row_channels(self, row_channels):
        """
        Validate a row channels array (4 channel values).
        Accepts null/empty for entire array or individual elements.
        
        Args:
            row_channels: The array to validate (can be None, empty, or list)
            
        Returns:
            bool: True if valid, False otherwise
        """
        # Null or empty array means inherit from bank
        if self._is_empty_or_null(row_channels):
            return True
        if not isinstance(row_channels, list) or len(row_channels) != 4:
            return False
        return all(self._validate_channel_value(ch) for ch in row_channels)
    
    def _get_bank_channels(self, bank_group_idx):
        """
        Get the resolved MIDI channels for a bank (not a specific row).
        Falls back to global if bank channel is empty/null/GLOBAL/BANK.
        
        Args:
            bank_group_idx (int): Bank group index (0-3)
            
        Returns:
            list: List of 0-indexed MIDI channels
        """
        bank_num = bank_group_idx + 1
        bank_channel_key = f"CC_BANKS_{bank_num}_CHANNEL"
        bank_ch = self.settings.get(bank_channel_key)
        
        # Empty/null/GLOBAL/BANK at bank level all fall through to global
        if self._is_empty_or_null(bank_ch) or bank_ch in ("GLOBAL", "BANK"):
            return self.get_global_channels()
        
        parsed = self._parse_channels(bank_ch)
        if parsed is not None:
            return parsed
        
        # Invalid value, fall back to global
        print(f"Invalid {bank_channel_key}: {bank_ch}. Falling back to global.")
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
    
    def get_resolved_channels(self, bank_group_idx, row_idx):
        """
        Get the resolved MIDI channels for a specific bank group and row.
        
        Hierarchy (first valid value wins):
        - Row Channel → if set to specific channel(s)
        - Bank Channel → if row is empty/null/"BANK", or row says "GLOBAL" and bank has specific channel
        - Global Channel → ultimate fallback
        
        Keywords:
        - "" or null: Inherit from parent (row→bank, bank→global)
        - "GLOBAL": Use global channel directly
        - "BANK": Use bank channel (only valid for row channels)
        
        Supports multi-channel format "1|2|3" at any level.
        
        Args:
            bank_group_idx (int): Bank group index (0-3)
            row_idx (int): Row index within the bank (0-3)
            
        Returns:
            list: List of 0-indexed MIDI channels
        """
        bank_num = bank_group_idx + 1  # Convert to 1-indexed for settings keys
        
        # 1. Check row-level override
        row_channels_key = f"CC_BANKS_{bank_num}_ROW_CHANNELS"
        row_channels = self.settings.get(row_channels_key)
        
        # If row_channels array exists and has this index
        if isinstance(row_channels, list) and len(row_channels) > row_idx:
            row_ch = row_channels[row_idx]
            
            # Empty/null or "BANK" → use bank channel
            if self._is_empty_or_null(row_ch) or row_ch == "BANK":
                return self._get_bank_channels(bank_group_idx)
            
            # "GLOBAL" → skip bank, go directly to global
            if row_ch == "GLOBAL":
                return self.get_global_channels()
            
            # Try to parse as channel number(s)
            parsed = self._parse_channels(row_ch)
            if parsed is not None:
                return parsed
            
            # Invalid value, fall through to bank
            print(f"Invalid row channel [{row_idx}] in {row_channels_key}: {row_ch}. Using bank channel.")
        
        # 2. Row channels array is null/empty or missing this index → use bank channel
        return self._get_bank_channels(bank_group_idx)

# Create a singleton instance
settings = Settings()