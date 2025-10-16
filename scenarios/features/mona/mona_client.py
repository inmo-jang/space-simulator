import socket
import threading
import time
import math
from typing import Optional, Tuple

class MonaClient:
    """
    Very small TCP client for Mona(ESP32) firmware that expects single-letter commands.
    Usage:
        mc = MonaClient(host, port)
        mc.connect()
        mc.send("F")   # forward (per your Arduino example)
        mc.close()
    """
    def __init__(
        self, 
        host: str, 
        port: int, 
        timeout: float = 2.0,
        px_to_mm: float = 1.0,
        deadband_deg: float = 1.0,
        deadband_mm: float = 5.0,
        reconnect_interval_sec: float = 2.0,
        g_interval_sec: float = 0.0,
    ):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sock: Optional[socket.socket] = None
        self._rx_thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        
        # motion params
        self.px_to_mm = float(px_to_mm)
        self.deadband_deg = float(deadband_deg)
        self.deadband_mm = float(deadband_mm)

        # connection mgmt
        self._last_attempt_ts: float = 0.0
        self._reconnect_interval = float(reconnect_interval_sec)

        # optional periodic G
        self._g_interval = float(g_interval_sec)
        self._last_g_ts: float = 0.0
        self._last_click_target: Optional[Tuple[float, float]] = None

    @property
    def is_connected(self) -> bool:
        return self._sock is not None
        
    def ensure_connected(self) -> bool:
        if self._sock:
            return True
        now = time.monotonic()
        if now - self._last_attempt_ts < self._reconnect_interval:
            return False
        self._last_attempt_ts = now
        return self.connect()

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
            
    '''
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
    '''
    
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
    
    @staticmethod
    def _wrap_pi(a: float) -> float:
        while a <= -math.pi:
            a += 2 * math.pi
        while a > math.pi:
            a -= 2 * math.pi
        return a

    def calculate_turn_and_distance(self, curr_xy: Tuple[float, float], curr_heading_rad: float, target_xy: Tuple[float, float]) -> Tuple[float, float]:
        """
        Returns (delta_deg, dist_mm) for the simulator's screen coordinate system.
        """
        cx, cy = float(curr_xy[0]), float(curr_xy[1])
        tx, ty = float(target_xy[0]), float(target_xy[1])

        dx = tx - cx
        dy = ty - cy
        desired_heading = math.atan2(dy, dx)  # rad, cw+
        delta_rad = MonaClient._wrap_pi(desired_heading - float(curr_heading_rad))
        delta_deg = math.degrees(delta_rad)
        dist_px = math.hypot(dx, dy)
        dist_mm = dist_px * self.px_to_mm
        return (delta_deg, dist_mm)

    def send(self, payload: str) -> bool:
        if not self._sock:
            print("[MonaClient] not connected")
            return False
        try:
            self._sock.sendall(payload.encode('utf-8'))
            return True
        except Exception as e:
            print(f"[MonaClient] send failed: {e}")
            self.close()
            return False

    def send_g(self, delta_deg: float, dist_mm: float) -> bool:
        # deadband
        if abs(delta_deg) < self.deadband_deg and dist_mm < self.deadband_mm:
            return False
        payload = f"G {delta_deg:.3f} {dist_mm:.1f}\n"
        ok = self.send(payload)
        if ok:
            print(f"[MONA] G sent: {payload.strip()}")
            self._last_g_ts = time.monotonic()
        return ok

    def send_g_to(
        self,
        curr_xy: Tuple[float, float],
        curr_heading_rad: float,
        target_xy: Tuple[float, float],
    ) -> bool:
        deg, mm = self.calculate_turn_and_distance(curr_xy, curr_heading_rad, target_xy)
        return self.send_g(deg, mm)

    def remember_click_target(self, target_xy: Tuple[float, float]):
        self._last_click_target = (float(target_xy[0]), float(target_xy[1]))

    def step_periodic_g(
        self,
        curr_xy: Tuple[float, float],
        curr_heading_rad: float,
    ):
        if self._g_interval <= 0.0 or self._last_click_target is None:
            return
        now = time.monotonic()
        if now - self._last_g_ts < self._g_interval:
            return
        deg, mm = self.calculate_turn_and_distance(curr_xy, curr_heading_rad, self._last_click_target)
        self.send_g(deg, mm)
    
    @classmethod
    def from_config(cls, agent_id: int, mona_cfg: dict):
        robots_cfg = mona_cfg.get('robots') or []
        my = None
        for r in robots_cfg:
            try:
                if int(r.get('agent_id')) == int(agent_id):
                    my = r
                    break
            except Exception:
                pass
        if my is None and robots_cfg and len(robots_cfg) > agent_id:
            my = robots_cfg[agent_id]
        host = (my or mona_cfg).get('host', '127.0.0.1')
        port = int((my or mona_cfg).get('port', 8080))
        return cls(
            host, port,
            timeout=float(mona_cfg.get('timeout_sec', 2.0)),
            px_to_mm=float(mona_cfg.get('px_to_mm', 1.0)),
            deadband_deg=float(mona_cfg.get('deadband_deg', 1.0)),
            deadband_mm=float(mona_cfg.get('deadband_mm', 5.0)),
            reconnect_interval_sec=float(mona_cfg.get('reconnect_interval_sec', 2.0)),
            g_interval_sec=float(mona_cfg.get('g_interval_sec', 0.0)),
        )
