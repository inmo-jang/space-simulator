# confirm.py (simulator debug API client)
# -*- coding: utf-8 -*-
import socket, json

HOST = "127.0.0.1"
PORT = 8765

def _req(cmd: str):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(2.0)
        s.connect((HOST, PORT))
        s.sendall((cmd + "\n").encode("utf-8"))
        buf = b""
        while True:
            ch = s.recv(1)
            if not ch:
                break
            buf += ch
            if buf.endswith(b"\n"):
                break
    try:
        return json.loads(buf.decode("utf-8", "ignore"))
    except Exception:
        return {"error": "parse failed", "raw": buf.decode("utf-8", "ignore")}

def show_last_set_all():
    resp = _req("GET_LAST_SET_ALL")
    print("\n[SET] 시뮬레이터가 보드로 보낸 마지막 메시지들:")
    print(json.dumps(resp, ensure_ascii=False, indent=2))

def show_last_get_all():
    resp = _req("GET_LAST_GET_ALL")
    print("\n[GET] 시뮬레이터가 보드에서 받은 마지막 메시지들:")
    print(json.dumps(resp, ensure_ascii=False, indent=2))

def poll_get_one():
    a = input("즉시 폴링할 agent_id (정수, 예: 0): ").strip()
    try:
        agent_id = int(a)
    except Exception:
        print("정수로 입력하세요.")
        return
    resp = _req(f"POLL_GET:{agent_id}")
    print("\n[POLL_GET] 결과:")
    print(json.dumps(resp, ensure_ascii=False, indent=2))

def main():
    print("confirm (space-simulator debug API)")
    print(f"server: {HOST}:{PORT}")
    while True:
        print("\n1) 마지막 set_message(시뮬레이터→보드) 전체 보기")
        print("2) 마지막 get_message(보드→시뮬레이터) 전체 보기")
        print("3) (선택) 특정 agent_id 즉시 POLL_GET")
        print("q) 종료")
        sel = input("> ").strip().lower()
        if sel == "1":
            show_last_set_all()
        elif sel == "2":
            show_last_get_all()
        elif sel == "3":
            poll_get_one()
        elif sel == "q":
            break
        else:
            print("올바른 키를 입력하세요.")

if __name__ == "__main__":
    main()
