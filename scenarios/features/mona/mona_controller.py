# scenarios/features/mona/mona_controller.py
# -*- coding: utf-8 -*-
"""
Mona_comm: Space-simulator <-> MONA(ESP32) TCP 브리지
- 역할: 통신 관리 + 데이터 전처리(JSON -> Space 포맷 변환) 담당
- set_message(agent): agent.message_to_share(dict) 를 대상 MONA 보드로 JSON 한 줄 전송
- get_message(agent_id): 대상 MONA 보드로부터 모니터 JSON 한 줄을 읽어 dict로 반환(None 가능)
- close(): 열린 소켓 정리

프로토콜
-> 개행을 통해 mona가 이 메세지가 JSON이라는 것을 판단하기 위함
- 송신: UTF-8 JSON + '\n' (한 줄)
- 수신: UTF-8 JSON + '\n' (한 줄)  # 보드가 self_message+received_messages를 합친 모니터 JSON을 스트리밍
"""

import json
import socket
import time
import errno
import select
from typing import Dict, Tuple, Optional
from threading import Thread, Lock # confirm.py 와 연동

_NEWLINE = b"\n"

class Mona_comm:
    def __init__(self, mona_cfg: Dict):
        """
        yaml에서 넘어온 enabled, robots 읽어와 내부 상태 세팅
        mona_cfg 예시:
        {
          "enabled": true,
          "robots": [
            {"agent_id": 0, "host": "192.168.0.44", "port": 8080},
            ...
          ]
        }
        """
        self.enabled: bool = bool(mona_cfg.get("enabled", False))
        robots = mona_cfg.get("robots", []) or []
        # agent_id -> (host, port)
        self.robot_map: Dict[int, Tuple[str, int]] = {
            int(r["agent_id"]): (str(r["host"]), int(r["port"])) for r in robots
            if "agent_id" in r and "host" in r and "port" in r
        }

        # 내부 상태: 연결 풀/수신버퍼
        self._socks: Dict[int, socket.socket] = {}
        self._buffers: Dict[int, bytearray] = {}

        # confirm.py가 내용 조회 용도 (debug용)
        self._pending_socks: Dict[int, socket.socket] = {}
        self._last_set: Dict[int, dict] = {}
        self._last_get: Dict[int, dict] = {}
        self._cache_lock = Lock()

        dbg = (mona_cfg or {}).get("debug_api", {}) or {}
        self._dbg_enabled = bool(dbg.get("enabled", False))
        self._dbg_host = dbg.get("host", "127.0.0.1")
        self._dbg_port = int(dbg.get("port", 8765))
        self._dbg_thread: Optional[Thread] = None
        if self._dbg_enabled:
            self._dbg_thread = Thread(target=self._run_debug_server, daemon=True)
            self._dbg_thread.start()

    # --- 데이터 전처리 함수---
    def _convert_data_JSON_to_Space(self, msg_dict):
        """ 
        MONA(JSON) 데이터를 Space 시뮬레이터 포맷으로 변환
        1. Key: string '0' -> int 0
        2. Value: None -> 0 (기본값)
        """
        if not isinstance(msg_dict, dict):
            return msg_dict
        
        clean_dict = {}
        try:
            for k, v in msg_dict.items():
                key = int(k) # Key를 정수형으로 변환
                value = v if v is not None else 0 # None 방지
                clean_dict[key] = value
            return clean_dict
        except (ValueError, TypeError):
            return msg_dict
    
    def _recv_comm_Transform(self, recv_mona_comm_data: dict) -> dict:
        """ 수신된 전체 모니터 데이터 내부를 순회하며 정제 """
        if not recv_mona_comm_data:
            return recv_mona_comm_data
            
        recv_msgs = recv_mona_comm_data.get("received_messages", {})
        if not recv_msgs:
            return recv_mona_comm_data
            
        # 이웃 데이터 하나하나를 꺼내서 변환
        for neighbor_id, payload in recv_msgs.items():
            if isinstance(payload, dict):
                # 변환이 필요한 주요 필드들을 처리
                payload['winning_agents'] = self._convert_data_JSON_to_Space(payload.get('winning_agents', {}))
                payload['winning_bids'] = self._convert_data_JSON_to_Space(payload.get('winning_bids', {}))
                payload['message_received_time_stamp'] = self._convert_data_JSON_to_Space(payload.get('message_received_time_stamp', {}))
        
        return recv_mona_comm_data
    # -------------------------------------------

    def _manage_mona_connection(self, agent_id: int) -> Optional[socket.socket]:
        if agent_id not in self.robot_map or not self.enabled:
            return None

        # 지속적인 연결되는지 확인
        if agent_id in self._socks:
            s = self._socks[agent_id]
            try:
                s.setblocking(False) # non-blocking으로 수신여부 기다리지 않고 다음코드 실행
                data = s.recv(1, socket.MSG_PEEK)
                if data == b'': raise OSError("Connection closed")
                return s
            except BlockingIOError: return s
            except Exception:
                try: s.close()
                except: pass
                self._socks.pop(agent_id, None)
                if agent_id in self._buffers: del self._buffers[agent_id]

        # 연결 시도 중인 mona 확인
        if agent_id in self._pending_socks:
            s = self._pending_socks[agent_id]
            try:
                _, writable, in_error = select.select([], [s], [s], 0)
                if s in writable:
                    err = s.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
                    if err == 0:
                        s.setblocking(False)
                        self._socks[agent_id] = s
                        self._buffers[agent_id] = bytearray()
                        del self._pending_socks[agent_id]
                        return s
                    else: raise OSError(err)
                elif s in in_error: raise OSError("Socket error")
                else: return None
            except Exception:
                try: s.close()
                except: pass
                del self._pending_socks[agent_id]
                return None

        host, port = self.robot_map[agent_id]
        # mona와의 연결 새로 시도
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setblocking(False)
            err = s.connect_ex((host, port))
            if err == 0:
                self._socks[agent_id] = s
                self._buffers[agent_id] = bytearray()
                return s
            elif err == errno.EINPROGRESS or err == errno.EWOULDBLOCK or err == 10035:
                self._pending_socks[agent_id] = s
                return None
            else:
                s.close()
                return None
        except Exception:
            return None

    def _transform_Json_to_dict(self, agent_id: int) -> Optional[dict]:
        s = self._manage_mona_connection(agent_id)
        if s is None: return None

        buf = self._buffers[agent_id]
        # 수신 시도
        try:
            chunk = s.recv(4096)
            if chunk: buf.extend(chunk)
            else:
                try: s.close()
                except: pass
                self._socks.pop(agent_id, None)
                return None
        except BlockingIOError: pass
        except Exception:
            try: s.close()
            except: pass
            self._socks.pop(agent_id, None)
            return None

        # 개행 기준으로 한 줄 파싱
        nl_idx = buf.find(_NEWLINE)
        if nl_idx < 0: return None

        line = bytes(buf[:nl_idx]).decode("utf-8", "ignore").strip()
        # 버퍼에서 제거
        del buf[:nl_idx + 1]

        if not line: return None
        try: return json.loads(line)
        except: return None

    # ---- 공개 API ----
    def set_message(self, agent) -> None:
        if not self.enabled: return
        try: agent_id = int(getattr(agent, "agent_id"))
        except: return
        s = self._manage_mona_connection(agent_id)
        if s is None: return
        msg = getattr(agent, "message_to_share", None)
        if not isinstance(msg, dict) or not msg: return
        try:
            line = (json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8")
            s.sendall(line)
            with self._cache_lock: self._last_set[agent_id] = msg
        except BlockingIOError: pass
        except Exception:
            try: s.close()
            except: pass
            self._socks.pop(agent_id, None)

    def get_message(self, agent_id: int) -> Optional[dict]:
        """
        데이터를 받아서 _recv_comm_Transform로 전처리 후 리턴
        """
        if not self.enabled: return None
        try: agent_id = int(agent_id)
        except: return None

        parsed = self._transform_Json_to_dict(agent_id)
        
        if parsed is not None:
            # ---데이터 전처리 과정---
            parsed = self._recv_comm_Transform(parsed)
            
            with self._cache_lock:
                self._last_get[agent_id] = parsed
        return parsed

    def close(self) -> None:
        """열린 소켓 정리(프로세스 종료 시 호출 권장)."""
        for k, s in list(self._socks.items()):
            try: s.close()
            except: pass
            self._socks.pop(k, None)
        for k, s in list(self._pending_socks.items()):
            try: s.close()
            except: pass
            self._pending_socks.pop(k, None)
        self._buffers.clear()

    # --------------------------------------------------------
    # ※ 간단한 로컬 디버그 서버 (Confirm.py 위한 부분)
    #   - confirm.py 가 시뮬레이터가 "보낸/받은" 최근 JSON을 조회
    #   - 텍스트 1줄 커맨드 → 1줄 JSON 응답
    #     * GET_LAST_SET_ALL  → {"items": {agent_id: {...}}, "ts_ms": ...}
    #     * GET_LAST_GET_ALL  → {"items": {agent_id: {...}}, "ts_ms": ...}
    #     * POLL_GET:<id>     → {"agent_id": id, "result": {... or null}}
    # --------------------------------------------------------
    def _run_debug_server(self) -> None:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((self._dbg_host, self._dbg_port))
        srv.listen(2)
        while True:
            try:
                conn, _ = srv.accept()
                conn.settimeout(2.0)
                # 명령 한 줄 읽기
                buf = bytearray()
                while True:
                    ch = conn.recv(1)
                    if not ch:
                        break
                    if ch == _NEWLINE:
                        break
                    buf.extend(ch)
                cmd = bytes(buf).decode("utf-8", "ignore").strip()

                if cmd == "GET_LAST_SET_ALL":
                    with self._cache_lock:
                        payload = {"items": self._last_set, "ts_ms": int(time.time() * 1000)}
                    out = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
                    conn.sendall(out)

                elif cmd == "GET_LAST_GET_ALL":
                    with self._cache_lock:
                        payload = {"items": self._last_get, "ts_ms": int(time.time() * 1000)}
                    out = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
                    conn.sendall(out)

                elif cmd.startswith("POLL_GET:"):
                    try:
                        agent_id = int(cmd.split(":", 1)[1])
                    except Exception:
                        agent_id = None
                    result = None
                    if agent_id is not None:
                        result = self._transform_Json_to_dict(agent_id)
                        if result is not None:
                            with self._cache_lock:
                                self._last_get[agent_id] = result
                    out = (json.dumps({"agent_id": agent_id, "result": result}, ensure_ascii=False) + "\n").encode("utf-8")
                    conn.sendall(out)

                else:
                    conn.sendall(b'{"error":"unknown command"}\n')

            except Exception:
                # 다음 연결 대기
                pass
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
