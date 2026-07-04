import socket

HOST, PORT = "0.0.0.0", 3200


def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(5)
    print(f"Listening on {HOST}:{PORT}")
    while True:
        conn, addr = srv.accept()
        with conn:
            print(f"Connection from {addr}")
            try:
                conn.settimeout(2)
                conn.recv(1024)
            except socket.timeout:
                pass
            # Trivial placeholder HL7-style ACK banner
            conn.sendall(b"MSH|^~\\&|PhilipsIntelliVue|HL7_ACK\r\n")


if __name__ == "__main__":
    main()
