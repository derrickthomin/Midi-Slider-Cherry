import adafruit_midi
from adafruit_midi.control_change import ControlChange
import busio
import board
import usb_midi

MIDI_AUX_TX_PIN = board.GP16
MIDI_AUX_RX_PIN = board.GP17

class MidiManager:
    """
    Manages sending and tracking MIDI CC messages over both USB and TRS MIDI.
    """

    def __init__(self):
        # Initialize last known CC values to something other than 0
        self.last_cc_values_sent = [16] * 128

        # Set up the UART and MIDI interfaces
        uart = busio.UART(
            MIDI_AUX_TX_PIN,
            MIDI_AUX_RX_PIN,
            baudrate=31250,
            timeout=0.001
        )
        self.midi = adafruit_midi.MIDI(midi_out=usb_midi.ports[1], out_channel=1)
        self.trs_midi = adafruit_midi.MIDI(
            midi_in=uart,
            midi_out=uart,
            in_channel=1,
            out_channel=1,
            debug=False,
        )

    def has_cc_value_changed(self, cc_number, cc_value):
        """
        Checks whether the given CC number's value differs from the last value sent.
        """
        return cc_value != self.last_cc_values_sent[cc_number]

    def send_cc(self, cc_list, cc_value):
        """
        Sends Control Change messages for all given CC numbers, but only if their values changed.
        """
        cc_objects = []
        for cc_number in cc_list:
            if self.has_cc_value_changed(cc_number, cc_value):
                self.last_cc_values_sent[cc_number] = cc_value
                print(f"Sending CC {cc_number} with value {cc_value}")
                cc_objects.append(ControlChange(cc_number, cc_value))

        if cc_objects:
            self.midi.send(cc_objects)
            self.trs_midi.send(cc_objects)

    def get_last_cc_value_sent(self, cc_number):
        """
        Retrieves the last CC value sent for a specified CC number.

        Args:
            cc_number (int): CC number to look up.

        Returns:
            int: The last CC value sent for that CC number.
        """
        return self.last_cc_values_sent[cc_number]

# Instantiate the global MidiManager
midi_manager = MidiManager()
