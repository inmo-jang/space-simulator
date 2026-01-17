import json
import socket
import time
from typing import Dict, List, Tuple
from threading import Lock


class MonaController:
    
    def __init__(self, mona_cfg: Dict):
        self.enabled = bool(mona_cfg.get("enabled", False))
        self.robot_map = self._parse_robot_config(mona_cfg.get("robots", []))
        self.broadcast_interval_ms = mona_cfg.get("broadcast_interval_ms", 50)
        
        # UDP socket for sending
        self._socket = None
        if self.enabled:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            print(f"[MonaController] Initialized with {len(self.robot_map)} robots")
        
        # Timing
        self._last_broadcast_time: Dict[int, float] = {}
        
        # Thread safety
        self._lock = Lock()

    def _parse_robot_config(self, robots: list) -> Dict[int, Tuple[str, int]]:
        """Parse robot configuration into agent_id -> (host, port) mapping."""
        return {
            int(r["agent_id"]): (str(r["host"]), int(r["port"]))
            for r in (robots or [])
            if all(k in r for k in ("agent_id", "host", "port"))
        }

    def send_update(self, agent_id: int, position: Tuple[float, float], 
                    yaw: float, tasks: List) -> bool:
        if not self.enabled or self._socket is None:
            return False
        
        if agent_id not in self.robot_map:
            return False
        
        # Rate limiting
        now = time.time()
        last_time = self._last_broadcast_time.get(agent_id, 0)
        if (now - last_time) * 1000 < self.broadcast_interval_ms:
            return False
        
        # Build compact message
        # Tasks: only include non-completed tasks
        # When a task is completed by PC, it simply won't appear in the next broadcast
        # MONA robots will know it's completed because it's no longer in the list
        task_list = []
        for task in tasks:
            if not task.completed:
                task_list.append([
                    task.task_id,
                    round(task.position.x, 1),
                    round(task.position.y, 1),
                    round(task.amount, 2)
                ])
        
        message = {
            "id": agent_id,
            "x": round(position[0], 1),
            "y": round(position[1], 1),
            "yaw": round(yaw, 4),
            "t": task_list
        }
        
        # Send UDP packet
        host, port = self.robot_map[agent_id]
        try:
            data = json.dumps(message, separators=(',', ':')).encode('utf-8')
            self._socket.sendto(data, (host, port))
            self._last_broadcast_time[agent_id] = now
            return True
        except Exception as e:
            print(f"[MonaController] Send error to agent {agent_id}: {e}")
            return False

    def broadcast_to_all(self, agents: List, tasks: List) -> int:
        if not self.enabled:
            return 0
        
        sent_count = 0
        for agent in agents:
            if hasattr(agent, 'is_real_robot') and agent.is_real_robot:
                success = self.send_update(
                    agent_id=agent.agent_id,
                    position=(agent.position.x, agent.position.y),
                    yaw=agent.rotation,
                    tasks=tasks
                )
                if success:
                    sent_count += 1
        
        return sent_count

    def close(self):
        """Close UDP socket."""
        if self._socket:
            self._socket.close()
            self._socket = None
            print("[MonaController] Closed")


# Backward compatibility alias
Mona_comm = MonaController
