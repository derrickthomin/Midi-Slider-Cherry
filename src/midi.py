import adafruit_midi
from adafruit_midi.control_change import ControlChange
from adafruit_midi.channel_pressure import ChannelPressure
import busio
import board
import usb_midi

# TRS A 
MIDI_AUX_TX_PIN = board.GP16
MIDI_AUX_RX_PIN = board.GP17

class MidiManager:
    """
    Manages sending and tracking MIDI CC and Aftertouch messages over both USB and TRS MIDI.
    """

    def __init__(self):
        # Track last CC values by (cc_number, channel) tuple
        # This allows different channels to track independently
        self.last_cc_values_sent = {}
        
        # Track last aftertouch values by channel only
        # (Channel Aftertouch is one value per channel, no CC number)
        self.last_aftertouch_values_sent = {}
        
        # Track last aftertouch values per slider for LED/pickup purposes
        # Key: (slider_idx, page_idx, bank_idx), Value: pressure value
        # This allows independent pickup behavior even though AT is per-channel
        self.last_at_values_per_slider = {}

        # Set up the UART and MIDI interfaces
        uart = busio.UART(
            MIDI_AUX_TX_PIN,
            MIDI_AUX_RX_PIN,
            baudrate=31250,
            timeout=0.001
        )
        # Note: out_channel here is just a default; we override per-message
        # USB MIDI: ports[0] is input, ports[1] is output
        self.midi = adafruit_midi.MIDI(
            midi_in=usb_midi.ports[0],
            midi_out=usb_midi.ports[1],
            in_channel=0,
            out_channel=0
        )
        self.trs_midi = adafruit_midi.MIDI(
            midi_in=uart,
            midi_out=uart,
            in_channel=0,
            out_channel=0,
            debug=False,
        )

    def receive_cc(self):
        """
        Check for incoming CC messages from both USB and TRS MIDI.
        
        Returns:
            tuple: (cc_number, channel) if CC received, None otherwise.
            Channel is 1-indexed (1-16) for user display.
        """
        # Check USB MIDI
        msg = self.midi.receive()
        if msg is not None and isinstance(msg, ControlChange):
            return (msg.control, msg.channel + 1)  # Return 1-indexed channel
        
        # Check TRS MIDI
        msg = self.trs_midi.receive()
        if msg is not None and isinstance(msg, ControlChange):
            return (msg.control, msg.channel + 1)  # Return 1-indexed channel
        
        return None

    def receive_cc_or_at(self):
        """
        Check for incoming CC or Channel Aftertouch messages from both USB and TRS MIDI.
        
        Returns:
            tuple: ("CC", cc_number, channel) or ("AT", value, channel) if received, None otherwise.
            Channel is 1-indexed (1-16) for user display.
        """
        # Check USB MIDI
        msg = self.midi.receive()
        if msg is not None:
            if isinstance(msg, ControlChange):
                return ("CC", msg.control, msg.channel + 1)
            if isinstance(msg, ChannelPressure):
                return ("AT", msg.pressure, msg.channel + 1)
        
        # Check TRS MIDI
        msg = self.trs_midi.receive()
        if msg is not None:
            if isinstance(msg, ControlChange):
                return ("CC", msg.control, msg.channel + 1)
            if isinstance(msg, ChannelPressure):
                return ("AT", msg.pressure, msg.channel + 1)
        
        return None
    
    def flush_receive_buffer(self):
        """
        Drain any pending messages from both USB and TRS MIDI input buffers.
        Call this before starting learn mode to avoid reading stale messages.
        """
        # Drain USB MIDI buffer
        while self.midi.receive() is not None:
            pass
        
        # Drain TRS MIDI buffer    
        while self.trs_midi.receive() is not None:
            pass

    def has_cc_value_changed(self, cc_number, channel, cc_value):
        """
        Checks whether the given CC number's value differs from the last value sent
        on the specified channel.
        
        Args:
            cc_number (int): The CC number (0-127)
            channel (int): The MIDI channel (0-indexed, 0-15)
            cc_value (int): The CC value to check
            
        Returns:
            bool: True if value changed or never sent, False otherwise
        """
        key = (cc_number, channel)
        return self.last_cc_values_sent.get(key, -1) != cc_value

    def send_cc(self, cc_list_with_channels, cc_value):
        """
        Sends Control Change messages for all given CC numbers with their channels,
        but only if their values changed.
        
        Args:
            cc_list_with_channels: List of (cc_number, channel) tuples
            cc_value (int): The CC value to send (0-127)
        """
        for cc_number, channel in cc_list_with_channels:
            if self.has_cc_value_changed(cc_number, channel, cc_value):
                key = (cc_number, channel)
                self.last_cc_values_sent[key] = cc_value
                cc_msg = ControlChange(cc_number, cc_value, channel=channel)
                # Send each message individually to preserve its channel
                # (MIDI.send() overwrites channel when sending lists)
                self.midi.send(cc_msg, channel=channel)
                self.trs_midi.send(cc_msg, channel=channel)

    def get_last_cc_value_sent(self, cc_number, channel):
        """
        Retrieves the last CC value sent for a specified CC number and channel.

        Args:
            cc_number (int): CC number to look up.
            channel (int): MIDI channel (0-indexed, 0-15)

        Returns:
            int: The last CC value sent for that CC number/channel, or 16 if never sent.
        """
        key = (cc_number, channel)
        return self.last_cc_values_sent.get(key, 16)
    
    # ==================== Aftertouch Methods ====================
    
    def has_aftertouch_value_changed(self, channel, pressure):
        """
        Checks whether the given aftertouch value differs from the last value sent
        on the specified channel.
        
        Args:
            channel (int): The MIDI channel (0-indexed, 0-15)
            pressure (int): The aftertouch pressure value to check (0-127)
            
        Returns:
            bool: True if value changed or never sent, False otherwise
        """
        return self.last_aftertouch_values_sent.get(channel, -1) != pressure
    
    def send_aftertouch(self, channels, pressure, slider_idx=0, page_idx=0, bank_idx=0):
        """
        Sends Channel Aftertouch (Channel Pressure) messages for all given channels,
        but only if their values changed.
        
        Note: Channel Aftertouch is a single pressure value per channel.
        Multiple sliders on the same channel will share the same aftertouch value.
        Per-slider tracking is maintained separately for LED/pickup behavior.
        
        Args:
            channels: List of channels (0-indexed) to send to
            pressure (int): The pressure value to send (0-127)
            slider_idx (int): Index of the slider (0-3) for per-slider tracking
            page_idx (int): Page index (0-3) for per-slider tracking
            bank_idx (int): Bank index (0-3) for per-slider tracking
        """
        # Track per-slider for LED/pickup purposes
        slider_key = (slider_idx, page_idx, bank_idx)
        self.last_at_values_per_slider[slider_key] = pressure
        
        for channel in channels:
            if self.has_aftertouch_value_changed(channel, pressure):
                self.last_aftertouch_values_sent[channel] = pressure
                at_msg = ChannelPressure(pressure, channel=channel)
                self.midi.send(at_msg, channel=channel)
                self.trs_midi.send(at_msg, channel=channel)
    
    def get_last_aftertouch_value_sent(self, channel):
        """
        Retrieves the last aftertouch value sent for a specified channel.

        Args:
            channel (int): MIDI channel (0-indexed, 0-15)

        Returns:
            int: The last aftertouch value sent for that channel, or 16 if never sent.
        """
        return self.last_aftertouch_values_sent.get(channel, 16)
    
    def get_last_at_value_per_slider(self, slider_idx, page_idx, bank_idx):
        """
        Retrieves the last aftertouch value sent for a specific slider/page/bank combo.
        Used for LED display and pickup mode behavior.

        Args:
            slider_idx (int): Slider index (0-3)
            page_idx (int): Page index (0-3)
            bank_idx (int): Bank index within the page (0-3), or -1 for global

        Returns:
            int: The last AT value sent for that slider/page/bank, or 16 if never sent.
        """
        key = (slider_idx, page_idx, bank_idx)
        return self.last_at_values_per_slider.get(key, 16)

# Instantiate the global MidiManager
midi_manager = MidiManager()
