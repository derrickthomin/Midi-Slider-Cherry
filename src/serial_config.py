"""
LumaFader - Serial Configuration Handler
=========================================
Handles serial commands for reading/writing settings via Web Serial API.

Uses USB CDC console (single serial port mode).
Disconnect any serial monitor before using web config.

Protocol:
---------
Commands are newline-terminated strings starting with "CMD:".
Responses are newline-terminated strings starting with "RSP:".

CMD:PING               - Returns RSP:{"status":"ok","device":"lumafader"}
CMD:GET_SETTINGS       - Returns RSP:<settings json>
CMD:SET_SETTINGS|json  - Updates settings from JSON, saves to file
CMD:GET_STATUS         - Returns RSP:<current device state for interactive UI>
CMD:SET_CONFIG_MODE|N  - Enable (1) or disable (0) config mode
CMD:SET_LOCKED_BANK|N  - Lock bank N (0-3), or -1 to unlock
"""

import json
import sys
import time
import supervisor

SETTINGS_FILE = "settings.json"
CONFIG_MODE_TIMEOUT = 5.0  # Auto-exit config mode if no ping for 5 seconds
LEARN_MODE_TIMEOUT = 30.0  # Auto-cancel learn mode after 30 seconds


class SerialConfigHandler:
    """Handles serial commands for configuration via USB serial."""
    
    def __init__(self):
        self._buffer = ""
        self._controller = None
        self._midi_manager = None
        self._last_moved_slider = -1
        self._last_slider_values = [0, 0, 0, 0]
        self._config_mode = False
        self._last_ping_time = 0
        # Learn mode state
        self._learn_mode = False
        self._learn_slider_idx = -1
        self._learn_start_time = 0
        # Last received MIDI for display
        self._last_midi_type = None   # "CC" or "AT"
        self._last_midi_num = None    # CC number or AT value
        self._last_midi_ch = None     # Channel (1-indexed)
    
    @property
    def config_mode(self):
        """Return True if in config mode (single-click locks banks)."""
        return self._config_mode
    
    def set_controller(self, controller):
        """Set reference to controller for status queries."""
        self._controller = controller
    
    def set_midi_manager(self, midi_manager):
        """Set reference to MIDI manager for learn mode."""
        self._midi_manager = midi_manager
    
    def update(self):
        """
        Check for and process serial commands.
        Call this from the main loop.
        Returns True if a command was processed.
        """
        # Check config mode timeout
        if self._config_mode and (time.monotonic() - self._last_ping_time) > CONFIG_MODE_TIMEOUT:
            self._config_mode = False
            if self._controller:
                self._controller.config_mode = False
                # Unlock bank when exiting config mode
                if self._controller.locked_bank_idx != -1:
                    self._controller.unlock_bank()
        
        # Check learn mode timeout
        if self._learn_mode and (time.monotonic() - self._learn_start_time) > LEARN_MODE_TIMEOUT:
            timed_out_slider = self._learn_slider_idx
            self._learn_mode = False
            self._learn_slider_idx = -1
            self._respond({"type": "learn_timeout", "slider": timed_out_slider})
        
        # Poll for incoming MIDI CC during learn mode
        if self._learn_mode and self._midi_manager:
            cc_data = self._midi_manager.receive_cc()
            if cc_data:
                cc_number, channel = cc_data
                self._last_midi_type = "CC"
                self._last_midi_num = cc_number
                self._last_midi_ch = channel
                self._respond({
                    "type": "learned",
                    "slider": self._learn_slider_idx,
                    "cc": cc_number,
                    "channel": channel
                })
                self._learn_mode = False
                self._learn_slider_idx = -1
        elif not self._learn_mode and self._midi_manager and self._config_mode:
            # Passively monitor incoming MIDI for display (only in config mode)
            midi_data = self._midi_manager.receive_cc_or_at()
            if midi_data:
                self._last_midi_type = midi_data[0]
                self._last_midi_num = midi_data[1]
                self._last_midi_ch = midi_data[2]
        
        # Check if there's serial data available
        while supervisor.runtime.serial_bytes_available:
            try:
                # Read one character at a time
                char = sys.stdin.read(1)
                if char:
                    self._buffer += char
                    
                    # Check for complete line
                    if char in ('\n', '\r'):
                        line = self._buffer.strip()
                        self._buffer = ""
                        
                        # Only process lines that start with CMD:
                        if line.startswith("CMD:"):
                            cmd = line[4:]  # Remove CMD: prefix
                            self._process_command(cmd)
                            return True
            except Exception as e:
                self._buffer = ""
        return False
    
    def _process_command(self, command):
        """Process a single command and send response."""
        try:
            if command == "PING":
                self._last_ping_time = time.monotonic()
                self._respond({"status": "ok", "device": "lumafader"})
            
            elif command == "GET_SETTINGS":
                self._send_file_contents(SETTINGS_FILE)
            
            elif command == "GET_STATUS":
                self._send_status()
            
            elif command.startswith("SET_SETTINGS|"):
                json_str = command[13:]  # Remove "SET_SETTINGS|" prefix
                self._save_settings(json_str)
            
            elif command.startswith("SET_CONFIG_MODE|"):
                mode = command[16:]  # Remove "SET_CONFIG_MODE|" prefix
                self._config_mode = (mode == "1")
                self._last_ping_time = time.monotonic()
                # Set controller's config mode
                if self._controller:
                    self._controller.config_mode = self._config_mode
                # Unlock bank when exiting config mode
                if not self._config_mode and self._controller and self._controller.locked_bank_idx != -1:
                    self._controller.unlock_bank()
                self._respond({"status": "ok", "config_mode": self._config_mode})
            
            elif command.startswith("SET_LOCKED_BANK|"):
                bank_str = command[16:]  # Remove "SET_LOCKED_BANK|" prefix
                try:
                    bank_idx = int(bank_str)
                    if self._controller:
                        if bank_idx == -1:
                            self._controller.unlock_bank()
                        elif 0 <= bank_idx <= 3:
                            self._controller.lock_bank(bank_idx)
                        else:
                            self._respond({"error": "Bank index must be -1 to 3"})
                            return
                        self._respond({"status": "ok", "locked_bank": self._controller.locked_bank_idx})
                    else:
                        self._respond({"error": "Controller not initialized"})
                except ValueError:
                    self._respond({"error": f"Invalid bank index: {bank_str}"})
            
            elif command.startswith("START_LEARN|"):
                slider_str = command[12:]  # Remove "START_LEARN|" prefix
                try:
                    slider_idx = int(slider_str)
                    if 0 <= slider_idx <= 3:
                        # Flush any pending MIDI messages before starting learn
                        if self._midi_manager:
                            self._midi_manager.flush_receive_buffer()
                        self._last_midi_type = None
                        self._last_midi_num = None
                        self._last_midi_ch = None
                        self._learn_mode = True
                        self._learn_slider_idx = slider_idx
                        self._learn_start_time = time.monotonic()
                        self._respond({"type": "learn_started", "slider": slider_idx})
                    else:
                        self._respond({"error": "Slider index must be 0-3"})
                except ValueError:
                    self._respond({"error": f"Invalid slider index: {slider_str}"})
            
            elif command == "STOP_LEARN":
                was_learning = self._learn_mode
                slider = self._learn_slider_idx
                self._learn_mode = False
                self._learn_slider_idx = -1
                self._respond({"type": "learn_stopped", "was_learning": was_learning, "slider": slider})
            
            else:
                self._respond({"error": f"Unknown command: {command}"})
        
        except Exception as e:
            self._respond({"error": str(e)})
    
    def _respond(self, data):
        """Send JSON response via serial."""
        response = "RSP:" + json.dumps(data) + "\n"
        print(response, end="")
    
    def _send_file_contents(self, filepath):
        """Read and send file contents as JSON response."""
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
            self._respond(data)
        except OSError:
            self._respond({"error": f"File not found: {filepath}"})
        except ValueError as e:
            self._respond({"error": f"Invalid JSON in {filepath}: {e}"})
    
    def _send_status(self):
        """Send current controller status for interactive UI."""
        if self._controller is None:
            self._respond({
                "type": "status",
                "held_buttons": [],
                "page": 0,
                "bank": -1,
                "last_moved_slider": -1,
                "slider_values": [0, 0, 0, 0],
                "ready": False
            })
            return
        
        # Get held button indices
        held_buttons = []
        for idx, btn in enumerate(self._controller.buttons):
            if btn.pressed:
                held_buttons.append(idx)
        
        # Get slider CC values and detect which moved
        slider_values = [s.cc_value for s in self._controller.sliders]
        
        # Detect most recently moved slider (largest change)
        max_change = 0
        moved_slider = -1
        for i, (new_val, old_val) in enumerate(zip(slider_values, self._last_slider_values)):
            change = abs(new_val - old_val)
            if change > max_change and change >= 3:  # Threshold to ignore noise
                max_change = change
                moved_slider = i
        
        if moved_slider != -1:
            self._last_moved_slider = moved_slider
        self._last_slider_values = slider_values[:]
        
        self._respond({
            "type": "status",
            "held_buttons": held_buttons,
            "page": self._controller.current_page_idx,
            "bank": self._controller.current_bank_idx,
            "locked_bank": self._controller.locked_bank_idx,
            "config_mode": self._config_mode,
            "last_moved_slider": self._last_moved_slider,
            "slider_values": slider_values,
            "last_midi_type": self._last_midi_type,
            "last_midi_num": self._last_midi_num,
            "last_midi_ch": self._last_midi_ch,
            "ready": True
        })
    
    def _save_settings(self, json_str):
        """Save settings JSON to file."""
        try:
            # Parse to validate JSON
            data = json.loads(json_str)
            
            # Write to file
            with open(SETTINGS_FILE, "w") as f:
                json.dump(data, f)
            
            self._respond({"status": "ok", "message": "Settings saved. Restart device to apply."})
        
        except ValueError as e:
            self._respond({"error": f"Invalid JSON: {e}"})
        except OSError as e:
            self._respond({"error": f"Cannot write file: {e}"})


# Global instance
serial_config = SerialConfigHandler()
