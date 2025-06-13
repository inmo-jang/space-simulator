# tacview_server.py
"""
Tacview real-time telemetry server capable of handling multiple aircraft.
"""
import socket
import threading
import time
import queue
from datetime import datetime, timezone
from aircraft_state import AircraftState
from config import HOST, PORT

class TacviewServer:
    def __init__(self, data_queue: queue.Queue):
        self.data_queue = data_queue
        self.server_socket = None
        self.running = False

    def handle_client(self, conn: socket.socket, addr):
        print(f"[+] Client connected: {addr}")
        known_aircraft = set()
        
        try:
            # Send server probe and wait for client handshake
            conn.sendall("XtraLib.Stream.0\nTacview.RealTimeTelemetry.0\nPX4-Multi-Bridge\n\0".encode('utf-8'))
            conn.settimeout(5.0)
            handshake = conn.recv(1024)
            if not handshake:
                raise ConnectionAbortedError("Client did not send handshake.")
            print(f"[>] Client handshake received from {addr}")
            conn.settimeout(None)

            # Send ACMI header
            ref_time = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            header = (
                f"FileType=text/acmi/tacview\r\nFileVersion=2.2\r\n"
                f"0,ReferenceTime={ref_time}\r\n"
                # f"0,DataSource=PX4 MAVROS Bridge\r\n"
                # f"0,Author=Multi-UAV Pilot\r\n\r\n"
            )
            conn.sendall(header.encode('utf-8'))
            print(f"[<] ACMI header sent to {addr}")

            start_time = time.time()
            while self.running:
                frame_data = {}
                while not self.data_queue.empty():
                    state: AircraftState = self.data_queue.get_nowait()
                    frame_data[state.aircraft_id] = state

                if not frame_data:
                    time.sleep(0.05)
                    continue

                time_offset = time.time() - start_time
                acmi_frame = f"#{time_offset:.2f}\r\n"

                for ac_id, state in frame_data.items():
                    # Initial object definition
                    if ac_id not in known_aircraft:
                        acmi_frame += (
                            f"{state.aircraft_id},"
                            f"T={state.longitude:.6f}|{state.latitude:.6f}|{state.altitude_m:.1f},"
                            f"Name={state.aircraft_type},"
                            f"Pilot={state.pilot_name},"
                            f"Type=Air+FixedWing," # Can be made dynamic
                            f"Coalition={state.coalition},"
                            f"Country={state.country}\r\n"
                        )
                        known_aircraft.add(ac_id)

                    # Object data update
                    acmi_frame += (
                        f"{state.aircraft_id},"
                        f"T={state.longitude:.6f}|{state.latitude:.6f}|{state.altitude_m:.1f}|"
                        f"{state.roll_deg:.1f}|{state.pitch_deg:.1f}|{state.yaw_deg:.1f},"
                        f"Speed={state.ground_speed_knots:.1f}\r\n"
                    )
                
                conn.sendall(acmi_frame.encode('utf-8'))
                time.sleep(0.1) # 10Hz update rate

        except (BrokenPipeError, ConnectionResetError):
            print(f"[!] Client {addr} disconnected.")
        except socket.timeout:
            print(f"[!] Client {addr} handshake timeout.")
        except Exception as e:
            print(f"[!] Error with client {addr}: {e}")
        finally:
            conn.close()
            print(f"[-] Client connection closed: {addr}")

    def start(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.running = True
        
        try:
            self.server_socket.bind((HOST, PORT))
            self.server_socket.listen(5)
            print(f"[+] Tacview server listening on {HOST}:{PORT}")

            while self.running:
                conn, addr = self.server_socket.accept()
                client_thread = threading.Thread(target=self.handle_client, args=(conn, addr))
                client_thread.daemon = True
                client_thread.start()
        
        except OSError as e:
            print(f"[!] Server socket error: {e}")
        finally:
            self.stop()

    def stop(self):
        self.running = False
        if self.server_socket:
            self.server_socket.close()
        print("[*] Tacview server stopped.")