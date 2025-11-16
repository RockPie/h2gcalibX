#!/usr/bin/env python3
import socket
import selectors
import threading
import json
import os

# ——— Load configuration ———
cfg_path = os.path.join(os.path.dirname(__file__), 'config/socket_pool_config.json')
with open(cfg_path, 'r') as f:
    cfg = json.load(f)

CONTROL_HOST = cfg['CONTROL_HOST']
CONTROL_PORT = cfg['CONTROL_PORT']
DATA_HOST    = cfg['DATA_HOST']
DATA_PORT    = cfg['DATA_PORT']
BUFFER_SIZE  = cfg['BUFFER_SIZE']

class SocketPool:
    def __init__(self):
        self.sel           = selectors.DefaultSelector()
        self.port_socks    = {}   # UDP port → socket
        self.registrations = {}   # (typ, port, src_ip) → set(worker_id)
        self.data_conns    = {}   # (worker_id, typ) → TCP data socket

        # --- TCP control server ---
        self.ctrl_svr = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.ctrl_svr.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try: self.ctrl_svr.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except AttributeError: pass
        self.ctrl_svr.bind((CONTROL_HOST, CONTROL_PORT))
        self.ctrl_svr.listen()
        print(f"[Pool] Control → {CONTROL_HOST}:{CONTROL_PORT}", flush=True)

        # --- TCP data server ---
        self.data_svr = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.data_svr.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try: self.data_svr.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except AttributeError: pass
        self.data_svr.bind((DATA_HOST, DATA_PORT))
        self.data_svr.listen()
        print(f"[Pool] Data    → {DATA_HOST}:{DATA_PORT}", flush=True)

    def start(self):
        threading.Thread(target=self._accept_control, daemon=True).start()
        threading.Thread(target=self._accept_data,    daemon=True).start()
        self._udp_event_loop()

    def _accept_control(self):
        while True:
            conn, _ = self.ctrl_svr.accept()
            conn_host, conn_port = conn.getpeername()
            print(f"[Pool] Control socket connected: {conn_host}:{conn_port}")
            threading.Thread(target=self._handle_control, args=(conn,), daemon=True).start()

    def _accept_data(self):
        while True:
            conn, _ = self.data_svr.accept()
            raw = conn.recv(BUFFER_SIZE)
            try:
                msg = json.loads(raw.decode())
                assert msg.get("action") == "hello"
                wid       = msg["worker_id"]
                direction = msg["direction"]
                assert direction in ("data", "cmd")
            except Exception:
                conn.close()
                continue
            # store per‐worker, per‐direction data socket
            self.data_conns[(wid, direction)] = conn
            print(f"[Pool] {direction.upper():4} socket connected: {wid}", flush=True)

    def _handle_control(self, conn):
        try:
            while True:
                raw = conn.recv(BUFFER_SIZE)
                if not raw:
                    break
                msg       = json.loads(raw.decode())
                action    = msg.get("action")
                worker_id = msg.get("worker_id")
                typ       = msg.get("type")    # "data" or "cmd"
                port      = msg.get("port")
                src_ip    = msg.get("src_ip")
                key       = (typ, port, src_ip)

                if action == "register":
                    self._ensure_udp(port)
                    self.registrations.setdefault(key, set()).add(worker_id)
                    conn.send(b'{"status":"ok"}')
                    print(f"[Pool] REGISTER   {worker_id} → {key}", flush=True)

                elif action == "unregister":
                    regs = self.registrations.get(key, set())
                    if worker_id in regs:
                        regs.remove(worker_id)
                        if not regs:
                            del self.registrations[key]
                            # if no registrations left on this port, close it
                            if not any(k[1] == port for k in self.registrations):
                                self._close_udp(port)
                        conn.send(b'{"status":"ok"}')
                        print(f"[Pool] UNREGISTER {worker_id} → {key}")
                    else:
                        conn.send(b'{"status":"error","reason":"not registered"}')
                else:
                    conn.send(b'{"status":"error","reason":"bad action"}')
        except Exception as e:
            print(f"[Pool] control error: {e}", flush=True)
        finally:
            conn.close()

    def _ensure_udp(self, port):
        if port in self.port_socks:
            return
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.setblocking(False)
        udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try: udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except AttributeError: pass
        udp.bind(("0.0.0.0", port))
        self.sel.register(udp, selectors.EVENT_READ, data=port)
        self.port_socks[port] = udp
        print(f"[Pool] Bound UDP port {port}", flush=True)

    def _close_udp(self, port):
        udp = self.port_socks.pop(port, None)
        if not udp:
            return
        self.sel.unregister(udp)
        udp.close()
        print(f"[Pool] Closed UDP port {port}", flush=True)

    def _udp_event_loop(self):
        while True:
            for key, _ in self.sel.select(timeout=1.0):
                udp_sock = key.fileobj
                port     = key.data
                data, (src_ip, _) = udp_sock.recvfrom(BUFFER_SIZE)

                # forward to each worker’s matching data_conn
                # if len(data) < 1000:
                #     typ = "cmd"
                # else:
                #     typ = "data"
                for typ in ("data", "cmd"):
                    key = (typ, port, src_ip)
                    for wid in self.registrations.get(key, []):
                        conn = self.data_conns.get((wid, typ))
                        if conn:
                            try:
                                # print(f"[Pool] Forwarded {len(data)} bytes to {wid} ({typ})")
                                # peer_addr, peer_port = conn.getpeername()
                                # print(f"[Pool] {typ.upper():4} socket used: {peer_addr}:{peer_port}")
                                # if typ == "data":
                                #     # print all the bytes in hex
                                #     print(' '.join([f"{x:02x}" for x in data]))
                                conn.sendall(data)
                            except Exception:
                                conn.close()
                                del self.data_conns[(wid, typ)]
                                print(f"[Pool] Dropped {typ.upper():4} conn for {wid}", flush=True)

if __name__ == "__main__":
    pool = SocketPool()
    pool.start()