import sys, socket
from ServerWorker import ServerWorker

class Server:	
	def main(self):
		try:
			SERVER_PORT = int(sys.argv[1])
		except:
			print("[Usage: Server.py Server_port]\n")
			return
		
		rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		rtspSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		rtspSocket.bind(('', SERVER_PORT))
		rtspSocket.listen(5)
		print(f"[SERVER] Listening on port {SERVER_PORT}...")
		
		try:
			while True:
				try:
					print("[SERVER] Waiting for connection...")
					client_socket, client_address = rtspSocket.accept()
					client_socket.settimeout(30.0)  # 30 second timeout
					print(f"[SERVER] Accepted connection from {client_address}")
					
					clientInfo = {
						'rtspSocket': (client_socket, client_address)
					}
					
					worker = ServerWorker(clientInfo)
					worker.run()
					
				except KeyboardInterrupt:
					print("\n[SERVER] Shutdown requested")
					break
				except Exception as e:
					print(f"[SERVER] Error: {e}")
					continue
					
		finally:
			print("[SERVER] Shutting down...")
			rtspSocket.close()
			print("[SERVER] Server stopped")

if __name__ == "__main__":
	(Server()).main()