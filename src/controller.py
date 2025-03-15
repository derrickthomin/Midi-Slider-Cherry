from inputs import MidiSlider, BankButton
from midi import midi_manager
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
        self.current_bank_idx = 0  # determined by if any buttons are held. 0 is global.
        self.additional_bank_indicies = []
        self.longest_held_button_idx = 0
        self.has_anything_changed = False
        self.locked_bank_idx = -1
        self.jump_mode_enabled = False
        self.unlock_pending = False

        # Setup
        self.setup_sliders()
        self.setup_buttons()
        self.setup_cc_banks()

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
        
        # Step 1: Set unlock_pending when all buttons are released after a lock
        if self.locked_bank_idx != -1 and all_buttons_released and not self.unlock_pending:
            self.unlock_pending = True
            print("Setting unlock_pending to True - all buttons released")
        
        # Step 2: Check for double-press events to lock/unlock
        for idx, button in enumerate(self.buttons):
            if button.was_double_pressed:
                if self.locked_bank_idx == idx:
                    self.unlock_bank()
                    print(f"Unlocking bank {idx} via double-press")
                else:
                    self.lock_bank(idx)
                    print(f"Locking bank {idx}")
                return
        
        # Step 3: Check for new button press after unlock_pending is set
        if self.unlock_pending and any_new_button_press:
            self.unlock_bank()
            print("Unlocking bank via new button press")
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
            self.locked_bank_idx = -1
            self.unlock_pending = False
            self.update_active_bank()

    def send_cc_messages(self):
        """
        Sends CC messages for any slider whose value changed, if 'should_send_cc' returns True.
        """
        for slider in self.sliders:
            if slider.cc_value_changed:
                cc_numbers = [slider.current_assigned_cc_number] + slider.additional_assigned_cc_numbers
                if self.should_send_cc(slider):
                    midi_manager.send_cc(cc_numbers, slider.cc_value)
                    slider.cc_value_changed = False

    def should_send_cc(self, slider):
        """
        Determines whether a CC message should be sent based on pickup mode logic.
        
        This method implements "pickup mode" where sliders only send CC values after 
        physically crossing the last sent value, preventing sudden jumps in parameter values.
        
        Args:
            slider (MidiSlider): The slider object to check
            
        Returns:
            bool: True if a CC message should be sent, False otherwise
        """
        cc_number = slider.current_assigned_cc_number
        last_cc_sent = midi_manager.get_last_cc_value_sent(cc_number)
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
        Updates 'additional_bank_indicies' based on pressed buttons, 
        and sets 'longest_held_button_idx' for the current held button with the highest hold time.
        """
        self.additional_bank_indicies = []
        max_hold_time = 0
        max_hold_time_idx = -1

        for idx, button in enumerate(self.buttons):
            if button.pressed:
                self.additional_bank_indicies.append(idx)
            if button.hold_time > max_hold_time:
                max_hold_time = button.hold_time
                max_hold_time_idx = idx

        self.longest_held_button_idx = max_hold_time_idx
        return self.additional_bank_indicies

    def update_active_bank(self):
        """
        Decides which bank is active based on locked bank index or whichever button has the max hold time.
        Then updates slider CC assignments if necessary.
        """
        previous_bank_idx = self.current_bank_idx
        previous_additional_indicies = list(self.additional_bank_indicies)

        self.update_held_button_indicies()

        if self.locked_bank_idx != -1:
            self.current_bank_idx = self.locked_bank_idx
        else:
            self.current_bank_idx = self.longest_held_button_idx

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
            last_cc_sent = midi_manager.get_last_cc_value_sent(slider.current_assigned_cc_number)
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

    def previous_bank_group(self):
        """
        Moves to the previous bank group if available (no wrap-around).
        """
        new_idx = self.current_bank_group_idx - 1
        if new_idx >= 0:
            self.current_bank_group_idx = new_idx