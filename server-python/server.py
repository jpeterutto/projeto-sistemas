import zmq
import datetime
import json
import os
import message_pb2

DATA_FILE = os.getenv("DATA_FILE", "/data/state.json")
SERVER_NAME = os.getenv("SERVER_NAME", "server_UNKNOWN")
REFERENCE_URL = os.getenv("REFERENCE_URL", "tcp://reference:5560")

state_logins: list = []
state_channels: list = []
state_publications: list = []

# Part 3 State
logical_clock = 0
client_messages_since_last_heartbeat = 0
server_rank = -1
clock_offset_millis = 0.0

socket_reference = None

def load_state():
    global state_logins, state_channels, state_publications
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                data = json.load(f)
                state_logins = data.get("logins", [])
                if isinstance(state_logins, dict):
                    state_logins = []
                state_channels = data.get("channels", [])
                state_publications = data.get("publications", [])
                if isinstance(state_publications, dict):
                    state_publications = []
        except Exception as e:
            print(f"Erro ao ler state: {e}")

def save_state():
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump({
            "logins": state_logins,
            "channels": state_channels,
            "publications": state_publications
        }, f)

def synced_now():
    now = datetime.datetime.now()
    synced = now + datetime.timedelta(milliseconds=clock_offset_millis)
    return synced.isoformat()

def on_receive_logical_clock(received_clock):
    global logical_clock
    logical_clock = max(logical_clock, received_clock)

def before_send_logical_clock():
    global logical_clock
    logical_clock += 1
    return logical_clock

def log(msg, direction, target, msg_type, content, result=""):
    ts = synced_now()
    res_str = f" | result={result}" if result else ""
    if direction == "in":
        print(f"[{ts}] CLIENT {target} -> SERVER {SERVER_NAME} | {msg_type} | {content}{res_str} | msg_ts={msg.timestamp} | lc={msg.logical_clock} | now_lc={logical_clock}", flush=True)
    else:
        print(f"[{ts}] SERVER {SERVER_NAME} -> CLIENT {target} | {msg_type} | {content}{res_str} | msg_ts={msg.timestamp} | lc={logical_clock}", flush=True)

