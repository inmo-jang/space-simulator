import socket
import threading
import time
import math
from typing import Optional, Tuple

class MonaClient:
    """
    TCP client for MONA (ESP32). Adds ACK-based gating so that a new G command
    is only sent after the previous one has completed (or was cancelled).
    """
    
    def __init__(
        self,
        host: str,
        port: int,
        timeout: float = 2.0,
        px_to_mm: float = 1.0,
        deadband_mm: float = 0.0,
        reconnect_interval_sec: float = 2.0,
        g_interval_sec: float = 0.0,
        arrive_threshold_mm: float = 0.0,
        distance_scale: float = 1.0,   # optional global scale (e.g., 0.95)
    ):
        # connection
        self.host = host
        self.port = int(port)
        self.timeout = float(timeout)
        self._sock: Optional[socket.socket] = None
        self._rx_thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

        # motion / gating
        self.px_to_mm = float(px_to_mm)
        self.distance_scale = float(distance_scale)
        self.deadband_mm = float(deadband_mm)
        self.arrive_threshold_mm = float(arrive_threshold_mm)

        # interval (optional; default disable and rely on ACK)
        self._g_interval = float(g_interval_sec)
        self._last_g_ts = 0.0

        # reconnect
        self._last_attempt_ts = 0.0
        self._reconnect_interval = float(reconnect_interval_sec)

        # state
        self._busy = False                 # True after send_g(), False on "OK G" or "INFO: Avoidance complete"
        self._last_click_target: Optional[Tuple[float, float]] = None

        # rx buffer
        self._rx_buf = bytearray()

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
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(self.timeout)
            s.connect((self.host, self.port))
            s.settimeout(None)
            self._sock = s
            self._stop.clear()
            self._rx_thread = threading.Thread(target=self._rx_loop, daemon=True)
            self._rx_thread.start()
            print(f"[MonaClient] connected to {self.host}:{self.port}")
            return True
        except Exception as e:
            print(f"[MonaClient] connect failed: {e}")
            self._sock = None
            return False

    def close(self):
        self._stop.set()
        try:
            if self._sock:
                try:
                    self._sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                self._sock.close()
        finally:
            self._sock = None
            self._rx_thread = None

    def _cleanup(self):
        try:
            if self._sock:
                self._sock.close()
        finally:
            self._sock = None

    # ---------- RX loop: parse ACK/INFO to drop busy ----------
    def _rx_loop(self):
        try:
            while not self._stop.is_set() and self._sock:
                try:
                    data = self._sock.recv(1024)
                    if not data:
                        break
                    self._rx_buf.extend(data)
                    while True:
                        if b'\n' not in self._rx_buf:
                            break
                        line, _, rest = self._rx_buf.partition(b'\n')
                        self._rx_buf = bytearray(rest)
                        try:
                            txt = line.decode('utf-8', errors='ignore').strip()
                        except Exception:
                            txt = ""
                        if not txt:
                            continue
                        print(f"[MONA<-] {txt}")
                        # ACK gating
                        up = txt.upper()
                        if up.startswith("OK G"):
                            self._busy = False
                        elif "AVOIDANCE COMPLETE" in up or "READY FOR NEW COMMAND" in up:
                            self._busy = False
                        elif up.startswith("ERR"):
                            # treat errors as completion
                            self._busy = False
                except OSError:
                    break
        finally:
            self._cleanup()

    # ---------- helpers ----------
    def compute_g(self, curr_xy: Tuple[float, float], curr_heading_rad: float, target_xy: Tuple[float, float]) -> Tuple[float, float]:
        cx, cy = float(curr_xy[0]), float(curr_xy[1])
        tx, ty = float(target_xy[0]), float(target_xy[1])
        dx, dy = (tx - cx), (ty - cy)
        dist_px = math.hypot(dx, dy)
        dist_mm = dist_px * self.px_to_mm 
        if self.distance_scale != 1.0:
            dist_mm *= self.distance_scale  # e.g., 0.95
        # desired heading (rad)
        desired = math.atan2(dy, dx)
        dtheta = desired - curr_heading_rad
        # normalize to [-pi, pi]
        while dtheta > math.pi:
            dtheta -= 2*math.pi
        while dtheta < -math.pi:
            dtheta += 2*math.pi
        deg = math.degrees(dtheta)
        return (deg, dist_mm)

    def _send_raw(self, payload: str) -> bool:
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

    # ---------- Public API ----------
    def send_g(self, delta_deg: float, dist_mm: float) -> bool:
        # deadband: ignore tiny corrections near target
        if dist_mm <= (self.deadband_mm):  # 5mm 마진
            return False

        now = time.monotonic()
        # interval gate (optional)
        if self._g_interval > 0.0 and (now - self._last_g_ts) < self._g_interval:
            return False

        if self._busy:
            # do not interrupt ongoing motion; keep only the latest
            # self._queued = (float(delta_deg), float(dist_mm))
            return False

        payload = f"G {delta_deg:.3f} {dist_mm:.1f}\n"
        ok = self._send_raw(payload)
        if ok:
            print(f"[MONA->] {payload.strip()}")
            self._last_g_ts = now
            self._busy = True
        return ok

    def try_flush_queue(self):
        '''
        if self._queued is None:
            return
        if self._busy:
            return
        now = time.monotonic()
        if self._g_interval > 0.0 and (now - self._last_g_ts) < self._g_interval:
            return
        deg, mm = self._queued
        self._queued = None
        self.send_g(deg, mm)
        '''
        return False
        

    def send_g_to(self, curr_xy: Tuple[float, float], curr_heading_rad: float, target_xy: Tuple[float, float]) -> bool:
        deg, mm = self.compute_g(curr_xy, curr_heading_rad, target_xy)
        return self.send_g(deg, mm)

    def remember_click_target(self, target_xy: Tuple[float, float]):
        self._last_click_target = (float(target_xy[0]), float(target_xy[1]))

    def step_periodic_g(self, curr_xy: Tuple[float, float], curr_heading_rad: float):
        """
        If g_interval_sec > 0, re-send queued G (to last click target) when allowed.
        """
        self.try_flush_queue()
        
    def cancel_all(self, send_stop: bool = True):
        """Drop any queued G and mark as not busy. Optionally send STOP to MONA."""
        self._busy = False
        if send_stop:
            try:
                self._send_raw("STOP\n")
            except Exception:
                pass

    # -------------- factory from config --------------
    @classmethod
    def from_config(cls, a, b=None):
        """
        Flexible signature:
          - from_config(agent_id: int, mona_cfg: dict)
          - from_config(cfg_root: dict, agent_id: int = 0)
            (cfg_root may be the whole YAML dict OR the 'mona' sub-dict)
        """
        # 1) 인자 해석
        if isinstance(a, int):                 # (agent_id, mona_cfg)
            agent_id = int(a)
            mona_cfg = dict(b or {})
        elif isinstance(a, dict):              # (cfg_root[, agent_id])
            agent_id = int(b or 0)
            # a가 전체 YAML일 수도, 'mona' 서브딕셔너리일 수도 있음
            mona_cfg = a.get('mona', a) or {}
        else:
            raise TypeError("from_config expects (int, dict) or (dict[, int])")

        # 2) 로봇 엔트리 선택
        robots_cfg = mona_cfg.get('robots') or []
        my = None
        for r in robots_cfg:
            try:
                if int(r.get('agent_id')) == agent_id:
                    my = r; break
            except Exception:
                pass
        if my is None and robots_cfg and agent_id < len(robots_cfg):
            my = robots_cfg[agent_id]

        # 3) 파라미터 추출 + 인스턴스 생성
        host = (my or mona_cfg).get('host', '127.0.0.1')
        port = int((my or mona_cfg).get('port', 8080))
        return cls(
            host, port,
            timeout=float(mona_cfg.get('timeout_sec', 2.0)),
            px_to_mm=float(mona_cfg.get('px_to_mm', 1.0)),
            deadband_mm=float(mona_cfg.get('deadband_mm', 0.0)),
            reconnect_interval_sec=float(mona_cfg.get('reconnect_interval_sec', 2.0)),
            g_interval_sec=float(mona_cfg.get('g_interval_sec', 0.0)),
            arrive_threshold_mm=float(mona_cfg.get('arrive_threshold_mm', 0.0)),
            distance_scale=float(mona_cfg.get('distance_scale', 1.0)),
        )

