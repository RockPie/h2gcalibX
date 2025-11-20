
import sys, json, uuid, socket
import packetlibX

def print_err(msg):
    print(f"[clx_udp] ERROR: {msg}", file=sys.stderr)
def print_info(msg):
    print(f"[clx_udp] INFO: {msg}", file=sys.stdout)
def print_warn(msg):
    print(f"[clx_udp] WARNING: {msg}", file=sys.stdout)

# * ---------------------------------------------------------------------------
# * - brief: class to hold UDP connection settings
# * ---------------------------------------------------------------------------
class udp_target:
    def __init__(self, pc_ip, pc_port_cmd, pc_port_data, board_ip, board_port):
        self.pc_ip         = pc_ip
        self.pc_port_cmd   = pc_port_cmd
        self.pc_port_data  = pc_port_data
        self.board_ip    = board_ip
        self.board_port  = board_port
        # extract board_id from ip by minus 208 from last octet
        self.board_id      = int(board_ip.split('.')[-1]) - 208

        self.pool_conn_setup = False

    def load_udp_json(self, json_dict):
        try:
            assert "pc_ip"         in json_dict
            assert "pc_cmd_port"   in json_dict
            assert "pc_data_port"  in json_dict
            assert "h2gcroc_ip"    in json_dict
            assert "h2gcroc_port"  in json_dict
        except AssertionError:
            print_err("JSON dictionary missing required UDP keys")
            return
        self.pc_ip         = json_dict["pc_ip"]
        self.pc_port_cmd   = json_dict["pc_cmd_port"]
        self.pc_port_data  = json_dict["pc_data_port"]
        self.board_ip    = json_dict["h2gcroc_ip"]
        self.board_port  = json_dict["h2gcroc_port"]
        self.board_id      = int(self.board_ip.split('.')[-1]) - 208

    def load_udp_json_file(self, json_path):
        try:
            with open(json_path, 'r') as f:
                json_dict = json.load(f)
                self.load_udp_json(json_dict.get('udp', {}))
        except Exception as e:
            print_err(f"Failed to load UDP settings from JSON file: {e}")

    def load_pool_json(self, json_dict):
        try:
            assert "control_host"  in json_dict
            assert "control_port"  in json_dict
            assert "data_host"     in json_dict
            assert "data_port"     in json_dict
            assert "buffer_size"   in json_dict
        except AssertionError:
            print_err("JSON dictionary missing required pool keys")
            return
        self.control_host = json_dict["control_host"]
        self.control_port = json_dict["control_port"]
        self.data_host    = json_dict["data_host"]
        self.data_port    = json_dict["data_port"]
        self.buffer_size  = json_dict["buffer_size"]

    def load_pool_json_file(self, json_path):
        try:
            with open(json_path, 'r') as f:
                json_dict = json.load(f)
                self.load_pool_json(json_dict.get('pool', {}))
        except Exception as e:
            print_err(f"Failed to load pool settings from JSON file: {e}")

    def connect_to_pool(self, timeout=2.0):
        self.worker_id = str(uuid.uuid4())
        try:
            self.ctrl_conn, self.data_cmd_conn, self.data_data_conn, self.cmd_outbound_conn, self.pool_do = init_worker_sockets(self.worker_id, self.board_ip, self.pc_ip, self.control_host, self.control_port, self.data_host, self.data_port, self.pc_port_cmd, self.pc_port_data, timeout)
        except Exception as e:
            print_err(f"Failed to connect to pool: {e}")

        self.pool_do("register", "cmd",  self.pc_port_cmd)
        self.pool_do("register", "data", self.pc_port_data)

        self.pool_conn_setup = True

    # make sure the connection is closed when the object is deleted
    def __del__(self):
        if self.pool_conn_setup:
            self.pool_do("unregister", "cmd",  self.pc_port_cmd)
            self.pool_do("unregister", "data", self.pc_port_data)
            try:
                self.ctrl_conn.close()
                self.data_cmd_conn.close()
                self.data_data_conn.close()
                self.cmd_outbound_conn.close()
            except Exception as e:
                print_err(f"Failed to close pool connections: {e}")


# * ---------------------------------------------------------------------------
# * - brief: set up worker connections to the pool server
# * - param:
# * -   worker_id: unique identifier for the worker
# * -   h2gcroc_ip: IP address of the H2GCROC board
# * -   pc_ip: IP address of the PC
# * -   CONTROL_HOST: pool control local host
# * -   CONTROL_PORT: pool control local port
# * -   DATA_HOST: pool data local host
# * -   DATA_PORT: pool data local port
# * -   pc_cmd_port: PC command port
# * -   pc_data_port: PC data remote port
# * -   timeout: socket timeout in seconds
# * - return:
# * -   ctrl_conn: control connection socket
# * -   data_cmd_conn: data command connection socket
# * -   data_data_conn: data data connection socket
# * -   cmd_outbound_conn: command outbound UDP socket
# * -   pool_do: function to perform pool actions
# * ---------------------------------------------------------------------------
def init_worker_sockets(
    worker_id: str,
    h2gcroc_ip: str,
    pc_ip: str,
    CONTROL_HOST: str,
    CONTROL_PORT: int,
    DATA_HOST: str,
    DATA_PORT: int,
    pc_cmd_port: int,
    pc_data_port: int,
    timeout: float
):
    """
    Initialize all worker sockets and registration function.

    Returns:
        ctrl_conn, data_cmd_conn, data_data_conn, cmd_outbound_conn, pool_do
    """
    # Create sockets
    ctrl_conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    data_cmd_conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    data_data_conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    cmd_outbound_conn = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # Connect / bind
    ctrl_conn.connect((CONTROL_HOST, CONTROL_PORT))
    data_cmd_conn.connect((DATA_HOST, DATA_PORT))
    data_data_conn.connect((DATA_HOST, DATA_PORT))
    cmd_outbound_conn.bind((pc_ip, 0))

    # Set timeouts
    for s in (ctrl_conn, data_cmd_conn, data_data_conn, cmd_outbound_conn):
        s.settimeout(timeout)

    # Fetch assigned local ports
    ctrl_port    = ctrl_conn.getsockname()[1]
    cmd_data_port= data_cmd_conn.getsockname()[1]
    data_data_port = data_data_conn.getsockname()[1]

    # Log assignment
    print_info(
        f"Worker: {worker_id}, Port: {ctrl_port}")
    print_info(
        f"DataCMD Port: {cmd_data_port}, DataDATA Port: {data_data_port}"
    )

    # Send hello frames
    hello_data = {"action": "hello", "worker_id": worker_id, "direction": "data"}
    hello_cmd  = {"action": "hello", "worker_id": worker_id, "direction": "cmd"}

    data_cmd_conn.send(json.dumps(hello_cmd).encode())
    data_data_conn.send(json.dumps(hello_data).encode())

    # Define pool_do
    def pool_do(action: str, typ: str, do_port: int):
        msg = {
            "action":    action,
            "worker_id": worker_id,
            "type":      typ,
            "src_ip":    h2gcroc_ip,
            "port":      do_port
        }
        ctrl_conn.send(json.dumps(msg).encode())
        resp = json.loads(ctrl_conn.recv(1024).decode())
        return resp

    return ctrl_conn, data_cmd_conn, data_data_conn, cmd_outbound_conn, pool_do