def handle_request(raw_msg, socket_pub):
    global client_messages_since_last_heartbeat
    
    req = message_pb2.Message()
    req.ParseFromString(raw_msg)
    
    on_receive_logical_clock(req.logical_clock)
        
    client_messages_since_last_heartbeat += 1
    if client_messages_since_last_heartbeat >= 10:
        send_heartbeat()
        client_messages_since_last_heartbeat = 0
    
    rep = message_pb2.Message()
    rep.timestamp = synced_now()
    rep.sender = SERVER_NAME
    
    client_name = req.sender
    
    if req.type == message_pb2.Message.LOGIN_REQ:
        username = req.login_req.username
        log(req, "in", client_name, "LOGIN_REQ", f"user={username}")
        
        rep.type = message_pb2.Message.LOGIN_REP
        if len(username) < 3 or len(username) > 20 or not username.replace("_", "").isalnum():
            rep.login_rep.success = False
            rep.login_rep.error_message = "Nome invalido (deve ser alfanumerico tamanho 3-20)"
            log(rep, "out", client_name, "LOGIN_REP", f"user={username}", "ERROR")
        else:
            rep.login_rep.success = True
            rep.login_rep.error_message = ""
            state_logins.append({
                "username": username,
                "timestamp": synced_now(),
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
            rep.create_rep.error_message = "Canal deve comecar com # e possuir ao menos 3 chars"
            log(rep, "out", client_name, "CREATE_CHANNEL_REP", f"channel={ch_name}", "ERROR")
        elif ch_name in state_channels:
            rep.create_rep.success = False
            rep.create_rep.error_message = "Canal ja existe."
            log(rep, "out", client_name, "CREATE_CHANNEL_REP", f"channel={ch_name}", "ERROR")
        else:
            rep.create_rep.success = True
            rep.create_rep.error_message = ""
            state_channels.append(ch_name)
            save_state()
            
            evt = message_pb2.Message()
            evt.type = message_pb2.Message.REPLICATE_CHANNEL_EVENT
            evt.timestamp = synced_now()
            evt.sender = SERVER_NAME
            evt.logical_clock = before_send_logical_clock()
            evt.replicate_event.channel_name = ch_name
            evt.replicate_event.source_server_id = SERVER_NAME
            
            socket_pub.send_multipart([b"__INTERNAL__", evt.SerializeToString()])
            
            ts_now = synced_now()
            print(f"[{ts_now}] SERVER {SERVER_NAME} created channel {ch_name} locally. Replicated with lc={evt.logical_clock}.", flush=True)
            log(rep, "out", client_name, "CREATE_CHANNEL_REP", f"channel={ch_name}", "OK")

    elif req.type == message_pb2.Message.LIST_CHANNELS_REQ:
        log(req, "in", client_name, "LIST_CHANNELS_REQ", "")
        rep.type = message_pb2.Message.LIST_CHANNELS_REP
        rep.list_rep.channels.extend(state_channels)
        channels_str = ",".join(state_channels)
        log(rep, "out", client_name, "LIST_CHANNELS_REP", f"channels=[{channels_str}]", "OK")
    
    elif req.type == message_pb2.Message.PUBLISH_MESSAGE_REQ:
        ch_name = req.pub_req.channel_name
        text = req.pub_req.text
        log(req, "in", client_name, "PUBLISH_MESSAGE_REQ", f"channel={ch_name} text={text}")
        
        rep.type = message_pb2.Message.PUBLISH_MESSAGE_REP
        if ch_name not in state_channels:
            rep.pub_rep.success = False
            rep.pub_rep.error_message = "Falha: o canal nao existe."
            log(rep, "out", client_name, "PUBLISH_MESSAGE_REP", f"channel={ch_name}", "ERROR")
        elif not text.strip():
            rep.pub_rep.success = False
            rep.pub_rep.error_message = "Falha: mensagem vazia."
            log(rep, "out", client_name, "PUBLISH_MESSAGE_REP", f"channel={ch_name}", "ERROR")
        else:
            rep.pub_rep.success = True
            rep.pub_rep.error_message = ""
            
            ts_now = synced_now()
            state_publications.append({
                "channel": ch_name,
                "sender": client_name,
                "text": text,
                "timestamp_sent": req.timestamp,
                "timestamp_persisted": ts_now,
                "server_id": SERVER_NAME
            })
            save_state()
            
            evt = message_pb2.Message()
            evt.type = message_pb2.Message.CHANNEL_MESSAGE_EVENT
            evt.timestamp = ts_now
            evt.sender = SERVER_NAME
            evt.logical_clock = before_send_logical_clock()
            evt.channel_event.channel_name = ch_name
            evt.channel_event.text = text
            evt.channel_event.sender = client_name
            
            socket_pub.send_multipart([ch_name.encode('utf-8'), evt.SerializeToString()])
            print(f"[{ts_now}] SERVER {SERVER_NAME} propagated 1 message to PUB '{ch_name}'. lc={evt.logical_clock}", flush=True)
            log(rep, "out", client_name, "PUBLISH_MESSAGE_REP", f"channel={ch_name}", "OK")

    else:
        rep.type = message_pb2.Message.UNKNOWN
        
    rep.logical_clock = before_send_logical_clock()
    return rep.SerializeToString()


def handle_replication(raw_msg):
    evt = message_pb2.Message()
    evt.ParseFromString(raw_msg)
    
    on_receive_logical_clock(evt.logical_clock)
        
    if evt.type == message_pb2.Message.REPLICATE_CHANNEL_EVENT:
        ch_name = evt.replicate_event.channel_name
        source_id = evt.replicate_event.source_server_id
        if source_id != SERVER_NAME and ch_name not in state_channels:
            state_channels.append(ch_name)
            save_state()
            ts_now = synced_now()
            print(f"[{ts_now}] SERVER {SERVER_NAME} applied replicated channel {ch_name} from {source_id} | local_lc={logical_clock}", flush=True)

def refresh_server_list():
    req = message_pb2.Message()
    req.type = message_pb2.Message.SERVER_LIST_REQ
    req.timestamp = synced_now()
    req.sender = SERVER_NAME
    req.logical_clock = before_send_logical_clock()
    
    socket_reference.send(req.SerializeToString())
    raw_rep = socket_reference.recv()
    rep = message_pb2.Message()
    rep.ParseFromString(raw_rep)
    on_receive_logical_clock(rep.logical_clock)
        
    if rep.type == message_pb2.Message.SERVER_LIST_REP:
        servers = [f"{s.name}(rank={s.rank})" for s in rep.srv_list_rep.servers]
        print(f"[{synced_now()}] LISTA DE SERVIDORES DISPONIVEIS: {servers}", flush=True)

def send_heartbeat():
    global clock_offset_millis
    
    req = message_pb2.Message()
    req.type = message_pb2.Message.HEARTBEAT_REQ
    req.timestamp = synced_now()
    req.sender = SERVER_NAME
    req.logical_clock = before_send_logical_clock()
    
    local_before = datetime.datetime.now()
    socket_reference.send(req.SerializeToString())
    raw_rep = socket_reference.recv()
    local_after = datetime.datetime.now()
    
    rep = message_pb2.Message()
    rep.ParseFromString(raw_rep)
    on_receive_logical_clock(rep.logical_clock)
        
    if rep.type == message_pb2.Message.HEARTBEAT_REP:
        ref_time_str = rep.hb_rep.reference_time
        try:
            ref_time = datetime.datetime.fromisoformat(ref_time_str)
            # Calculate simple offset assuming rtt/2 delay
            rtt = (local_after - local_before).total_seconds() * 1000.0
            server_now_estimated = ref_time + datetime.timedelta(milliseconds=rtt/2)
            offset = (server_now_estimated - local_after).total_seconds() * 1000.0
            clock_offset_millis = offset
            
            print(f"[{synced_now()}] HEARTBEAT ENVIADO. Resposta recebida. Offset atualizado para: {clock_offset_millis:.2f}ms", flush=True)
            refresh_server_list()
        except Exception as e:
            print(f"Erro ao parsear tempo de referencia: {e}")

def request_initial_rank():
    global server_rank
    
    req = message_pb2.Message()
    req.type = message_pb2.Message.SERVER_RANK_REQ
    req.timestamp = synced_now()
    req.sender = SERVER_NAME
    req.logical_clock = before_send_logical_clock()
    req.rank_req.server_name = SERVER_NAME
    
    socket_reference.send(req.SerializeToString())
    raw_rep = socket_reference.recv()
    
    rep = message_pb2.Message()
    rep.ParseFromString(raw_rep)
    on_receive_logical_clock(rep.logical_clock)

    if rep.type == message_pb2.Message.SERVER_RANK_REP:
        server_rank = rep.rank_rep.rank
        print(f"[{synced_now()}] RANK OBTIDO DO SERVICO DE REFERENCIA: {server_rank}", flush=True)

def main():
    global socket_reference
    
    load_state()
    context = zmq.Context()
    
    socket_reference = context.socket(zmq.REQ)
    socket_reference.connect(REFERENCE_URL)
    
    request_initial_rank()
    send_heartbeat()
    
    socket_rep = context.socket(zmq.REP)
    broker_url = os.getenv("BROKER_URL", "tcp://broker:5556")
    socket_rep.connect(broker_url)
    
    socket_pub = context.socket(zmq.PUB)
    pub_url = os.getenv("PUB_URL", "tcp://pubsub:5557")
    socket_pub.connect(pub_url)
    
    socket_sub = context.socket(zmq.SUB)
    sub_url = os.getenv("SUB_URL", "tcp://pubsub:5558")
    socket_sub.connect(sub_url)
    socket_sub.setsockopt_string(zmq.SUBSCRIBE, "__INTERNAL__")
    
    poller = zmq.Poller()
    poller.register(socket_rep, zmq.POLLIN)
    poller.register(socket_sub, zmq.POLLIN)
    
    print(f"[{synced_now()}] Servidor {SERVER_NAME} conectado ao broker em {broker_url}.", flush=True)
    
    while True:
        try:
            socks = dict(poller.poll())
            if socket_rep in socks:
                raw_msg = socket_rep.recv()
                reply = handle_request(raw_msg, socket_pub)
                socket_rep.send(reply)
            if socket_sub in socks:
                multipart_msg = socket_sub.recv_multipart()
                if len(multipart_msg) == 2 and multipart_msg[0] == b"__INTERNAL__":
                    handle_replication(multipart_msg[1])
                elif len(multipart_msg) == 1:
                    handle_replication(multipart_msg[0])
        except Exception as e:
            print(f"Erro no loop principal: {e}", flush=True)

if __name__ == "__main__":
    main()

