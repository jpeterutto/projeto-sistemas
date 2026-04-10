import zmq
import threading
import os

MODE = os.getenv("MODE", "REQ_REP")

def proxy_req_rep(context):
    frontend = context.socket(zmq.ROUTER)
    frontend.bind("tcp://0.0.0.0:5555")
    backend = context.socket(zmq.DEALER)
    backend.bind("tcp://0.0.0.0:5556")
    print(" Broker Req/Rep ativo (Clientes 5555 -> Servidores 5556)", flush=True)
    try:
        zmq.proxy(frontend, backend)
    except Exception as e:
        print(f"Erro REQ/REP proxy: {e}", flush=True)

def proxy_pub_sub(context):
    frontend = context.socket(zmq.XSUB)
    frontend.bind("tcp://0.0.0.0:5557")
    backend = context.socket(zmq.XPUB)
    backend.bind("tcp://0.0.0.0:5558")
    print(" Proxy Pub/Sub ativo (Publishers XSUB 5557 -> Subscribers XPUB 5558)", flush=True)
    try:
        zmq.proxy(frontend, backend)
    except Exception as e:
        print(f"Erro PUB/SUB proxy: {e}", flush=True)

def main():
    context = zmq.Context()
    
    if MODE == "REQ_REP":
        print("Iniciando Broker Mestre (Req/Rep)", flush=True)
        t1 = threading.Thread(target=proxy_req_rep, args=(context,), daemon=True)
        t1.start()
        t1.join()
    elif MODE == "PUB_SUB":
        print("Iniciando Proxy Dedicado (Pub/Sub)", flush=True)
        t2 = threading.Thread(target=proxy_pub_sub, args=(context,), daemon=True)
        t2.start()
        t2.join()

if __name__ == "__main__":
    main()
