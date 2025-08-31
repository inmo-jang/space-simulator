import socket
import threading
from typing import Optional

class MonaClient:
    """
    Very small TCP client for Mona(ESP32) firmware that expects single-letter commands.
    Usage:
        mc = MonaClient(host, port)
        mc.connect()
        mc.send("F")   # forward (per your Arduino example)
        mc.close()
    """
    def __init__(self, host: str, port: int, timeout: float = 2.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sock: Optional[socket.socket] = None
        self._rx_thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    @property
    def is_connected(self) -> bool:
        return self._sock is not None

    def connect(self) -> bool:
        if self._sock:
            return True
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(self.timeout)
            s.connect((self.host, self.port))
            s.settimeout(None)  # blocking for normal ops
            self._sock = s
            # Optional RX thread (firmware가 에코/로그를 보낼 경우 대비)
            self._stop.clear()
            self._rx_thread = threading.Thread(target=self._rx_loop, daemon=True)
            self._rx_thread.start()
            return True
        except Exception as e:
            print(f"[MonaClient] connect failed: {e}")
            self._sock = None
            return False

    def _rx_loop(self):
        try:
            while not self._stop.is_set() and self._sock:
                try:
                    data = self._sock.recv(1024)
                    if not data:  # peer closed
                        break
                    print(f"[MonaClient] RX: {data!r}")
                except OSError:
                    break
        finally:
            self._cleanup()

    def send(self, payload: str) -> bool:
        if not self._sock:
            print("[MonaClient] not connected")
            return False
        try:
            # 단문자 ASCII (F,B,L,R,S 등) 그대로 보냄
            self._sock.sendall(payload.encode('utf-8'))
            return True
        except Exception as e:
            print(f"[MonaClient] send failed: {e}")
            self.close()
            return False

    def close(self):
        self._stop.set()
        self._cleanup()

    def _cleanup(self):
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
        self._sock = None