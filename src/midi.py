import adafruit_midi
from adafruit_midi.control_change import ControlChange
import busio
import board
import usb_midi

# TRS A 
MIDI_AUX_TX_PIN = board.GP16
MIDI_AUX_RX_PIN = board.GP17

class MidiManager:
    """
    Manages sending and tracking MIDI CC messages over both USB and TRS MIDI.
    """

    def __init__(self):
        # Track last CC values by (cc_number, channel) tuple
        # This allows different channels to track independently
        self.last_cc_values_sent = {}

        # Set up the UART and MIDI interfaces
        uart = busio.UART(
            MIDI_AUX_TX_PIN,
            MIDI_AUX_RX_PIN,
            baudrate=31250,
            timeout=0.001
        )
        # Note: out_channel here is just a default; we override per-message
        self.midi = adafruit_midi.MIDI(midi_out=usb_midi.ports[1], out_channel=0)
        self.trs_midi = adafruit_midi.MIDI(
            midi_in=uart,
            midi_out=uart,
            in_channel=0,
            out_channel=0,
            debug=False,
        )

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

# Instantiate the global MidiManager
midi_manager = MidiManager()
