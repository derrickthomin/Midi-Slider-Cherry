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

        bottom_hold_time = bottom_button.hold_time
        bottom_was_long_held = bottom_button.was_long_held
        bottom_new_release = bottom_button.detected_new_release

        # Switch to next bank group if bottom is held, top is released
        if bottom_hold_time > 0 and top_new_release and not top_was_long_held:
            self.next_bank_group()
            self.unlock_bank()
            return

        # Switch to previous bank group if top is held, bottom is released
        if top_hold_time > 0 and bottom_new_release and not bottom_was_long_held:
            self.previous_bank_group()
            self.unlock_bank()
            return

        # Check for Jump Mode
        middle_buttons_held = (middle_button_T.hold_time > 0) and (middle_button_B.hold_time > 0)
        if middle_buttons_held:
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
        
        # Clear bank_group_just_changed when all buttons are released
        if all_buttons_released:
            self.bank_group_just_changed = False
        
        # Step 1: Set unlock_pending when all buttons are released after a lock
        if self.locked_bank_idx != -1 and all_buttons_released and not self.unlock_pending:
            self.unlock_pending = True
        
        # Step 2: Check for double-press events to lock/unlock
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
        Sends CC messages for any slider whose value changed, if 'should_send_cc' returns True.
        Supports multi-channel output where each bank/row can send to multiple MIDI channels.
        """
        for slider in self.sliders:
            if slider.cc_value_changed:
                # Determine main channels (list)
                if self.current_bank_idx == -1:
                    main_channels = self.global_channels
                else:
                    main_channels = self.channel_lookup[self.current_bank_group_idx][self.current_bank_idx]
                
                # Use first channel for pickup mode check (handles overlap gracefully)
                if self.should_send_cc(slider, main_channels[0]):
                    # Build list of (cc_number, channel) tuples for all main channels
                    cc_with_channels = [(slider.current_assigned_cc_number, ch) for ch in main_channels]
                    
                    # Add additional CCs from held buttons with their respective channels
                    for i, add_cc in enumerate(slider.additional_assigned_cc_numbers):
                        row_idx = self.additional_bank_indicies[i]
                        add_channels = self.channel_lookup[self.current_bank_group_idx][row_idx]
                        for ch in add_channels:
                            cc_with_channels.append((add_cc, ch))
                    
                    midi_manager.send_cc(cc_with_channels, slider.cc_value)
                    slider.cc_value_changed = False

    def should_send_cc(self, slider, channel):
        """
        Determines whether a CC message should be sent based on pickup mode logic.
        
        This method implements "pickup mode" where sliders only send CC values after 
        physically crossing the last sent value, preventing sudden jumps in parameter values.
        
        Args:
            slider (MidiSlider): The slider object to check
            channel (int): The MIDI channel (0-indexed) for this slider's current bank
            
        Returns:
            bool: True if a CC message should be sent, False otherwise
        """
        cc_number = slider.current_assigned_cc_number
        last_cc_sent = midi_manager.get_last_cc_value_sent(cc_number, channel)
        cc_value = slider.cc_value

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
        
        # Determine the channels for pickup mode tracking (use first channel)
        if self.current_bank_idx == -1:
            current_channel = self.global_channels[0]
        else:
            current_channel = self.channel_lookup[self.current_bank_group_idx][self.current_bank_idx][0]

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

            # Step 3: Reset pickup mode tracking to prevent unwanted CC jumps
            last_cc_sent = midi_manager.get_last_cc_value_sent(slider.current_assigned_cc_number, current_channel)
            slider.crossing_cc_value = last_cc_sent
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
        """
        self.global_channels = settings.get_global_channels()
        
        # channel_lookup[bank_group_idx][row_idx] = list of 0-indexed channels
        self.channel_lookup = [
            [settings.get_resolved_channels(bg, row) for row in range(4)]
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
        """
        new_idx = self.current_bank_group_idx + 1
        if new_idx <= 3:
            self.current_bank_group_idx = new_idx
            self.bank_group_just_changed = True

    def previous_bank_group(self):
        """
        Moves to the previous bank group if available (no wrap-around).
        """
        new_idx = self.current_bank_group_idx - 1
        if new_idx >= 0:
            self.current_bank_group_idx = new_idx
            self.bank_group_just_changed = True