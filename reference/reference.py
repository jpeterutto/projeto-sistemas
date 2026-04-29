import zmq
import datetime
import time
import message_pb2

# ranks: dict name -> rank
server_ranks = {}
next_rank = 0

# heartbeats: dict name -> last seen time
server_heartbeats = {}

TIMEOUT_SECONDS = 30.0

# Logical clock state
logical_clock = 0

def on_receive_logical_clock(received_clock):
    global logical_clock
    logical_clock = max(logical_clock, received_clock)

def before_send_logical_clock():
    global logical_clock
    logical_clock += 1
    return logical_clock

def handle_request(raw_msg):
    global next_rank
    
    req = message_pb2.Message()
    req.ParseFromString(raw_msg)
    
    on_receive_logical_clock(req.logical_clock)
    
    rep = message_pb2.Message()
    rep.timestamp = datetime.datetime.now().isoformat()
    rep.sender = "reference"
        
    client_name = req.sender
    
    if req.type == message_pb2.Message.SERVER_RANK_REQ:
        srv_name = req.rank_req.server_name
        if srv_name not in server_ranks:
            server_ranks[srv_name] = next_rank
            next_rank += 1
            print(f"[{datetime.datetime.now().isoformat()}] REGISTRO: Novo servidor '{srv_name}' recebeu rank {server_ranks[srv_name]} | lc_msg={req.logical_clock} | log_local_agora={logical_clock}")
        else:
            print(f"[{datetime.datetime.now().isoformat()}] REGISTRO: Servidor conhecido '{srv_name}' solicitou rank (recebeu {server_ranks[srv_name]}) | lc_msg={req.logical_clock} | log_local_agora={logical_clock}")
            
        rep.type = message_pb2.Message.SERVER_RANK_REP
        rep.rank_rep.rank = server_ranks[srv_name]

    elif req.type == message_pb2.Message.HEARTBEAT_REQ:
        now_ts = datetime.datetime.now().timestamp()
        server_heartbeats[client_name] = now_ts
        print(f"[{datetime.datetime.now().isoformat()}] HEARTBEAT recebido de {client_name} | lc_msg={req.logical_clock} | log_local_agora={logical_clock}")
        
        rep.type = message_pb2.Message.HEARTBEAT_REP
        # Não devolver mais a hora no heartbeat
        # rep.hb_rep.reference_time = datetime.datetime.now().isoformat()
        
    elif req.type == message_pb2.Message.SERVER_LIST_REQ:
        print(f"[{datetime.datetime.now().isoformat()}] LIST_REQ recebido de {client_name} | lc_msg={req.logical_clock} | log_local_agora={logical_clock}")
        rep.type = message_pb2.Message.SERVER_LIST_REP
        
        now = datetime.datetime.now().timestamp()
        available_servers = []
        for srv, last_seen in list(server_heartbeats.items()):
            if now - last_seen <= TIMEOUT_SECONDS:
                available_servers.append(srv)
            else:
                # Remove expired server
                print(f"[{datetime.datetime.now().isoformat()}] TIMEOUT: Removendo {srv} da lista de disponiveis.")
                del server_heartbeats[srv]
                
        for srv in available_servers:
            info = rep.srv_list_rep.servers.add()
            info.name = srv
            info.rank = server_ranks.get(srv, -1)
            
        print(f"[{datetime.datetime.now().isoformat()}] LIST_REP enviada com {len(available_servers)} servidores disponiveis.")
        
    else:
        rep.type = message_pb2.Message.UNKNOWN
        
    rep.logical_clock = before_send_logical_clock()
    print(f"[{datetime.datetime.now().isoformat()}] REP preparada para enviar a {client_name} | lc_enviado={rep.logical_clock}")
    
    return rep.SerializeToString()


def main():
    context = zmq.Context()
    socket_rep = context.socket(zmq.REP)
    socket_rep.bind("tcp://*:5560")
    
    print("Servico de Referencia iniciado na porta 5560", flush=True)
    
    while True:
        try:
            # use poll to allow timeout cleanup even without requests, though removing on LIST_REQ is fine too.
            events = socket_rep.poll(timeout=5000)
            if events:
                raw_msg = socket_rep.recv()
                reply = handle_request(raw_msg)
                socket_rep.send(reply)
            else:
                # periodic cleanup
                now = datetime.datetime.now().timestamp()
                for srv, last_seen in list(server_heartbeats.items()):
                    if now - last_seen > TIMEOUT_SECONDS:
                        print(f"[{datetime.datetime.now().isoformat()}] TIMEOUT (Cleanup): Removendo {srv} da lista de disponiveis.")
                        del server_heartbeats[srv]
        except Exception as e:
            print(f"Erro no loop de referencia: {e}", flush=True)

if __name__ == "__main__":
    main()
