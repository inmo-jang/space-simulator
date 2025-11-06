# scenarios/features/mona/mona_client.py
# -*- coding: utf-8 -*-
"""
Mona_comm: Space-simulator <-> MONA(ESP32) TCP 브리지 (최소 구현)
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
from typing import Dict, Tuple, Optional
from threading import Thread, Lock  # 디버그 API/캐시용

_NEWLINE = b"\n"
_DEFAULT_TIMEOUT = 0.2  # keep_connection에 가까운 짧은 대기


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

        # --------------------------------------------------------
        # 최근 송/수신 캐시 + 디버그 API(127.0.0.1)
        #   - confirm.py가 space-simulator가 실제 "보낸/받은" 내용을 조회할 수 있도록
        #   - mona.yaml 에서:
        #       mona:
        #         debug_api:
        #           enabled: true
        #           host: 127.0.0.1
        #           port: 8765
        # --------------------------------------------------------
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

    # ---- 내부 유틸 ----
    def _ensure_conn(self, agent_id: int) -> Optional[socket.socket]:
        """
        주어진 agent_id 보드와 TCP 연결 여부 확인
        -> 연결 X = 재연결함.
        -> 연결 성공 시 소켓 반환, 실패 시 None.
        """
        if agent_id not in self.robot_map or not self.enabled:
            return None

        # 이미 연결되어 있으면 반환
        s = self._socks.get(agent_id)
        if s is not None:
            try:
                # 간단한 연결 검증: keep_connection recv(0 bytes)
                s.settimeout(0.0)
                s.recv(0)
            except BlockingIOError:
                pass
            except Exception:
                # 죽은 소켓이면 정리 후 재연결
                try:
                    s.close()
                except Exception:
                    pass
                s = None
                self._socks.pop(agent_id, None)

        if s is None:
            host, port = self.robot_map[agent_id]
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(_DEFAULT_TIMEOUT)
            try:
                s.connect((host, port))
            except Exception:
                # 연결 실패 시 조용히 None
                try:
                    s.close()
                except Exception:
                    pass
                return None
            # keep_connection 수신을 위해 timeout 짧게
            s.settimeout(_DEFAULT_TIMEOUT)
            self._socks[agent_id] = s
            self._buffers.setdefault(agent_id, bytearray())
        return s

    def _transform_Json_to_dict(self, agent_id: int) -> Optional[dict]:
        """
        개행 단위로 한 줄 JSON을 읽어서 dict로 반환.
        새 데이터가 없거나 파싱 실패하면 None.
        """
        s = self._ensure_conn(agent_id)
        if s is None:
            return None

        buf = self._buffers[agent_id]
        # 수신 시도
        try:
            chunk = s.recv(4096)
            if chunk:
                buf.extend(chunk)
        except socket.timeout:
            pass
        except BlockingIOError:
            pass
        except Exception:
            # 소켓 에러 -> 연결 종료
            try:
                s.close()
            except Exception:
                pass
            self._socks.pop(agent_id, None)
            return None

        # 개행 기준으로 한 줄 파싱
        nl_idx = buf.find(_NEWLINE)
        if nl_idx < 0:
            return None

        line = bytes(buf[:nl_idx]).decode("utf-8", "ignore").strip()
        # 버퍼에서 제거
        del buf[:nl_idx + 1]

        if not line:
            return None
        try:
            return json.loads(line)
        except Exception:
            return None

    # ---- 공개 API ----
    def set_message(self, agent) -> None:
        """
        Agent.update()에서 호출.
        - agent.agent_id (int)
        - agent.message_to_share (dict)  # 없거나 비어 있으면 전송 생략
        """
        if not self.enabled:
            return
        try:
            agent_id = int(getattr(agent, "agent_id"))
        except Exception:
            return

        s = self._ensure_conn(agent_id)
        if s is None:
            return
        """
        dict -> JSON 한줄로 만들어 개행하여 UTF-8 인코딩을 통해 모든 바이트 끝까지 보냄(sendall)
        """
        msg = getattr(agent, "message_to_share", None)
        if not isinstance(msg, dict) or not msg:
            return

        # JSON 한 줄로 전송
        try:
            line = (json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8")
            s.sendall(line)
            # 보낸 원본을 캐시에 기록 (confirm.py 위함)
            with self._cache_lock:
                self._last_set[agent_id] = msg
        except Exception:
            # 전송 실패 시 연결을 끊고 다음 틱에서 재시도
            try:
                s.close()
            except Exception:
                pass
            self._socks.pop(agent_id, None)

    def get_message(self, agent_id: int) -> Optional[dict]:
        """
        GatherLocalInfo(local_message_receive)에서 호출.
        - 대상 보드로부터 최신 '모니터 JSON 한 줄'을 읽어 dict로 반환.
        - 새 데이터가 없으면 None.
        """
        if not self.enabled:
            return None
        try:
            agent_id = int(agent_id)
        except Exception:
            return None

        parsed = self._transform_Json_to_dict(agent_id)
        if parsed is not None:
            # 받은 최종본을 캐시에 기록 (confrim.py 위함)
            with self._cache_lock:
                self._last_get[agent_id] = parsed
        return parsed

    def close(self) -> None:
        """열린 소켓 정리(프로세스 종료 시 호출 권장)."""
        for k, s in list(self._socks.items()):
            try:
                s.close()
            except Exception:
                pass
            self._socks.pop(k, None)
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
