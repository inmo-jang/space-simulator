import time

class MessageCodec:
    """
    통신 메시지의 압축 및 복원을 담당하는 코덱 클래스.
    """
    BID_SCALE_FACTOR = 100000.0
    # 메시지 크기를 줄이기 위해 현재 시간을 기준으로 한 오프셋 사용
    TIMESTAMP_OFFSET = int(time.time())

    @staticmethod
    def _is_numeric_key(key) -> bool:
        try:
            int(key)
            return True
        except (ValueError, TypeError):
            return False

    @classmethod
    def encode(cls, agent_id, message_to_share, tasks_info) -> dict:
        """알고리즘 데이터를 ESP-NOW 포맷으로 압축"""
        if not message_to_share:
            return {}
        
        y_dict = message_to_share.get('winning_bids', {})
        z_dict = message_to_share.get('winning_agents', {})
        
        compressed_y = {}
        compressed_z = {}

        # 완료되지 않은 태스크 정보만 압축하여 전송량 절약
        for i, task in enumerate(tasks_info):
            if not task.completed:
                val_y = y_dict.get(i, y_dict.get(str(i)))
                if val_y is not None and float(val_y) > 0:
                    compressed_y[i] = int(round(float(val_y) * cls.BID_SCALE_FACTOR))
                
                val_z = z_dict.get(i, z_dict.get(str(i)))
                if val_z is not None and val_z != -1:
                    compressed_z[i] = int(val_z)

        s_data = message_to_share.get('message_received_time_stamp', {})
        compressed_s = {ag_id: int(ts) - cls.TIMESTAMP_OFFSET 
                        for ag_id, ts in s_data.items() 
                        if ts is not None and isinstance(ts, (int, float))}

        return {
            "id": int(agent_id),
            "y": compressed_y,
            "z": compressed_z,
            "s": compressed_s
        }

    @classmethod
    def decode(cls, raw_payload) -> dict:
        """압축된 데이터를 원래 알고리즘 형식으로 복원"""
        if not isinstance(raw_payload, dict) or "y" not in raw_payload:
            return None

        restored = {
            "agent_id": raw_payload.get("id", raw_payload.get("agent_id")),
            "winning_bids": {},
            "winning_agents": {},
            "message_received_time_stamp": {}
        }

        # 1. Winning Bids 복원
        y_raw = raw_payload["y"]
        if isinstance(y_raw, (dict, list)):
            items = y_raw.items() if isinstance(y_raw, dict) else enumerate(y_raw)
            restored["winning_bids"] = {
                int(tid): (val / cls.BID_SCALE_FACTOR)
                for tid, val in items if isinstance(val, (int, float)) and val > 0 and (isinstance(y_raw, list) or cls._is_numeric_key(tid))
            }

        # 2. Winning Agents 복원
        z_raw = raw_payload.get("z", {})
        if isinstance(z_raw, (dict, list)):
            items = z_raw.items() if isinstance(z_raw, dict) else enumerate(z_raw)
            restored["winning_agents"] = {
                int(tid): val for tid, val in items 
                if isinstance(val, (int, float)) and val != -1 and (isinstance(z_raw, list) or cls._is_numeric_key(tid))
            }

        # 3. Timestamps 복원
        s_raw = raw_payload.get("s", {})
        if isinstance(s_raw, dict):
            restored["message_received_time_stamp"] = {
                str(ag_id): (int(ts) + cls.TIMESTAMP_OFFSET)
                for ag_id, ts in s_raw.items() if isinstance(ts, (int, float)) and cls._is_numeric_key(ag_id)
            }

        return restored
