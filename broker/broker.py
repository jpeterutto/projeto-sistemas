import zmq
import threading

def proxy_req_rep(context):
    frontend = context.socket(zmq.ROUTER)
    frontend.bind("tcp://0.0.0.0:5555")
    backend = context.socket(zmq.DEALER)
    backend.bind("tcp://0.0.0.0:5556")
    print(" Proxy REQ/REP ativo (Clientes 5555 -> Servidores 5556)")
    try:
        zmq.proxy(frontend, backend)
    except Exception as e:
        print(f"Erro REQ/REP proxy: {e}")

def proxy_pub_sub(context):
    frontend = context.socket(zmq.XSUB)
    frontend.bind("tcp://0.0.0.0:5557")
    backend = context.socket(zmq.XPUB)
    backend.bind("tcp://0.0.0.0:5558")
    print(" Proxy PUB/SUB ativo (Replicacao 5557 -> 5558)")
    try:
        zmq.proxy(frontend, backend)
    except Exception as e:
        print(f"Erro PUB/SUB proxy: {e}")

def main():
    print("Broker Proxy inicializado.")
    context = zmq.Context()
    
    t1 = threading.Thread(target=proxy_req_rep, args=(context,), daemon=True)
    t2 = threading.Thread(target=proxy_pub_sub, args=(context,), daemon=True)
    
    t1.start()
    t2.start()
    
    t1.join()
    t2.join()

if __name__ == "__main__":
    main()
