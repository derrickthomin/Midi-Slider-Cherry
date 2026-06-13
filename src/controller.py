import time
from inputs import MidiSlider, BankButton
from midi import midi_manager
from settings import settings
from loopmanager import (LoopManager, SLOT_EMPTY, SLOT_RECORDING,
                         SLOT_PLAYING, SLOT_STOPPED)
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
        self.current_page_idx = 0
        self.current_bank_idx = 0  # determined by if any buttons are held. -1 is global.
        self.held_button_order = []  # Tracks button press order; first is primary, rest are additional
        self.primary_bank_idx = -1  # Derived from held_button_order[0], -1 = global
        self.additional_bank_indicies = []  # Derived from held_button_order[1:]
        self.has_anything_changed = False
        self.locked_bank_idx = -1
        self.jump_mode_enabled = False
        self.unlock_pending = False
        self.page_just_changed = False  # For showing indicator during navigation
        
        # Double-press filter: ignore double-press on same button that was just unlocked
        self._last_unlocked_bank_idx = -1
        self._last_unlock_time = 0

        # Page change mode state
        self.page_change_mode_active = False  # True when in page change mode (hide all button colors)
        self.page_change_exit_button_idx = -1  # Button that must be released to exit page change mode
        self.page_limit_blink_idx = -1  # Button pixel to blink when at min/max
        self.page_limit_blink_time = 0  # When the blink started
        self.page_limit_blink_duration = 0.12  # Total on-off-on cycle duration (fast)
        self.page_limit_blink_locked = False  # If True, blink cycle is running and won't reset
        
        # Config mode: single click locks banks (for web config interface)
        self.config_mode = False

        # ==================== Record Mode state ====================
        self.record_mode_active = False
        self.record_mode_just_toggled = False  # code.py plays the enter/exit animation, then clears
        self.record_cc_set_idx = 0  # 0 = global bank, 1-4 = page 1 banks (separate from page/bank state, gotcha 9.3)
        self.loop_manager = LoopManager()

        # Hold-all-four-buttons mode-toggle detection
        self._mode_hold_start = 0     # time.monotonic() when all four went down; 0 = not armed
        self._mode_hold_fired = False  # toggled already on this hold; waiting for releases

        # One-shot release suppression: a button's next release fires no gesture/slot
        # action (mode-toggle participants, set-navigation held button, etc.)
        self._suppress_release = [False] * 4

        # Per-slot click state machine (release-based; gotcha 9.1 - don't use
        # BankButton.was_double_pressed for click counting)
        self._slot_last_press_time = [0.0] * 4
        self._slot_pending_record = [False] * 4    # start recording on this button's next release
        self._slot_prev_play_state = [False] * 4   # play state at first press of a pair (delete restore)
        self._slot_ignore_press_until = [0.0] * 4  # swallow presses right after a stop-recording click

        # Delete arm/confirm state
        self._delete_armed_slot = -1
        self._delete_armed_time = 0.0
        self._delete_restore_play = False

        # Record-mode CC-set navigation (mirrors normal-mode page change)
        self._rec_nav_active = False
        self._rec_nav_exit_button_idx = -1

        # CC-set switch white flash (optional polish, 3d)
        self._set_flash_time = 0.0
        self._set_flash_set_idx = -1

        # Live-values cache for cc_reset (3e): last value live-sent by the
        # physical faders, per (cc, ch) / per ch. Updated only on fader-origin
        # sends (both modes), never by the playback pump.
        self._last_live_cc_values = {}  # {(cc_number, channel): value}
        self._last_live_at_values = {}  # {channel: pressure}

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
        In Record Mode, button events drive the loop slots instead (gestures branch).
        """
        # Record-mode machinery is time-based (hold timer, delete window,
        # playback pump) and must run every iteration, even with no input
        # changes (gotcha 9.1).
        self.update_record_mode_state()

        if not self.has_anything_changed:
            return

        # Consume one-shot release suppressions (mode-toggle hold and
        # set-navigation participants): these releases fire nothing in either mode.
        swallowed = [False] * 4
        for idx, button in enumerate(self.buttons):
            if button.detected_new_release and self._suppress_release[idx]:
                self._suppress_release[idx] = False
                swallowed[idx] = True

        if self.record_mode_active:
            self.process_record_mode_inputs(swallowed)
            return

        self.handle_lock_changes()

        top_button = self.buttons[-1]
        middle_button_T = self.buttons[1]
        middle_button_B = self.buttons[2]
        bottom_button = self.buttons[0]

        top_hold_time = top_button.hold_time
        top_was_long_held = top_button.was_long_held
        top_new_release = top_button.detected_new_release and not swallowed[3]
        top_new_press = top_button.detected_new_press

        bottom_hold_time = bottom_button.hold_time
        bottom_was_long_held = bottom_button.was_long_held
        bottom_new_release = bottom_button.detected_new_release and not swallowed[0]
        bottom_new_press = bottom_button.detected_new_press
        
        # Check if middle buttons are held (prevents bank switch when multi-bank holding)
        middle_buttons_held = (middle_button_T.hold_time > 0) or (middle_button_B.hold_time > 0)
        
        # Check if ONLY the initiating button is held (for entering bank change mode)
        only_bottom_held = bottom_button.pressed and not any(b.pressed for b in [top_button, middle_button_T, middle_button_B])
        only_top_held = top_button.pressed and not any(b.pressed for b in [bottom_button, middle_button_T, middle_button_B])

        # Page switching logic:
        # - First switch uses release (to distinguish from multi-bank hold intent)
        # - Once in page change mode, use click for faster switching
        # - Only allow ENTERING page change mode if ONLY the initiating button is held
        # - While IN page change mode, no restrictions (works as before)
        
        # Switch to next page (bottom held, top activated)
        if bottom_hold_time > 0:
            if self.page_change_mode_active and top_new_press:
                # Already in page change mode - switch on click for rapid switching (no restrictions)
                self.next_page()
                self.unlock_bank()
                return
            elif not self.page_change_mode_active and top_new_release and not top_was_long_held and only_bottom_held:
                # Entering page change mode - only allow if ONLY bottom is held
                self.next_page()
                self.unlock_bank()
                return

        # Switch to previous page (top held, bottom activated)
        if top_hold_time > 0:
            if self.page_change_mode_active and bottom_new_press:
                # Already in page change mode - switch on click for rapid switching (no restrictions)
                self.previous_page()
                self.unlock_bank()
                return
            elif not self.page_change_mode_active and bottom_new_release and not bottom_was_long_held and only_top_held:
                # Entering page change mode - only allow if ONLY top is held
                self.previous_page()
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
        In config mode, single click locks/toggles banks instead of double-press.
        """
        # Check button states
        all_buttons_released = all(not button.pressed for button in self.buttons)
        any_new_button_press = any(button.detected_new_press for button in self.buttons)
        
        # Check if exit button for page change mode was released
        if self.page_change_mode_active and self.page_change_exit_button_idx != -1:
            if not self.buttons[self.page_change_exit_button_idx].pressed:
                # Exit button released - exit page change mode
                self.page_change_mode_active = False
                self.page_change_exit_button_idx = -1
                self.page_limit_blink_idx = -1
                self.page_limit_blink_locked = False
        
        # Clear page_just_changed when all buttons are released
        if all_buttons_released:
            self.page_just_changed = False
            # Also clear page change mode state when all released
            self.page_change_mode_active = False
            self.page_change_exit_button_idx = -1
            self.page_limit_blink_idx = -1
            self.page_limit_blink_locked = False
        
        # CONFIG MODE: Single click locks/toggles banks
        if self.config_mode and not self.page_change_mode_active:
            for idx, button in enumerate(self.buttons):
                if button.detected_new_press:
                    if self.locked_bank_idx == idx:
                        # Click on locked bank = unlock (back to global)
                        self.unlock_bank()
                    else:
                        # Click on different bank = switch lock to that bank  
                        self.lock_bank(idx)
                    return
            # In config mode, skip normal lock handling
            return
        
        # NORMAL MODE: Double-press and unlock_pending logic
        
        # Step 1: Set unlock_pending when all buttons are released after a lock
        if self.locked_bank_idx != -1 and all_buttons_released and not self.unlock_pending:
            self.unlock_pending = True
        
        # Step 2: Check for double-press events to lock/unlock
        # Skip if in page change mode - no locking allowed until mode exits
        if not self.page_change_mode_active:
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
        Supports multi-channel output where each page/bank/slider can send to multiple MIDI channels.
        Handles both CC (Control Change) and AT (Channel Aftertouch) message types.
        Each bank (primary and additional) sends according to its own type setting.
        """
        for slider_idx, slider in enumerate(self.sliders):
            if slider.cc_value_changed:
                # Determine main channels and message type
                if self.current_bank_idx == -1:
                    main_channels = self.global_slider_channels[slider_idx]
                    main_type = self.global_message_type
                    main_bank_idx = -1  # Global bank
                else:
                    main_channels = self.channel_lookup[self.current_page_idx][self.current_bank_idx][slider_idx]
                    main_type = self.type_lookup[self.current_page_idx][self.current_bank_idx]
                    main_bank_idx = self.current_bank_idx

                # Use first channel for pickup mode check (handles overlap gracefully)
                if self.should_send_cc(slider, slider_idx, main_channels[0], main_type, main_bank_idx):
                    # Send primary bank message based on its type
                    if main_type == "AT":
                        midi_manager.send_aftertouch(main_channels, slider.cc_value,
                                                      slider_idx, self.current_page_idx, main_bank_idx)
                        self._update_live_at_cache(main_channels, slider.cc_value)
                    else:
                        cc_with_channels = [(slider.current_assigned_cc_number, ch) for ch in main_channels]
                        midi_manager.send_cc(cc_with_channels, slider.cc_value)
                        self._update_live_cc_cache(slider.current_assigned_cc_number, main_channels, slider.cc_value)

                    # Process each additional bank according to its own type
                    for i, add_cc in enumerate(slider.additional_assigned_cc_numbers):
                        bank_idx = self.additional_bank_indicies[i]
                        add_channels = self.channel_lookup[self.current_page_idx][bank_idx][slider_idx]
                        add_type = self.type_lookup[self.current_page_idx][bank_idx]

                        if add_type == "AT":
                            midi_manager.send_aftertouch(add_channels, slider.cc_value,
                                                          slider_idx, self.current_page_idx, bank_idx)
                            self._update_live_at_cache(add_channels, slider.cc_value)
                        else:
                            cc_with_channels = [(add_cc, ch) for ch in add_channels]
                            midi_manager.send_cc(cc_with_channels, slider.cc_value)
                            self._update_live_cc_cache(add_cc, add_channels, slider.cc_value)

                    slider.cc_value_changed = False

    def _update_live_cc_cache(self, cc_number, channels, value):
        """Track the last value live-sent by the physical faders per (cc, channel).
        Feeds the cc_reset scan (3e). Never called from the playback pump."""
        for channel in channels:
            self._last_live_cc_values[(cc_number, channel)] = value

    def _update_live_at_cache(self, channels, pressure):
        for channel in channels:
            self._last_live_at_values[channel] = pressure

    def should_send_cc(self, slider, slider_idx, channel, message_type="CC", bank_idx=-1, page_idx=None):
        """
        Determines whether a MIDI message should be sent based on pickup mode logic.

        This method implements "pickup mode" where sliders only send values after
        physically crossing the last sent value, preventing sudden jumps in parameter values.

        Args:
            slider (MidiSlider): The slider object to check
            slider_idx (int): Index of the slider (0-3)
            channel (int): The MIDI channel (0-indexed) for this slider's current bank
            message_type (str): "CC" for Control Change, "AT" for Channel Aftertouch
            bank_idx (int): Bank index (-1 for global, 0-3 for banks)
            page_idx (int): Page index for AT per-slider tracking; None = current page
                (Record Mode passes 0 since its sets all live on page 1)

        Returns:
            bool: True if a message should be sent, False otherwise
        """
        cc_number = slider.current_assigned_cc_number
        cc_value = slider.cc_value
        if page_idx is None:
            page_idx = self.current_page_idx

        # Get last sent value based on message type
        # For AT, use per-slider tracking for independent pickup behavior
        if message_type == "AT":
            last_cc_sent = midi_manager.get_last_at_value_per_slider(slider_idx, page_idx, bank_idx)
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

        for idx, slider in enumerate(self.sliders):
            # Step 1: Assign primary CC number
            if self.current_bank_idx == -1:
                # Global bank
                slider.current_assigned_cc_number = cfg.GLOBAL_CC_BANK[idx]
                slider.additional_assigned_cc_numbers = []
                current_channel = self.global_slider_channels[idx][0]
                current_type = self.global_message_type
            else:
                # Bank from current group
                slider.current_assigned_cc_number = current_cc_bank[idx]
                current_channel = self.channel_lookup[self.current_page_idx][self.current_bank_idx][idx][0]
                current_type = self.type_lookup[self.current_page_idx][self.current_bank_idx]

                # Step 2: Add any secondary CC assignments from additional held buttons
                if self.additional_bank_indicies:
                    slider.additional_assigned_cc_numbers = self.get_additional_cc_numbers(idx)
                else:
                    slider.additional_assigned_cc_numbers = []

            # Step 3: Reset pickup mode tracking to prevent unwanted jumps
            # Use appropriate last value based on message type (per-slider for AT)
            if current_type == "AT":
                last_sent = midi_manager.get_last_at_value_per_slider(idx, self.current_page_idx, self.current_bank_idx)
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
        Prepares the main and per-page CC banks.
        """
        self.global_cc_bank = cfg.GLOBAL_CC_BANK

        self.pages = cfg.PAGES

        # Default global CC assignments
        for idx, slider in enumerate(self.sliders):
            slider.current_assigned_cc_number = self.global_cc_bank[idx]

    def setup_channel_lookup(self):
        """
        Precomputes the MIDI channel lookup table for all pages, banks, and sliders.
        Also stores the global slider channels for per-slider overrides in the global bank.
        Each entry is a list of channels to support multi-channel output.
        Additionally precomputes message type lookup for CC vs Aftertouch.
        """
        self.global_channels = settings.get_global_channels()
        self.global_message_type = settings.get_global_message_type()

        # global_slider_channels[slider_idx] = list of 0-indexed channels
        self.global_slider_channels = [
            settings.get_resolved_global_slider_channels(slider)
            for slider in range(4)
        ]

        # channel_lookup[page_idx][bank_idx][slider_idx] = list of 0-indexed channels
        self.channel_lookup = [
            [
                [settings.get_resolved_slider_channels(page, bank, slider) for slider in range(4)]
                for bank in range(4)
            ]
            for page in range(4)
        ]

        # type_lookup[page_idx][bank_idx] = "CC" or "AT"
        self.type_lookup = [
            [settings.get_resolved_message_type(page, bank) for bank in range(4)]
            for page in range(4)
        ]

    def get_current_cc_bank(self):
        """
        Returns the CC bank list for the currently active bank index,
        or the global CC bank if current_bank_idx is -1.
        """
        if self.current_bank_idx == -1:
            return self.global_cc_bank
        return self.pages[self.current_page_idx][self.current_bank_idx]

    def get_additional_cc_numbers(self, idx):
        """
        Returns extra CC numbers from other held buttons' banks for the slider at 'idx'.
        """
        additional_cc_numbers = []
        for button_idx in self.additional_bank_indicies:
            bank = self.pages[self.current_page_idx][button_idx]
            additional_cc_numbers.append(bank[idx])
        return additional_cc_numbers

    def next_page(self):
        """
        Moves to the next page if available (no wrap-around).
        Enters page change mode - hides all button colors until exit button released.
        """
        current_time = time.monotonic()
        new_idx = self.current_page_idx + 1
        
        # Enter page change mode - bottom button (idx 0) must be released to exit
        self.page_change_mode_active = True
        self.page_change_exit_button_idx = 0
        self.page_just_changed = True
        
        if new_idx <= 3:
            self.current_page_idx = new_idx
            # Clear any pending limit blink on successful change
            self.page_limit_blink_idx = -1
            self.page_limit_blink_locked = False
        else:
            # Already at max - trigger a quick blink on the page indicator pixel
            # Only start new blink if not already in a locked blink cycle
            if not self.page_limit_blink_locked:
                self.page_limit_blink_idx = self.current_page_idx
                self.page_limit_blink_time = current_time
                self.page_limit_blink_locked = True

    def previous_page(self):
        """
        Moves to the previous page if available (no wrap-around).
        Enters page change mode - hides all button colors until exit button released.
        """
        current_time = time.monotonic()
        new_idx = self.current_page_idx - 1
        
        # Enter page change mode - top button (idx 3) must be released to exit
        self.page_change_mode_active = True
        self.page_change_exit_button_idx = 3
        self.page_just_changed = True
        
        if new_idx >= 0:
            self.current_page_idx = new_idx
            # Clear any pending limit blink on successful change
            self.page_limit_blink_idx = -1
            self.page_limit_blink_locked = False
        else:
            # Already at min - trigger a quick blink on the page indicator pixel
            # Only start new blink if not already in a locked blink cycle
            if not self.page_limit_blink_locked:
                self.page_limit_blink_idx = self.current_page_idx
                self.page_limit_blink_time = current_time
                self.page_limit_blink_locked = True

    def update_page_change_feedback(self):
        """
        Returns current page change mode feedback state for use by the lights manager.
        
        When in page change mode, all button colors are hidden - only the page indicator
        (white dot) is shown, or the blink animation if at a limit.
        
        Blink cycle is on-off-on to ensure visibility even with repeated attempts.
        
        Returns:
            dict: {
                'page_change_mode': bool (True if in page change mode - hide all button colors),
                'blink_button_idx': int (-1 if none),
                'blink_off': bool (True if we're in the "off" phase of the blink)
            }
        """
        current_time = time.monotonic()
        blink_button_idx = -1
        blink_off = False
        
        # Check if limit blink is active (on-off-on cycle)
        if self.page_limit_blink_idx != -1:
            elapsed = current_time - self.page_limit_blink_time
            if elapsed < self.page_limit_blink_duration:
                blink_button_idx = self.page_limit_blink_idx
                # Divide cycle into thirds: ON (0-33%), OFF (33-66%), ON (66-100%)
                cycle_position = elapsed / self.page_limit_blink_duration
                blink_off = (0.33 <= cycle_position < 0.66)
            else:
                # Blink cycle complete - unlock and clear
                self.page_limit_blink_idx = -1
                self.page_limit_blink_locked = False
        
        return {
            'page_change_mode': self.page_change_mode_active,
            'blink_button_idx': blink_button_idx,
            'blink_off': blink_off
        }

    # ==================== Record Mode ====================

    def update_record_mode_state(self):
        """
        Time-based Record Mode machinery, run every main-loop iteration
        regardless of input changes: the hold-all-four toggle timer, the
        delete-confirm window, recording caps, and the playback pump.
        """
        now = time.monotonic()

        # Web config mode and Record Mode are mutually exclusive (gotcha 9.11)
        if self.config_mode and self.record_mode_active:
            self._toggle_record_mode()

        self._update_mode_hold(now)

        if self.record_mode_active:
            self._update_delete_arm_timeout(now)
            # Hitting an event/memory/time cap auto-stops the recording
            # exactly like a manual stop.  Apply the same post-stop ignore
            # window as a manual stop so a click racing the cap can't pair
            # into a double-press and arm delete on the brand-new loop (3b).
            auto_stopped = self.loop_manager.check_recording_limits()
            if auto_stopped >= 0:
                self._slot_ignore_press_until[auto_stopped] = now + cfg.DOUBLE_PRESS_TIME
                self._slot_last_press_time[auto_stopped] = 0.0
            self.process_loop_playback()

    def _update_mode_hold(self, now):
        """Detect the hold-all-four-buttons-for-3s Record Mode toggle."""
        if not all(button.pressed for button in self.buttons):
            self._mode_hold_start = 0
            self._mode_hold_fired = False
            return

        if self.config_mode:
            # All-four hold is ignored while the web config is connected
            self._mode_hold_start = 0
            return

        if self._mode_hold_fired:
            return  # Already toggled on this hold; waiting for the releases

        if self._mode_hold_start == 0:
            self._mode_hold_start = now
            # All four buttons participate in the hold: their releases must
            # not leak into either mode's gestures (suppression rule c, 3b) -
            # this also covers the jump-mode combo an aborted hold would match.
            for idx in range(4):
                self._suppress_release[idx] = True
            self._reset_slot_click_state()
        elif now - self._mode_hold_start >= cfg.RECORD_MODE_HOLD_S:
            self._mode_hold_fired = True
            self._toggle_record_mode()

    @property
    def mode_hold_pixels_lit(self):
        """How many button pixels of red hold-progress fill to show (0-4)."""
        if self._mode_hold_start == 0 or self._mode_hold_fired:
            return 0
        elapsed = time.monotonic() - self._mode_hold_start
        pixels_lit = int(elapsed / cfg.RECORD_MODE_HOLD_STEP_S)
        return min(pixels_lit, 4)

    def _toggle_record_mode(self):
        if self.record_mode_active:
            self._exit_record_mode()
        else:
            self._enter_record_mode()
        self.record_mode_just_toggled = True

        # Hard-reset normal-mode gesture state so the trailing releases land
        # clean in the other mode (gotcha 9.2)
        self.unlock_bank()
        self.held_button_order = []
        self.primary_bank_idx = -1
        self.additional_bank_indicies = []
        self.unlock_pending = False
        self.page_change_mode_active = False
        self.page_change_exit_button_idx = -1
        self.page_limit_blink_idx = -1
        self.page_limit_blink_locked = False
        self.page_just_changed = False

        # Reset record-mode gesture state
        self._reset_slot_click_state()
        self._rec_nav_active = False
        self._rec_nav_exit_button_idx = -1
        self._set_flash_set_idx = -1

    def _enter_record_mode(self):
        self.record_mode_active = True
        self.record_cc_set_idx = 0  # Always start in the global set
        self.update_record_slider_assignments()

    def _exit_record_mode(self):
        """Exit Record Mode (3a): finalize any recording, cancel an armed
        delete (loop kept, left stopped), stop all loops (they stay in RAM)."""
        self.record_mode_active = False

        if self.loop_manager.is_recording:
            self.loop_manager.stop_recording()

        self._cancel_delete_arm(restore=False)

        for slot_idx in range(4):
            self._stop_loop_with_reset(slot_idx)

        # Normal-mode page/bank state was never touched (gotcha 9.3); just
        # restore the sliders' normal CC assignments and pickup tracking.
        self.update_slider_cc_assignments()

    def _reset_slot_click_state(self):
        for idx in range(4):
            self._slot_last_press_time[idx] = 0.0
            self._slot_pending_record[idx] = False
            self._slot_prev_play_state[idx] = False
            self._slot_ignore_press_until[idx] = 0.0

    # -------------------- Record Mode input processing --------------------

    def process_record_mode_inputs(self, swallowed):
        """
        Record-mode replacement for the normal gesture handling. All
        normal-mode gestures are inert here except set navigation (3c).
        """
        # Exit set-navigation mode when its initiating button is released
        # (mirrors page change mode)
        if self._rec_nav_active:
            if (self._rec_nav_exit_button_idx != -1
                    and not self.buttons[self._rec_nav_exit_button_idx].pressed):
                self._rec_nav_active = False
                self._rec_nav_exit_button_idx = -1

        if all(not button.pressed for button in self.buttons):
            self._rec_nav_active = False
            self._rec_nav_exit_button_idx = -1

        # While the all-four mode-toggle hold is in progress, slot actions are
        # inert but the faders keep sending (and recording)
        if all(button.pressed for button in self.buttons):
            self.send_record_mode_cc()
            return

        if self._handle_set_navigation(swallowed):
            return

        if not self._rec_nav_active:
            # In rapid-stepping navigation mode, clicks are navigation only
            self._process_slot_clicks(swallowed)
        self.send_record_mode_cc()

    def _handle_set_navigation(self, swallowed):
        """
        Step through the 5 CC sets with the page-change gesture (hold bottom +
        click top = next, hold top + click bottom = previous), with wrap.
        First step fires on release, subsequent steps on click while in
        navigation mode - mirroring the normal-mode page-change structure.
        Returns True if a navigation event was consumed.
        """
        top_button = self.buttons[3]
        bottom_button = self.buttons[0]
        middles_idle = not self.buttons[1].pressed and not self.buttons[2].pressed
        only_bottom_held = bottom_button.pressed and not top_button.pressed and middles_idle
        only_top_held = top_button.pressed and not bottom_button.pressed and middles_idle

        # Next set (bottom held, top activated)
        if bottom_button.hold_time > 0:
            if self._rec_nav_active and top_button.detected_new_press:
                self._cancel_slot_click(3)
                self._step_record_set(1)
                return True
            if (not self._rec_nav_active and top_button.detected_new_release
                    and not swallowed[3] and not top_button.was_long_held
                    and only_bottom_held):
                self._rec_nav_active = True
                self._rec_nav_exit_button_idx = 0
                self._suppress_release[0] = True  # held button's release fires nothing (rule b)
                self._cancel_slot_click(0)
                self._cancel_slot_click(3)
                self._step_record_set(1)
                return True

        # Previous set (top held, bottom activated)
        if top_button.hold_time > 0:
            if self._rec_nav_active and bottom_button.detected_new_press:
                self._cancel_slot_click(0)
                self._step_record_set(-1)
                return True
            if (not self._rec_nav_active and bottom_button.detected_new_release
                    and not swallowed[0] and not bottom_button.was_long_held
                    and only_top_held):
                self._rec_nav_active = True
                self._rec_nav_exit_button_idx = 3
                self._suppress_release[3] = True
                self._cancel_slot_click(0)
                self._cancel_slot_click(3)
                self._step_record_set(-1)
                return True

        return False

    def _cancel_slot_click(self, slot_idx):
        """Remove a button's pending click state (it was used by another gesture)."""
        self._slot_last_press_time[slot_idx] = 0.0
        self._slot_pending_record[slot_idx] = False

    def _step_record_set(self, direction):
        self._cancel_delete_arm(restore=True)
        self.record_cc_set_idx = (self.record_cc_set_idx + direction) % cfg.NUM_RECORD_CC_SETS
        self.update_record_slider_assignments()
        self._set_flash_set_idx = self.record_cc_set_idx
        self._set_flash_time = time.monotonic()

    def _record_set_lookup(self, slider_idx):
        """
        Resolve the active record CC set for one slider.
        Set 0 = global bank; sets 1-4 = page 1's banks (page index 0 lookups).

        Returns:
            (cc_number, channels, message_type, bank_idx) - bank_idx is -1 for global.
        """
        set_idx = self.record_cc_set_idx
        if set_idx == 0:
            return (cfg.GLOBAL_CC_BANK[slider_idx],
                    self.global_slider_channels[slider_idx],
                    self.global_message_type,
                    -1)
        bank_idx = set_idx - 1
        return (self.pages[0][bank_idx][slider_idx],
                self.channel_lookup[0][bank_idx][slider_idx],
                self.type_lookup[0][bank_idx],
                bank_idx)

    def update_record_slider_assignments(self):
        """
        Record-mode equivalent of update_slider_cc_assignments: assign each
        slider's CC from the active set and reset pickup tracking. Run on every
        set change, including Record Mode entry.
        """
        for idx, slider in enumerate(self.sliders):
            cc_number, channels, message_type, bank_idx = self._record_set_lookup(idx)
            slider.current_assigned_cc_number = cc_number
            slider.additional_assigned_cc_numbers = []

            if message_type == "AT":
                last_sent = midi_manager.get_last_at_value_per_slider(idx, 0, bank_idx)
            else:
                last_sent = midi_manager.get_last_cc_value_sent(cc_number, channels[0])
            slider.crossing_cc_value = last_sent

            if abs(slider.cc_value - last_sent) <= cfg.CC_THRESHOLD:
                slider.has_crossed_last_cc_value = True
            else:
                slider.has_crossed_last_cc_value = False
            slider.cc_value_changed = False

    # -------------------- Per-slot click state machine --------------------

    def _process_slot_clicks(self, swallowed):
        now = time.monotonic()
        for idx, button in enumerate(self.buttons):
            if button.detected_new_press:
                self._handle_slot_press(idx, now)
        for idx, button in enumerate(self.buttons):
            if button.detected_new_release:
                self._handle_slot_release(idx, button, swallowed[idx], now)

    def _handle_slot_press(self, slot_idx, now):
        # Presses within the double-press window after a stop-recording click
        # are ignored - otherwise a bouncy stop click would arm delete on the
        # brand-new loop (3b)
        if now < self._slot_ignore_press_until[slot_idx]:
            self._suppress_release[slot_idx] = True
            self._slot_last_press_time[slot_idx] = 0.0
            return

        # Confirm delete: an explicit press on the armed slot within the window
        if self._delete_armed_slot == slot_idx:
            self._confirm_delete(slot_idx)
            self._suppress_release[slot_idx] = True
            self._slot_last_press_time[slot_idx] = 0.0
            return

        # Any other slot's action cancels an armed delete (restores play
        # state); this press is then processed normally
        if self._delete_armed_slot != -1:
            self._cancel_delete_arm(restore=True)

        is_double = (self._slot_last_press_time[slot_idx] > 0
                     and (now - self._slot_last_press_time[slot_idx]) <= cfg.DOUBLE_PRESS_TIME)
        self._slot_last_press_time[slot_idx] = now

        if not is_double:
            # First press of a potential pair: capture the play state for a
            # possible delete-arm restore (before the first click toggles it)
            loop = self.loop_manager.loops[slot_idx]
            self._slot_prev_play_state[slot_idx] = bool(loop and loop.loop_is_playing)
            return

        # --- Double-press recognized (on the second press) ---
        state = self.loop_manager.get_slot_state(slot_idx)
        if state == SLOT_EMPTY:
            # Start recording fires on the second release
            self._slot_pending_record[slot_idx] = True
        elif state in (SLOT_PLAYING, SLOT_STOPPED):
            self._arm_delete(slot_idx, now)
            self._suppress_release[slot_idx] = True  # second release fires nothing

    def _handle_slot_release(self, slot_idx, button, was_swallowed, now):
        # Suppression rules (3b): (c) mode-toggle/navigation participants...
        if was_swallowed:
            self._slot_pending_record[slot_idx] = False
            self._slot_last_press_time[slot_idx] = 0.0
            return
        # ...and (a) long-held buttons
        if button.was_long_held:
            self._slot_pending_record[slot_idx] = False
            self._slot_last_press_time[slot_idx] = 0.0
            return

        if self._slot_pending_record[slot_idx]:
            self._slot_pending_record[slot_idx] = False
            # Switching from another recording slot finalizes that recording
            # first (inside LoopManager.start_recording)
            self.loop_manager.start_recording(slot_idx, self.record_cc_set_idx)
            # Ignore presses within the double-press window after starting a
            # recording (symmetric with stop-recording, 3b) - prevents a bouncy
            # third tap from immediately single-click stopping the new recording.
            self._slot_ignore_press_until[slot_idx] = now + cfg.DOUBLE_PRESS_TIME
            self._slot_last_press_time[slot_idx] = 0.0
            return

        # --- Single-click actions ---
        state = self.loop_manager.get_slot_state(slot_idx)
        if state == SLOT_RECORDING:
            self.loop_manager.stop_recording()
            self._slot_ignore_press_until[slot_idx] = now + cfg.DOUBLE_PRESS_TIME
            self._slot_last_press_time[slot_idx] = 0.0
        elif state == SLOT_PLAYING:
            self._stop_loop_with_reset(slot_idx)
        elif state == SLOT_STOPPED:
            self.loop_manager.toggle_playstate(slot_idx, True)
        # SLOT_EMPTY: no-op

    # -------------------- Delete arm / confirm / cancel --------------------

    def _arm_delete(self, slot_idx, now):
        self._delete_armed_slot = slot_idx
        self._delete_armed_time = now
        # Restore target is the play state from before the first click of the
        # pair (the first click's release already toggled it - accepted transient)
        self._delete_restore_play = self._slot_prev_play_state[slot_idx]

        loop = self.loop_manager.loops[slot_idx]
        if loop is not None and loop.loop_is_playing:
            self._stop_loop_with_reset(slot_idx)

    def _cancel_delete_arm(self, restore=True):
        if self._delete_armed_slot == -1:
            return
        slot_idx = self._delete_armed_slot
        self._delete_armed_slot = -1
        if restore and self._delete_restore_play and self.loop_manager.slot_has_loop(slot_idx):
            self.loop_manager.toggle_playstate(slot_idx, True)

    def _confirm_delete(self, slot_idx):
        self._delete_armed_slot = -1
        self.loop_manager.delete_loop(slot_idx)

    def _update_delete_arm_timeout(self, now):
        if (self._delete_armed_slot != -1
                and now - self._delete_armed_time > cfg.DELETE_CONFIRM_WINDOW_S):
            self._cancel_delete_arm(restore=True)

    # -------------------- Sending / recording / playback --------------------

    def send_record_mode_cc(self):
        """
        Record-mode fader output: same live send path as normal mode but with
        the active CC set's lookups, plus the recording tap (9.5) - events go
        both to MIDI out and into the recording loop, after the pickup check.
        """
        recording_loop = self.loop_manager.get_recording_loop()

        for slider_idx, slider in enumerate(self.sliders):
            if not slider.cc_value_changed:
                continue

            cc_number, channels, message_type, bank_idx = self._record_set_lookup(slider_idx)

            if not self.should_send_cc(slider, slider_idx, channels[0], message_type,
                                       bank_idx, page_idx=0):
                continue

            value = slider.cc_value
            if message_type == "AT":
                midi_manager.send_aftertouch(channels, value, slider_idx, 0, bank_idx)
                self._update_live_at_cache(channels, value)
                if recording_loop is not None:
                    for channel in channels:
                        recording_loop.add_aftertouch(value, channel)
            else:
                midi_manager.send_cc([(cc_number, ch) for ch in channels], value)
                self._update_live_cc_cache(cc_number, channels, value)
                if recording_loop is not None:
                    for channel in channels:
                        recording_loop.add_cc(cc_number, value, channel)

            slider.cc_value_changed = False

    def process_loop_playback(self):
        """
        Playback pump: collect due events from every slot and send them.
        Safe to call unconditionally - stopped/recording loops return None.
        Playback goes through midi_manager so its de-dupe and pickup state
        stay consistent with reality (gotcha 9.6).
        """
        for loop in self.loop_manager.loops:
            if loop is None:
                continue
            events = loop.get_new_events()
            if not events:
                continue
            new_cc, new_at = events
            for cc_number, value, channel in new_cc:
                midi_manager.send_cc([(cc_number, channel)], value)
            for _, pressure, channel in new_at:
                midi_manager.send_aftertouch([channel], pressure)

    def _stop_loop_with_reset(self, slot_idx):
        """Stop a slot's loop; if cc_reset is enabled, re-send the last live
        fader values for exactly the (CC, channel) pairs the loop recorded (3e)."""
        loop = self.loop_manager.loops[slot_idx]
        if loop is None:
            return
        was_playing = loop.loop_is_playing and not loop.is_recording
        self.loop_manager.toggle_playstate(slot_idx, False)
        if was_playing and settings.get_cc_reset():
            self._send_cc_reset(loop)

    def _send_cc_reset(self, loop):
        for (cc_number, channel) in loop._last_cc_values:
            live_value = self._last_live_cc_values.get((cc_number, channel))
            if live_value is not None:
                midi_manager.send_cc([(cc_number, channel)], live_value)
        for channel in loop._last_at_values:
            live_pressure = self._last_live_at_values.get(channel)
            if live_pressure is not None:
                midi_manager.send_aftertouch([channel], live_pressure)

    # -------------------- Lights interface --------------------

    def get_record_slot_states(self):
        """
        Per-slot display state for the LightsManager (3d).

        Returns:
            list of (state, color) for slots 0-3. color is only meaningful for
            "stopped" (the bank color of the set active at record start).
        """
        states = []
        for slot_idx in range(4):
            if slot_idx == self._delete_armed_slot:
                states.append(("delete_armed", None))
                continue
            state = self.loop_manager.get_slot_state(slot_idx)
            color = None
            if state == SLOT_STOPPED:
                set_idx = self.loop_manager.loops[slot_idx].cc_set_idx
                if set_idx == 0:
                    color = cfg.GLOBAL_BANK_COLOR
                else:
                    color = cfg.PAGE_COLORS[0][set_idx - 1]
            states.append((state, color))
        return states

    def get_set_flash(self):
        """CC-set switch flash for the lights (3d polish): the set index to
        flash, or -1 when no flash is active."""
        if self._set_flash_set_idx == -1:
            return -1
        if time.monotonic() - self._set_flash_time > cfg.RECORD_SET_FLASH_S:
            self._set_flash_set_idx = -1
            return -1
        return self._set_flash_set_idx

    @property
    def record_display_bank_idx(self):
        """Active record set mapped to a bank index for the slider lights
        (page 0); -1 = global."""
        return self.record_cc_set_idx - 1