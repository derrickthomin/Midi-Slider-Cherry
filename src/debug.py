import time
import adafruit_ticks as ticks
import digitalio
from collections import OrderedDict
import constants
from utils import free_memory
DEBUG_INTERVAL_S = 1.5  # Interval to print debug info (seconds)

DEBUG = True # Set to True to enable debug mode

class PerformanceTimer:
    """
    Memory-efficient performance timer for constrained environments.

    This implementation avoids dynamic memory allocation by using preallocated
    fixed-size arrays for storing labels and statistics. All statistics reset
    after each printout.
    """

    def __init__(self, max_labels=10):
        """
        Initialize the performance timer with a fixed number of labels.

        :param max_labels: Maximum number of unique sections (labels) to track.
        """
        self.max_labels = max_labels
        
        # Preallocate fixed-size structures
        self.labels = [None] * max_labels  # Label names
        self.start_times = [0] * max_labels  # Start times for active labels
        self.total_times = [0] * max_labels  # Accumulated total times
        self.call_counts = [0] * max_labels  # Number of calls for each label
        self.max_times = [0] * max_labels   # Maximum elapsed time for each label
        self.min_times = [float("inf")] * max_labels  # Minimum elapsed time for each label
        
        self._last_print_time = ticks.ticks_ms()  # Last time the statistics were printed

    def _get_label_index(self, label):
        """
        Find the index of the given label or allocate a new one.

        :param label: The name of the section/label.
        :return: Index of the label in preallocated arrays.
        :raises MemoryError: If the maximum number of labels is exceeded.
        """
        # Check if the label already exists
        for i in range(self.max_labels):
            if self.labels[i] == label:
                return i
        
        # Find the first free slot to allocate this label
        for i in range(self.max_labels):
            if self.labels[i] is None:
                self.labels[i] = label
                return i
        
        # If we reach here, we've exceeded the maximum number of labels
        raise MemoryError("Exceeded the maximum number of performance timer labels")

    def start(self, label):
        """
        Start timing the section identified by 'label'.
        """
        try:
            index = self._get_label_index(label)
            self.start_times[index] = ticks.ticks_ms()
        except MemoryError as e:
            print(f"[PerformanceTimer] {e}")

    def stop(self, label):
        """
        Stop timing the section identified by 'label' and update statistics.
        """
        try:
            index = self._get_label_index(label)
            start_time = self.start_times[index]
            if start_time == 0:
                print(f"[PerformanceTimer] Warning: stop() called for label '{label}' without matching start()")
                return

            # Calculate elapsed time
            end_time = ticks.ticks_ms()
            elapsed = ticks.ticks_diff(end_time, start_time)
            self.start_times[index] = 0  # Reset the start time

            # Update statistics for the label
            self.total_times[index] += elapsed
            self.call_counts[index] += 1
            self.max_times[index] = max(self.max_times[index], elapsed)
            self.min_times[index] = min(self.min_times[index], elapsed)

        except MemoryError as e:
            print(f"[PerformanceTimer] {e}")

    def print_data(self):
        """
        Print the accumulated performance data for all tracked sections.
        Resets all statistics after printing.
        """
        header = f"{'Section':<35} {'Calls':>10} {'Total (ms)':>12} {'Avg (ms)':>12} {'Max (ms)':>12} {'Min (ms)':>12}"
        separator = "-" * len(header)
        print("\n=== Performance Timer Data ===")
        print(header)
        print(separator)

        for i in range(self.max_labels):
            if self.labels[i] is not None and self.call_counts[i] > 0:
                # Calculate and display statistics for each label
                total = self.total_times[i]
                count = self.call_counts[i]
                avg = total / count if count > 0 else 0
                max_time = self.max_times[i]
                min_time = self.min_times[i] if self.min_times[i] != float("inf") else 0
                print(f"{self.labels[i]:<35} {count:>10} {total:>12} {avg:>12.2f} {max_time:>12} {min_time:>12}")

        print(separator)

        # Reset all statistics after printing
        self._reset_statistics()

    def _reset_statistics(self):
        """
        Reset all recorded statistics for the timer.
        This clears totals, counts, and min/max times while keeping labels intact.
        """
        for i in range(self.max_labels):
            self.start_times[i] = 0
            self.total_times[i] = 0
            self.call_counts[i] = 0
            self.max_times[i] = 0
            self.min_times[i] = float("inf")

    def update(self):
        """
        Print performance statistics at regular intervals (default: every second).
        Automatically resets statistics after each printout.
        """
        now = ticks.ticks_ms()
        if ticks.ticks_diff(now, self._last_print_time) >= 1000:
            self.print_data()
            self._last_print_time = now

# Create an instance of the Debug class for debugging
performance_timer = PerformanceTimer()


