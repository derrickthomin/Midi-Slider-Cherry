import time
from inputs import MidiSlider, BankButton
from midi import midi_manager
from settings import settings
import constants as cfg

class MidiController:
    """
    Controls the interaction between hardware inputs (sliders and buttons) and MIDI output.

    Responsibilities:
    - Reading input states (buttons/sliders).
    - Mapping change events to MIDI control change (CC) messages.
    - Managing active and locked banks.
    """

    def __init__(self, slider_pins, button_pins):
        """
        Initialize the MidiController with slider and button pins.
        """
        self.sliders = []
        self.buttons = []
        self.slider_pins = slider_pins
        self.button_pins = button_pins

        # Tracking
        self.is_muted = False
        self.current_bank_group_idx = 0
        self.current_bank_idx = 0  # determined by if any buttons are held. -1 is global.
        self.held_button_order = []  # Tracks button press order; first is primary, rest are additional
        self.primary_bank_idx = -1  # Derived from held_button_order[0], -1 = global
        self.additional_bank_indicies = []  # Derived from held_button_order[1:]
        self.has_anything_changed = False
        self.locked_bank_idx = -1
        self.jump_mode_enabled = False
        self.unlock_pending = False
        self.bank_group_just_changed = False  # For showing indicator during navigation
        
        # Double-press filter: ignore double-press on same button that was just unlocked
        self._last_unlocked_bank_idx = -1
        self._last_unlock_time = 0

        # Bank change mode state
        self.bank_change_mode_active = False  # True when in bank change mode (hide all button colors)
        self.bank_change_exit_button_idx = -1  # Button that must be released to exit bank change mode
        self.bank_limit_blink_idx = -1  # Button pixel to blink when at min/max
        self.bank_limit_blink_time = 0  # When the blink started
        self.bank_limit_blink_duration = 0.12  # Total on-off-on cycle duration (fast)
        self.bank_limit_blink_locked = False  # If True, blink cycle is running and won't reset

        # Setup
        self.setup_sliders()
        self.setup_buttons()
        self.setup_cc_banks()
        self.setup_channel_lookup()

    def setup_sliders(self):
        """
        Initializes the slider objects using the given slider pins.
        """
        for idx, pin in enumerate(self.slider_pins):
            self.sliders.append(MidiSlider(pin, idx))

    def setup_buttons(self):
        """
        Initializes the button objects using the given button pins.
        """
        for pin in self.button_pins:
            self.buttons.append(BankButton(pin))

    def update_inputs(self):
        """
        Updates all sliders and buttons and sets 'has_anything_changed' if any input changed.
        Returns:
            bool: True if any slider or button changed state, False otherwise.
        """
        slider_changes = [slider.update() for slider in self.sliders]
        button_changes = [button.update() for button in self.buttons]
        self.has_anything_changed = any(slider_changes + button_changes)
        return self.has_anything_changed

    def process_inputs(self):
        """
        Processes input changes. Determines if any bank/bank-group changes are needed.
        Also checks if Jump Mode should toggle based on button events.
        """
        if not self.has_anything_changed:
            return

        self.handle_lock_changes()

        top_button = self.buttons[-1]
        middle_button_T = self.buttons[1]
        middle_button_B = self.buttons[2]
        bottom_button = self.buttons[0]

        top_hold_time = top_button.hold_time
        top_was_long_held = top_button.was_long_held
        top_new_release = top_button.detected_new_release
        top_new_press = top_button.detected_new_press

        bottom_hold_time = bottom_button.hold_time
        bottom_was_long_held = bottom_button.was_long_held
        bottom_new_release = bottom_button.detected_new_release
        bottom_new_press = bottom_button.detected_new_press
        
        # Check if middle buttons are held (prevents bank switch when multi-bank holding)
        middle_buttons_held = (middle_button_T.hold_time > 0) or (middle_button_B.hold_time > 0)
        
        # Check if ONLY the initiating button is held (for entering bank change mode)
        only_bottom_held = bottom_button.pressed and not any(b.pressed for b in [top_button, middle_button_T, middle_button_B])
        only_top_held = top_button.pressed and not any(b.pressed for b in [bottom_button, middle_button_T, middle_button_B])

        # Bank group switching logic:
        # - First switch uses release (to distinguish from multi-bank hold intent)
        # - Once in bank change mode, use click for faster switching
        # - Only allow ENTERING bank change mode if ONLY the initiating button is held
        # - While IN bank change mode, no restrictions (works as before)
        
        # Switch to next bank group (bottom held, top activated)
        if bottom_hold_time > 0:
            if self.bank_change_mode_active and top_new_press:
                # Already in bank change mode - switch on click for rapid switching (no restrictions)
                self.next_bank_group()
                self.unlock_bank()
                return
            elif not self.bank_change_mode_active and top_new_release and not top_was_long_held and only_bottom_held:
                # Entering bank change mode - only allow if ONLY bottom is held
                self.next_bank_group()
                self.unlock_bank()
                return

        # Switch to previous bank group (top held, bottom activated)
        if top_hold_time > 0:
            if self.bank_change_mode_active and bottom_new_press:
                # Already in bank change mode - switch on click for rapid switching (no restrictions)
                self.previous_bank_group()
                self.unlock_bank()
                return
            elif not self.bank_change_mode_active and bottom_new_release and not bottom_was_long_held and only_top_held:
                # Entering bank change mode - only allow if ONLY top is held
                self.previous_bank_group()
                self.unlock_bank()
                return

        # Check for Jump Mode (requires BOTH middle buttons held)
        both_middle_buttons_held = (middle_button_T.hold_time > 0) and (middle_button_B.hold_time > 0)
        if both_middle_buttons_held:
            if top_new_release and not top_was_long_held:
                self.jump_mode_enabled = not self.jump_mode_enabled
                return  # Exit after toggling jump mode

            if bottom_new_release and not bottom_was_long_held:
                self.jump_mode_enabled = not self.jump_mode_enabled
                return  # Exit after toggling jump mode

        self.update_active_bank()
        self.send_cc_messages()

    def handle_lock_changes(self):
        """
        Checks if any button was double-pressed to lock/unlock the corresponding bank.
        Also handles unlocking once all buttons are released, if 'unlock_pending' is set.
        """
        # Check button states
        all_buttons_released = all(not button.pressed for button in self.buttons)
        any_new_button_press = any(button.detected_new_press for button in self.buttons)
        
        # Check if exit button for bank change mode was released
        if self.bank_change_mode_active and self.bank_change_exit_button_idx != -1:
            if not self.buttons[self.bank_change_exit_button_idx].pressed:
                # Exit button released - exit bank change mode
                self.bank_change_mode_active = False
                self.bank_change_exit_button_idx = -1
                self.bank_limit_blink_idx = -1
                self.bank_limit_blink_locked = False
        
        # Clear bank_group_just_changed when all buttons are released
        if all_buttons_released:
            self.bank_group_just_changed = False
            # Also clear bank change mode state when all released
            self.bank_change_mode_active = False
            self.bank_change_exit_button_idx = -1
            self.bank_limit_blink_idx = -1
            self.bank_limit_blink_locked = False
        
        # Step 1: Set unlock_pending when all buttons are released after a lock
        if self.locked_bank_idx != -1 and all_buttons_released and not self.unlock_pending:
            self.unlock_pending = True
        
        # Step 2: Check for double-press events to lock/unlock
        # Skip if in bank change mode - no locking allowed until mode exits
        if not self.bank_change_mode_active:
            for idx, button in enumerate(self.buttons):
                if button.was_double_pressed:
                    time_since_unlock = time.monotonic() - self._last_unlock_time
                    
                    # Filter: ignore double-press on same button that was just unlocked (within DOUBLE_PRESS_TIME)
                    if idx == self._last_unlocked_bank_idx and time_since_unlock < cfg.DOUBLE_PRESS_TIME:
                        continue
                    
                    if self.locked_bank_idx == idx:
                        self.unlock_bank()
                    else:
                        self.lock_bank(idx)
                    return
        
        # Step 3: Check for new button press after unlock_pending is set
        if self.unlock_pending and any_new_button_press:
            self.unlock_bank()
            return

    def lock_bank(self, bank_idx):
        """
        Locks the given bank index and updates the active bank accordingly.
        """
        self.locked_bank_idx = bank_idx
        self.unlock_pending = False
        self.update_active_bank()

    def unlock_bank(self):
        """
        Unlocks any currently locked bank and updates the active bank.
        """
        if self.locked_bank_idx != -1:
            # Track which bank was unlocked and when (for double-press filtering)
            self._last_unlocked_bank_idx = self.locked_bank_idx
            self._last_unlock_time = time.monotonic()
            self.locked_bank_idx = -1
            self.unlock_pending = False
            self.update_active_bank()

    def send_cc_messages(self):
        """
        Sends MIDI messages for any slider whose value changed, if 'should_send_cc' returns True.
        Supports multi-channel output where each bank/row can send to multiple MIDI channels.
        Handles both CC (Control Change) and AT (Channel Aftertouch) message types.
        Each bank (primary and additional) sends according to its own type setting.
        """
        for slider_idx, slider in enumerate(self.sliders):
            if slider.cc_value_changed:
                # Determine main channels and message type
                if self.current_bank_idx == -1:
                    main_channels = self.global_channels
                    main_type = self.global_message_type
                    main_row_idx = -1  # Global bank
                else:
                    main_channels = self.channel_lookup[self.current_bank_group_idx][self.current_bank_idx]
                    main_type = self.type_lookup[self.current_bank_group_idx][self.current_bank_idx]
                    main_row_idx = self.current_bank_idx
                
                # Use first channel for pickup mode check (handles overlap gracefully)
                if self.should_send_cc(slider, slider_idx, main_channels[0], main_type, main_row_idx):
                    # Send primary bank message based on its type
                    if main_type == "AT":
                        midi_manager.send_aftertouch(main_channels, slider.cc_value, 
                                                      slider_idx, self.current_bank_group_idx, main_row_idx)
                    else:
                        cc_with_channels = [(slider.current_assigned_cc_number, ch) for ch in main_channels]
                        midi_manager.send_cc(cc_with_channels, slider.cc_value)
                    
                    # Process each additional bank according to its own type
                    for i, add_cc in enumerate(slider.additional_assigned_cc_numbers):
                        row_idx = self.additional_bank_indicies[i]
                        add_channels = self.channel_lookup[self.current_bank_group_idx][row_idx]
                        add_type = self.type_lookup[self.current_bank_group_idx][row_idx]
                        
                        if add_type == "AT":
                            midi_manager.send_aftertouch(add_channels, slider.cc_value,
                                                          slider_idx, self.current_bank_group_idx, row_idx)
                        else:
                            cc_with_channels = [(add_cc, ch) for ch in add_channels]
                            midi_manager.send_cc(cc_with_channels, slider.cc_value)
                    
                    slider.cc_value_changed = False

    def should_send_cc(self, slider, slider_idx, channel, message_type="CC", row_idx=-1):
        """
        Determines whether a MIDI message should be sent based on pickup mode logic.
        
        This method implements "pickup mode" where sliders only send values after 
        physically crossing the last sent value, preventing sudden jumps in parameter values.
        
        Args:
            slider (MidiSlider): The slider object to check
            slider_idx (int): Index of the slider (0-3)
            channel (int): The MIDI channel (0-indexed) for this slider's current bank
            message_type (str): "CC" for Control Change, "AT" for Channel Aftertouch
            row_idx (int): Row index (-1 for global, 0-3 for banks)
            
        Returns:
            bool: True if a message should be sent, False otherwise
        """
        cc_number = slider.current_assigned_cc_number
        cc_value = slider.cc_value
        
        # Get last sent value based on message type
        # For AT, use per-slider tracking for independent pickup behavior
        if message_type == "AT":
            last_cc_sent = midi_manager.get_last_at_value_per_slider(slider_idx, self.current_bank_group_idx, row_idx)
        else:
            last_cc_sent = midi_manager.get_last_cc_value_sent(cc_number, channel)

        # Jump Mode always allows sending values immediately
        if self.jump_mode_enabled:
            return True
            
        # First-time initialization of crossing values
        if slider.crossing_cc_value == -1:
            slider.crossing_cc_value = cc_value
            slider.has_crossed_last_cc_value = False
            return False
            
        # Special handling for min/max edge values
        if last_cc_sent == cfg.MIN_CC_VALUE and cfg.MIN_CC_VALUE <= cc_value <= 2:
            slider.has_crossed_last_cc_value = True
            return True
            
        if last_cc_sent == cfg.MAX_CC_VALUE and 125 <= cc_value <= cfg.MAX_CC_VALUE:
            slider.has_crossed_last_cc_value = True
            return True
            
        # Once crossed threshold, continue sending all values
        if slider.has_crossed_last_cc_value:
            return True
            
        # Check if slider has crossed the last value from either direction
        crossed_from_above = cc_value < last_cc_sent < slider.crossing_cc_value
        crossed_from_below = cc_value > last_cc_sent > slider.crossing_cc_value
        
        if crossed_from_above or crossed_from_below:
            slider.has_crossed_last_cc_value = True
            return True
            
        # Skip small changes within the deadband
        if abs(cc_value - last_cc_sent) < cfg.CC_THRESHOLD:
            return False
            
        # Update tracking value for future comparisons
        slider.crossing_cc_value = cc_value
        return False

    def update_held_button_indicies(self):
        """
        Updates 'held_button_order' to track button press order.
        
        - New presses are appended to the list (preserving order)
        - Released buttons are removed from wherever they are in the list
        - First element is the primary bank, rest are additional
        - When list is empty, we're in global bank mode
        """
        # Add newly pressed buttons to the end of the order list
        for idx, button in enumerate(self.buttons):
            if button.detected_new_press and idx not in self.held_button_order:
                self.held_button_order.append(idx)
        
        # Remove released buttons from the order list
        self.held_button_order = [idx for idx in self.held_button_order 
                                   if self.buttons[idx].pressed]
        
        # Derive primary and additional from the order list
        if self.held_button_order:
            self.primary_bank_idx = self.held_button_order[0]
            self.additional_bank_indicies = self.held_button_order[1:]
        else:
            self.primary_bank_idx = -1
            self.additional_bank_indicies = []
        
        return self.additional_bank_indicies

    def update_active_bank(self):
        """
        Decides which bank is active based on locked bank index or the primary held button.
        Then updates slider CC assignments if necessary.
        """
        previous_bank_idx = self.current_bank_idx
        previous_additional_indicies = list(self.additional_bank_indicies)

        self.update_held_button_indicies()

        if self.locked_bank_idx != -1:
            self.current_bank_idx = self.locked_bank_idx
        else:
            self.current_bank_idx = self.primary_bank_idx

        # Reassign CC numbers if we switched banks or changed held-button indices
        if (previous_bank_idx != self.current_bank_idx 
            or previous_additional_indicies != self.additional_bank_indicies):
            self.update_slider_cc_assignments()

    def update_slider_cc_assignments(self):
        """
        Updates each slider's CC assignments based on the current active bank.
        
        This method:
        1. Assigns the primary CC number from the current bank
        2. Adds any additional CC numbers from simultaneously held buttons
        3. Resets pickup-mode tracking values to ensure smooth transitions
        """
        current_cc_bank = self.get_current_cc_bank()
        
        # Determine the channels and message type for pickup mode tracking
        if self.current_bank_idx == -1:
            current_channel = self.global_channels[0]
            current_type = self.global_message_type
        else:
            current_channel = self.channel_lookup[self.current_bank_group_idx][self.current_bank_idx][0]
            current_type = self.type_lookup[self.current_bank_group_idx][self.current_bank_idx]

        for idx, slider in enumerate(self.sliders):
            # Step 1: Assign primary CC number
            if self.current_bank_idx == -1:
                # Global bank
                slider.current_assigned_cc_number = cfg.GLOBAL_CC_BANK[idx]
                slider.additional_assigned_cc_numbers = []
            else:
                # Bank from current group
                slider.current_assigned_cc_number = current_cc_bank[idx]
                
                # Step 2: Add any secondary CC assignments from additional held buttons
                if self.additional_bank_indicies:
                    slider.additional_assigned_cc_numbers = self.get_additional_cc_numbers(idx)
                else:
                    slider.additional_assigned_cc_numbers = []

            # Step 3: Reset pickup mode tracking to prevent unwanted jumps
            # Use appropriate last value based on message type (per-slider for AT)
            if current_type == "AT":
                last_sent = midi_manager.get_last_at_value_per_slider(idx, self.current_bank_group_idx, self.current_bank_idx)
            else:
                last_sent = midi_manager.get_last_cc_value_sent(slider.current_assigned_cc_number, current_channel)
            slider.crossing_cc_value = last_sent
            
            # If slider is already at/near the target value, consider it "picked up"
            # This prevents requiring a wiggle when re-entering a bank at the same position
            if abs(slider.cc_value - last_sent) <= cfg.CC_THRESHOLD:
                slider.has_crossed_last_cc_value = True
            else:
                slider.has_crossed_last_cc_value = False
            slider.cc_value_changed = False

    def setup_cc_banks(self):
        """
        Prepares the main and per-group CC banks.
        """
        self.global_cc_bank = cfg.GLOBAL_CC_BANK

        self.cc_bank_groups = cfg.CC_BANK_GROUPS

        # Default global CC assignments
        for idx, slider in enumerate(self.sliders):
            slider.current_assigned_cc_number = self.global_cc_bank[idx]

    def setup_channel_lookup(self):
        """
        Precomputes the MIDI channel lookup table for all bank groups and rows.
        Also stores the global channels for the global CC bank.
        Each entry is now a list of channels to support multi-channel output.
        Additionally precomputes message type lookup for CC vs Aftertouch.
        """
        self.global_channels = settings.get_global_channels()
        self.global_message_type = settings.get_global_message_type()
        
        # channel_lookup[bank_group_idx][row_idx] = list of 0-indexed channels
        self.channel_lookup = [
            [settings.get_resolved_channels(bg, row) for row in range(4)]
            for bg in range(4)
        ]
        
        # type_lookup[bank_group_idx][row_idx] = "CC" or "AT"
        self.type_lookup = [
            [settings.get_resolved_message_type(bg, row) for row in range(4)]
            for bg in range(4)
        ]

    def get_current_cc_bank(self):
        """
        Returns the CC bank list for the currently active bank index,
        or the global CC bank if current_bank_idx is -1.
        """
        if self.current_bank_idx == -1:
            return self.global_cc_bank
        return self.cc_bank_groups[self.current_bank_group_idx][self.current_bank_idx]

    def get_additional_cc_numbers(self, idx):
        """
        Returns extra CC numbers from other held buttons' banks for the slider at 'idx'.
        """
        additional_cc_numbers = []
        for button_idx in self.additional_bank_indicies:
            bank = self.cc_bank_groups[self.current_bank_group_idx][button_idx]
            additional_cc_numbers.append(bank[idx])
        return additional_cc_numbers

    def next_bank_group(self):
        """
        Moves to the next bank group if available (no wrap-around).
        Enters bank change mode - hides all button colors until exit button released.
        """
        current_time = time.monotonic()
        new_idx = self.current_bank_group_idx + 1
        
        # Enter bank change mode - bottom button (idx 0) must be released to exit
        self.bank_change_mode_active = True
        self.bank_change_exit_button_idx = 0
        self.bank_group_just_changed = True
        
        if new_idx <= 3:
            self.current_bank_group_idx = new_idx
            # Clear any pending limit blink on successful change
            self.bank_limit_blink_idx = -1
            self.bank_limit_blink_locked = False
        else:
            # Already at max - trigger a quick blink on the bank indicator pixel
            # Only start new blink if not already in a locked blink cycle
            if not self.bank_limit_blink_locked:
                self.bank_limit_blink_idx = self.current_bank_group_idx
                self.bank_limit_blink_time = current_time
                self.bank_limit_blink_locked = True

    def previous_bank_group(self):
        """
        Moves to the previous bank group if available (no wrap-around).
        Enters bank change mode - hides all button colors until exit button released.
        """
        current_time = time.monotonic()
        new_idx = self.current_bank_group_idx - 1
        
        # Enter bank change mode - top button (idx 3) must be released to exit
        self.bank_change_mode_active = True
        self.bank_change_exit_button_idx = 3
        self.bank_group_just_changed = True
        
        if new_idx >= 0:
            self.current_bank_group_idx = new_idx
            # Clear any pending limit blink on successful change
            self.bank_limit_blink_idx = -1
            self.bank_limit_blink_locked = False
        else:
            # Already at min - trigger a quick blink on the bank indicator pixel
            # Only start new blink if not already in a locked blink cycle
            if not self.bank_limit_blink_locked:
                self.bank_limit_blink_idx = self.current_bank_group_idx
                self.bank_limit_blink_time = current_time
                self.bank_limit_blink_locked = True

    def update_bank_change_feedback(self):
        """
        Returns current bank change mode feedback state for use by the lights manager.
        
        When in bank change mode, all button colors are hidden - only the bank indicator
        (white dot) is shown, or the blink animation if at a limit.
        
        Blink cycle is on-off-on to ensure visibility even with repeated attempts.
        
        Returns:
            dict: {
                'bank_change_mode': bool (True if in bank change mode - hide all button colors),
                'blink_button_idx': int (-1 if none),
                'blink_off': bool (True if we're in the "off" phase of the blink)
            }
        """
        current_time = time.monotonic()
        blink_button_idx = -1
        blink_off = False
        
        # Check if limit blink is active (on-off-on cycle)
        if self.bank_limit_blink_idx != -1:
            elapsed = current_time - self.bank_limit_blink_time
            if elapsed < self.bank_limit_blink_duration:
                blink_button_idx = self.bank_limit_blink_idx
                # Divide cycle into thirds: ON (0-33%), OFF (33-66%), ON (66-100%)
                cycle_position = elapsed / self.bank_limit_blink_duration
                blink_off = (0.33 <= cycle_position < 0.66)
            else:
                # Blink cycle complete - unlock and clear
                self.bank_limit_blink_idx = -1
                self.bank_limit_blink_locked = False
        
        return {
            'bank_change_mode': self.bank_change_mode_active,
            'blink_button_idx': blink_button_idx,
            'blink_off': blink_off
        }