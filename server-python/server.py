import zmq
import datetime
import json
import os
import message_pb2

DATA_FILE = os.getenv("DATA_FILE", "/data/state.json")
SERVER_NAME = os.getenv("SERVER_NAME", "server_UNKNOWN")

state_logins: list = []
state_channels: list = []

def load_state():
    global state_logins, state_channels
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                data = json.load(f)
                state_logins = data.get("logins", [])
                if isinstance(state_logins, dict):
                    state_logins = []
                state_channels = data.get("channels", [])
        except Exception as e:
            print(f"Erro ao ler state: {e}")

def save_state():
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump({
            "logins": state_logins,
            "channels": state_channels
        }, f)

def log(msg, direction, target, msg_type, content, result=""):
    ts = datetime.datetime.now().isoformat()
    res_str = f" | result={result}" if result else ""
    if direction == "in":
        print(f"[{ts}] CLIENT {target} -> SERVER {SERVER_NAME} | {msg_type} | {content}{res_str} | msg_ts={msg.timestamp}", flush=True)
    else:
        print(f"[{ts}] SERVER {SERVER_NAME} -> CLIENT {target} | {msg_type} | {content}{res_str} | msg_ts={msg.timestamp}", flush=True)

def handle_request(raw_msg, socket_pub):
    req = message_pb2.Message()
    req.ParseFromString(raw_msg)
    
    rep = message_pb2.Message()
    rep.timestamp = datetime.datetime.now().isoformat()
    rep.sender = SERVER_NAME
    
    client_name = req.sender
    
    if req.type == message_pb2.Message.LOGIN_REQ:
        username = req.login_req.username
        log(req, "in", client_name, "LOGIN_REQ", f"user={username}")
        
        rep.type = message_pb2.Message.LOGIN_REP
        if len(username) < 3 or len(username) > 20 or not username.replace("_", "").isalnum():
            rep.login_rep.success = False
            rep.login_rep.error_message = "Nome de usuario invalido (deve ser alfanumerico com tamanho 3-20)"
            log(rep, "out", client_name, "LOGIN_REP", f"user={username}", "ERROR")
        else:
            rep.login_rep.success = True
            rep.login_rep.error_message = ""
            state_logins.append({
                "username": username,
                "timestamp": datetime.datetime.now().isoformat(),
                "server_id": SERVER_NAME
            })
            save_state()
            log(rep, "out", client_name, "LOGIN_REP", f"user={username}", "OK")
            
    elif req.type == message_pb2.Message.CREATE_CHANNEL_REQ:
        ch_name = req.create_req.channel_name
        log(req, "in", client_name, "CREATE_CHANNEL_REQ", f"channel={ch_name}")
        
        rep.type = message_pb2.Message.CREATE_CHANNEL_REP
        if not ch_name.startswith("#") or len(ch_name) < 3:
            rep.create_rep.success = False
            rep.create_rep.error_message = "Nome invalido. Insira um canal que inicie com # e possua pelo menos 3 caracteres"
            log(rep, "out", client_name, "CREATE_CHANNEL_REP", f"channel={ch_name}", "ERROR")
        elif ch_name in state_channels:
            rep.create_rep.success = False
            rep.create_rep.error_message = "Canal repetido. Ja existe neste servidor."
            log(rep, "out", client_name, "CREATE_CHANNEL_REP", f"channel={ch_name}", "ERROR")
        else:
            rep.create_rep.success = True
            rep.create_rep.error_message = ""
            state_channels.append(ch_name)
            save_state()
            
            evt = message_pb2.Message()
            evt.type = message_pb2.Message.REPLICATE_CHANNEL_EVENT
            evt.timestamp = datetime.datetime.now().isoformat()
            evt.sender = SERVER_NAME
            evt.replicate_event.channel_name = ch_name
            evt.replicate_event.source_server_id = SERVER_NAME
            socket_pub.send(evt.SerializeToString())
            
            ts_now = datetime.datetime.now().isoformat()
            print(f"[{ts_now}] SERVER {SERVER_NAME} created channel {ch_name} locally", flush=True)
            print(f"[{ts_now}] SERVER {SERVER_NAME} replicated channel {ch_name}", flush=True)
            
            log(rep, "out", client_name, "CREATE_CHANNEL_REP", f"channel={ch_name}", "OK")

    elif req.type == message_pb2.Message.LIST_CHANNELS_REQ:
        log(req, "in", client_name, "LIST_CHANNELS_REQ", "")
        rep.type = message_pb2.Message.LIST_CHANNELS_REP
        rep.list_rep.channels.extend(state_channels)
        channels_str = ",".join(state_channels)
        log(rep, "out", client_name, "LIST_CHANNELS_REP", f"channels=[{channels_str}]", "OK")
    
    else:
        rep.type = message_pb2.Message.UNKNOWN
        
    return rep.SerializeToString()

def handle_replication(raw_msg):
    evt = message_pb2.Message()
    evt.ParseFromString(raw_msg)
    if evt.type == message_pb2.Message.REPLICATE_CHANNEL_EVENT:
        ch_name = evt.replicate_event.channel_name
        source_id = evt.replicate_event.source_server_id
        if source_id != SERVER_NAME and ch_name not in state_channels:
            state_channels.append(ch_name)
            save_state()
            ts_now = datetime.datetime.now().isoformat()
            print(f"[{ts_now}] SERVER {SERVER_NAME} applied replicated channel {ch_name} from {source_id}", flush=True)

def main():
    load_state()
    context = zmq.Context()
    
    socket_rep = context.socket(zmq.REP)
    broker_url = os.getenv("BROKER_URL", "tcp://broker:5556")
    socket_rep.connect(broker_url)
    
    socket_pub = context.socket(zmq.PUB)
    pub_url = os.getenv("PUB_URL", "tcp://broker:5557")
    socket_pub.connect(pub_url)
    
    socket_sub = context.socket(zmq.SUB)
    sub_url = os.getenv("SUB_URL", "tcp://broker:5558")
    socket_sub.connect(sub_url)
    socket_sub.setsockopt_string(zmq.SUBSCRIBE, "")
    
    poller = zmq.Poller()
    poller.register(socket_rep, zmq.POLLIN)
    poller.register(socket_sub, zmq.POLLIN)
    
    print(f"Servidor {SERVER_NAME} conectado ao broker em {broker_url}.", flush=True)
    
    while True:
        try:
            socks = dict(poller.poll())
            if socket_rep in socks:
                raw_msg = socket_rep.recv()
                reply = handle_request(raw_msg, socket_pub)
                socket_rep.send(reply)
            if socket_sub in socks:
                raw_msg = socket_sub.recv()
                handle_replication(raw_msg)
        except Exception as e:
            print(f"Erro no loop principal: {e}", flush=True)

if __name__ == "__main__":
    main()
