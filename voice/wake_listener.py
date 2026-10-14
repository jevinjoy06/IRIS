"""UART wake listener — receives single byte from FPGA when wake word detected."""
import threading
import time

try:
    import serial
except ImportError:
    print(
        "[uart_wake] pyserial not installed. Install with: pip install pyserial>=3.5"
    )
    serial = None


class UARTWakeListener:
    """Listen for wake trigger byte from FPGA over UART."""

    def __init__(self, port: str, baud: int = 115200, wake_byte: int = 0x57):
        """Initialize UART listener.

        Args:
            port: Serial port (e.g., COM3 on Windows, /dev/ttyUSB0 on Linux)
            baud: Baud rate (default 115200)
            wake_byte: Byte value that triggers wake (default 0x57 = 'W')
        """
        self.port = port
        self.baud = baud
        self.wake_byte = wake_byte
        self._thread = None
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._ser = None

    def start(self) -> None:
        """Start background listener thread."""
        self._stop_event.clear()
        self._wake_event.clear()
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop listener thread and close serial port."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        if self._ser and self._ser.is_open:
            self._ser.close()

    def triggered(self) -> bool:
        """Check if wake event was triggered; clear flag if so."""
        if self._wake_event.is_set():
            self._wake_event.clear()
            return True
        return False

    def _listen_loop(self) -> None:
        """Background thread: read bytes from UART, set event on wake_byte."""
        while not self._stop_event.is_set():
            try:
                if self._ser is None or not self._ser.is_open:
                    if serial is None:
                        print(
                            "[uart_wake] pyserial not available, cannot open port"
                        )
                        time.sleep(2.0)
                        continue

                    self._ser = serial.Serial(self.port, self.baud, timeout=1.0)
                    print(
                        f"[uart_wake] opened {self.port} at {self.baud} baud"
                    )

                # Read one byte
                byte_data = self._ser.read(1)
                if byte_data and len(byte_data) > 0:
                    byte_val = byte_data[0]
                    if byte_val == self.wake_byte:
                        print("[uart_wake] trigger received")
                        self._wake_event.set()

            except (OSError, Exception) as e:
                # Port not found, disconnected, or other read error
                print(f"[uart_wake] error: {e}")
                if self._ser and self._ser.is_open:
                    self._ser.close()
                    self._ser = None
                # Retry after 2s
                time.sleep(2.0)
