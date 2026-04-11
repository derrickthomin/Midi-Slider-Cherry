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
        """Set settings to default values."""
        self.settings = {
            "GLOBAL_CHANNEL": self.DEFAULT_GLOBAL_CHANNEL,
            "GLOBAL_CC_BANK": self.DEFAULT_GLOBAL_CC_BANK,
            "CC_BANKS_1": self.DEFAULT_CC_BANKS_1,
            "CC_BANKS_2": self.DEFAULT_CC_BANKS_2,
            "CC_BANKS_3": self.DEFAULT_CC_BANKS_3,
            "CC_BANKS_4": self.DEFAULT_CC_BANKS_4,
            "CC_BANKS_1_CHANNEL": "GLOBAL",
            "CC_BANKS_2_CHANNEL": "GLOBAL",
            "CC_BANKS_3_CHANNEL": "GLOBAL",
            "CC_BANKS_4_CHANNEL": "GLOBAL",
            "CC_BANKS_1_ROW_CHANNELS": ["GLOBAL", "GLOBAL", "GLOBAL", "GLOBAL"],
            "CC_BANKS_2_ROW_CHANNELS": ["GLOBAL", "GLOBAL", "GLOBAL", "GLOBAL"],
            "CC_BANKS_3_ROW_CHANNELS": ["GLOBAL", "GLOBAL", "GLOBAL", "GLOBAL"],
            "CC_BANKS_4_ROW_CHANNELS": ["GLOBAL", "GLOBAL", "GLOBAL", "GLOBAL"],
        }
    
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
    
    def _is_valid_channel_number(self, val):
        """
        Check if a value is a valid MIDI channel number (1-16, user-indexed).
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
    
    def _get_channel_as_int(self, val):
        """
        Convert a channel value to integer (1-16).
        
        Args:
            val: Channel value (int or string)
            
        Returns:
            int: The channel number, or None if invalid
        """
        if isinstance(val, int):
            return val
        if isinstance(val, str) and val.isdigit():
            return int(val)
        return None
    
    def _validate_channel_value(self, val):
        """
        Validate a channel value (either "GLOBAL" or int 1-16).
        
        Args:
            val: The value to validate
            
        Returns:
            bool: True if valid, False otherwise
        """
        if val == "GLOBAL":
            return True
        return self._is_valid_channel_number(val)
    
    def _validate_row_channels(self, row_channels):
        """
        Validate a row channels array (4 channel values).
        
        Args:
            row_channels: The array to validate
            
        Returns:
            bool: True if valid, False otherwise
        """
        if not isinstance(row_channels, list) or len(row_channels) != 4:
            return False
        return all(self._validate_channel_value(ch) for ch in row_channels)
    
    def get_global_channel(self):
        """
        Get the global MIDI channel (0-indexed for internal use).
        Falls back to 0 (channel 1) if invalid.
        
        Returns:
            int: 0-indexed MIDI channel (0-15)
        """
        ch = self.settings.get("GLOBAL_CHANNEL", self.DEFAULT_GLOBAL_CHANNEL)
        if self._is_valid_channel_number(ch):
            return self._get_channel_as_int(ch) - 1  # Convert to 0-indexed
        print(f"Invalid GLOBAL_CHANNEL: {ch}. Falling back to channel 1.")
        return 0  # Default to channel 1 (0-indexed)
    
    def get_resolved_channel(self, bank_group_idx, row_idx):
        """
        Get the resolved MIDI channel for a specific bank group and row.
        Hierarchy: Row Channel → Bank Channel → Global Channel
        
        Args:
            bank_group_idx (int): Bank group index (0-3)
            row_idx (int): Row index within the bank (0-3)
            
        Returns:
            int: 0-indexed MIDI channel (0-15)
        """
        bank_num = bank_group_idx + 1  # Convert to 1-indexed for settings keys
        
        # 1. Check row-level override
        row_channels_key = f"CC_BANKS_{bank_num}_ROW_CHANNELS"
        row_channels = self.settings.get(row_channels_key)
        if row_channels and isinstance(row_channels, list) and len(row_channels) > row_idx:
            row_ch = row_channels[row_idx]
            if self._is_valid_channel_number(row_ch):
                return self._get_channel_as_int(row_ch) - 1  # Convert to 0-indexed
        
        # 2. Check bank-level override
        bank_channel_key = f"CC_BANKS_{bank_num}_CHANNEL"
        bank_ch = self.settings.get(bank_channel_key)
        if self._is_valid_channel_number(bank_ch):
            return self._get_channel_as_int(bank_ch) - 1  # Convert to 0-indexed
        
        # 3. Fall back to global channel
        return self.get_global_channel()

# Create a singleton instance
settings = Settings()