"""
MONA Communication Controller.

TCP bridge between Space-simulator and MONA (ESP32) robots.
Handles bidirectional JSON message exchange over TCP sockets.

Protocol:
- Send: UTF-8 JSON + '\\n' (single line)
- Receive: UTF-8 JSON + '\\n' (monitor JSON with self_message + received_messages)
"""

import json
import socket
import time
import errno
import select
from typing import Dict, Tuple, Optional
from threading import Thread, Lock

NEWLINE = b"\n"
RECV_BUFFER_SIZE = 4096
SOCKET_TIMEOUT = 2.0


class MonaComm:
    """
    Communication manager for MONA robot network.
    
    Manages TCP connections to multiple MONA robots and provides
    message send/receive capabilities with automatic reconnection.
    """
    
    def __init__(self, mona_cfg: Dict):
        """
        Initialize MONA communication manager.
        
        Args:
            mona_cfg: Configuration dict with keys:
                - enabled: bool
                - robots: list of {agent_id, host, port}
                - debug_api: optional debug server config
        """
        self.enabled = bool(mona_cfg.get("enabled", False))
        self.robot_map = self._parse_robot_config(mona_cfg.get("robots", []))
        
        # Connection state
        self._sockets: Dict[int, socket.socket] = {}
        self._pending_sockets: Dict[int, socket.socket] = {}
        self._buffers: Dict[int, bytearray] = {}
        
        # Debug cache (for confirm.py)
        self._last_set: Dict[int, dict] = {}
        self._last_get: Dict[int, dict] = {}
        self._cache_lock = Lock()
        
        # Debug server
        self._setup_debug_server(mona_cfg.get("debug_api", {}))

    def _parse_robot_config(self, robots: list) -> Dict[int, Tuple[str, int]]:
        """Parse robot configuration into agent_id -> (host, port) mapping."""
        return {
            int(r["agent_id"]): (str(r["host"]), int(r["port"]))
            for r in (robots or [])
            if all(k in r for k in ("agent_id", "host", "port"))
        }

    def _setup_debug_server(self, debug_cfg: dict):
        """Initialize debug API server if enabled."""
        if not debug_cfg.get("enabled", False):
            return
        
        host = debug_cfg.get("host", "127.0.0.1")
        port = int(debug_cfg.get("port", 8765))
        
        thread = Thread(
            target=self._run_debug_server,
            args=(host, port),
            daemon=True
        )
        thread.start()

    # ==================== Public API ====================

    def set_message(self, agent, msg_override: dict = None) -> None:
        """
        Send message to MONA robot.
        
        Args:
            agent: Agent object with agent_id attribute
            msg_override: Message dict to send (uses agent.message_to_share if None)
        """
        if not self.enabled:
            return
        
        try:
            agent_id = int(agent.agent_id)
        except (AttributeError, TypeError, ValueError):
            return
        
        sock = self._get_connection(agent_id)
        if sock is None:
            return
        
        msg = msg_override if isinstance(msg_override, dict) else getattr(agent, "message_to_share", None)
        if not isinstance(msg, dict) or not msg:
            return
        
        self._send_json(agent_id, sock, msg)

    def get_message(self, agent_id: int) -> Optional[dict]:
        """
        Receive latest message from MONA robot.
        
        Args:
            agent_id: Target robot's agent ID
            
        Returns:
            Latest monitor dict or None if unavailable
        """
        if not self.enabled:
            return None
        
        # 모든 메시지를 수집하고 병합
        all_messages = []
        while True:
            parsed = self._receive_json(agent_id)
            if parsed is None:
                break
            all_messages.append(parsed)
        
        if not all_messages:
            return None
        
        # 마지막 메시지를 기준으로 하되, received_messages는 병합
        merged = all_messages[-1].copy()
        merged_recv = {}
        
        for msg in all_messages:
            recv = msg.get("received_messages", {})
            if not recv:  # recv가 None이거나 빈 딕셔너리인 경우 스킵
                continue
            for peer_id, data in recv.items():
                # data가 None이거나 dict가 아닌 경우 스킵
                if not isinstance(data, dict):
                    continue
                
                # 더 최신 타임스탬프를 가진 데이터 유지
                if peer_id not in merged_recv:
                    merged_recv[peer_id] = data
                else:
                    existing_ts = merged_recv[peer_id].get("s", {}) if merged_recv[peer_id] else {}
                    new_ts = data.get("s", {}) if data else {}
                    # 타임스탬프 비교 후 더 최신 것 선택
                    if self._is_newer(new_ts, existing_ts):
                        merged_recv[peer_id] = data
        
        merged["received_messages"] = merged_recv
        
        if merged is not None:
            merged = self._transform_received_data(merged)
            with self._cache_lock:
                self._last_get[agent_id] = merged
        
        return merged

    def _is_newer(self, new_ts: dict, old_ts: dict) -> bool:
        """Compare timestamps to determine which is newer."""
        if not new_ts:
            return False
        if not old_ts:
            return True
        
        # None 값을 필터링하고 유효한 숫자만 비교
        new_values = [v for v in new_ts.values() if isinstance(v, (int, float))]
        old_values = [v for v in old_ts.values() if isinstance(v, (int, float))]
        
        new_max = max(new_values) if new_values else 0
        old_max = max(old_values) if old_values else 0
        
        return new_max > old_max

    def close(self) -> None:
        """Close all open connections."""
        for sock in list(self._sockets.values()):
            self._close_socket(sock)
        for sock in list(self._pending_sockets.values()):
            self._close_socket(sock)
        
        self._sockets.clear()
        self._pending_sockets.clear()
        self._buffers.clear()

    # ==================== Connection Management ====================

    def _get_connection(self, agent_id: int) -> Optional[socket.socket]:
        """Get or establish connection to robot."""
        if agent_id not in self.robot_map:
            return None
        
        # Check existing connection
        if agent_id in self._sockets:
            sock = self._sockets[agent_id]
            if self._is_connected(sock):
                return sock
            self._cleanup_connection(agent_id)
        
        # Check pending connection
        if agent_id in self._pending_sockets:
            return self._check_pending_connection(agent_id)
        
        # Start new connection
        return self._start_connection(agent_id)

    def _is_connected(self, sock: socket.socket) -> bool:
        """Check if socket is still connected."""
        try:
            sock.setblocking(False)
            data = sock.recv(1, socket.MSG_PEEK)
            return data != b''
        except BlockingIOError:
            return True
        except Exception:
            return False

    def _check_pending_connection(self, agent_id: int) -> Optional[socket.socket]:
        """Check status of pending async connection."""
        sock = self._pending_sockets[agent_id]
        
        try:
            _, writable, errored = select.select([], [sock], [sock], 0)
            
            if sock in writable:
                err = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
                if err == 0:
                    sock.setblocking(False)
                    self._sockets[agent_id] = sock
                    self._buffers[agent_id] = bytearray()
                    del self._pending_sockets[agent_id]
                    return sock
                raise OSError(err)
            
            if sock in errored:
                raise OSError("Socket error")
            
            return None
            
        except Exception:
            self._close_socket(sock)
            del self._pending_sockets[agent_id]
            return None

    def _start_connection(self, agent_id: int) -> Optional[socket.socket]:
        """Start async connection to robot."""
        host, port = self.robot_map[agent_id]
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setblocking(False)
            err = sock.connect_ex((host, port))
            
            if err == 0:
                self._sockets[agent_id] = sock
                self._buffers[agent_id] = bytearray()
                return sock
            
            if err in (errno.EINPROGRESS, errno.EWOULDBLOCK, 10035):
                self._pending_sockets[agent_id] = sock
                return None
            
            sock.close()
            return None
            
        except Exception:
            return None

    def _cleanup_connection(self, agent_id: int):
        """Clean up failed connection."""
        if agent_id in self._sockets:
            self._close_socket(self._sockets[agent_id])
            del self._sockets[agent_id]
        if agent_id in self._buffers:
            del self._buffers[agent_id]

    def _close_socket(self, sock: socket.socket):
        """Safely close a socket."""
        try:
            sock.close()
        except Exception:
            pass

    # ==================== Message I/O ====================

    def _send_json(self, agent_id: int, sock: socket.socket, msg: dict):
        """Send JSON message over socket."""
        try:
            line = json.dumps(msg, ensure_ascii=False, separators=(",", ":")) + "\n"
            sock.sendall(line.encode("utf-8"))
            
            with self._cache_lock:
                self._last_set[agent_id] = msg
                
        except BlockingIOError:
            pass
        except Exception:
            self._cleanup_connection(agent_id)

    def _receive_json(self, agent_id: int) -> Optional[dict]:
        """Receive and parse one JSON line from socket."""
        sock = self._get_connection(agent_id)
        if sock is None:
            return None
        
        buf = self._buffers.get(agent_id, bytearray())
        
        # Try to receive data
        try:
            chunk = sock.recv(RECV_BUFFER_SIZE)
            if chunk:
                buf.extend(chunk)
            else:
                self._cleanup_connection(agent_id)
                return None
        except BlockingIOError:
            pass
        except Exception:
            self._cleanup_connection(agent_id)
            return None
        
        self._buffers[agent_id] = buf
        
        # Parse complete line
        nl_idx = buf.find(NEWLINE)
        if nl_idx < 0:
            return None
        
        line = bytes(buf[:nl_idx]).decode("utf-8", "ignore").strip()
        del buf[:nl_idx + 1]
        
        if not line:
            return None
        
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return None

    # ==================== Data Transformation ====================

    def _transform_received_data(self, data: dict) -> dict:
        """Transform received monitor data to Space format."""
        if not data:
            return data
        
        recv_msgs = data.get("received_messages", {})
        if not recv_msgs:
            return data
        
        for payload in recv_msgs.values():
            if isinstance(payload, dict):
                payload["winning_agents"] = self._convert_keys_to_int(
                    payload.get("winning_agents", {}), none_to=None
                )
                payload["winning_bids"] = self._convert_keys_to_int(
                    payload.get("winning_bids", {}), none_to=0.0
                )
                payload["message_received_time_stamp"] = self._convert_keys_to_int(
                    payload.get("message_received_time_stamp", {}), none_to=0
                )
        
        return data

    def _convert_keys_to_int(self, data: dict, none_to=None) -> dict:
        """Convert string keys to integers in dict."""
        if not isinstance(data, dict):
            return data
        
        try:
            return {
                int(k): (v if v is not None else none_to)
                for k, v in data.items()
            }
        except (ValueError, TypeError):
            return data

    # ==================== Debug Server ====================

    def _run_debug_server(self, host: str, port: int):
        """
        Run debug API server for confirm.py.
        
        Commands:
        - GET_LAST_SET_ALL: Get all last sent messages
        - GET_LAST_GET_ALL: Get all last received messages  
        - POLL_GET:<id>: Poll specific agent immediately
        """
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((host, port))
        srv.listen(2)
        
        while True:
            conn = None
            try:
                conn, _ = srv.accept()
                conn.settimeout(SOCKET_TIMEOUT)
                
                cmd = self._read_line(conn)
                response = self._handle_debug_command(cmd)
                
                conn.sendall((json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8"))
                
            except Exception:
                pass
            finally:
                if conn:
                    self._close_socket(conn)

    def _read_line(self, conn: socket.socket) -> str:
        """Read a single line from connection."""
        buf = bytearray()
        while True:
            ch = conn.recv(1)
            if not ch or ch == NEWLINE:
                break
            buf.extend(ch)
        return bytes(buf).decode("utf-8", "ignore").strip()

    def _handle_debug_command(self, cmd: str) -> dict:
        """Handle debug API command and return response."""
        if cmd == "GET_LAST_SET_ALL":
            with self._cache_lock:
                return {"items": self._last_set.copy(), "ts_ms": int(time.time() * 1000)}
        
        if cmd == "GET_LAST_GET_ALL":
            with self._cache_lock:
                return {"items": self._last_get.copy(), "ts_ms": int(time.time() * 1000)}
        
        if cmd.startswith("POLL_GET:"):
            try:
                agent_id = int(cmd.split(":", 1)[1])
                result = self._receive_json(agent_id)
                if result is not None:
                    with self._cache_lock:
                        self._last_get[agent_id] = result
                return {"agent_id": agent_id, "result": result}
            except (ValueError, IndexError):
                return {"agent_id": None, "result": None}
        
        return {"error": "unknown command"}


# Backward compatibility alias
Mona_comm = MonaComm
