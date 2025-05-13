import socket
import threading

# Server configuration
HOST = '0.0.0.0'  # Listen on all available interfaces
PORT = 5555

# Dictionary to store client connections
clients = {}
clients_lock = threading.Lock()

def broadcast(message, exclude_client=None):
    """Send a message to all connected clients except the sender."""
    with clients_lock:
        for client_socket, client_name in clients.items():
            if client_socket != exclude_client:
                try:
                    client_socket.send(message)
                except:
                    # Remove client if we can't send to them
                    remove_client(client_socket)

def remove_client(client_socket):
    """Remove a client from the clients dictionary."""
    with clients_lock:
        if client_socket in clients:
            client_name = clients[client_socket]
            del clients[client_socket]
            print(f"Client {client_name} disconnected")
            broadcast(f"SERVER: {client_name} has left the chat\n".encode())

def handle_client(client_socket, client_address):
    """Handle communication with a single client."""
    try:
        # Get client name
        client_socket.send("Enter your name: ".encode())
        client_name = client_socket.recv(1024).decode().strip()
        
        # Register the client
        with clients_lock:
            clients[client_socket] = client_name
        
        # Welcome message
        client_socket.send(f"Welcome to the chat, {client_name}!\n".encode())
        broadcast(f"SERVER: {client_name} has joined the chat\n".encode(), client_socket)
        
        # Message loop
        while True:
            message = client_socket.recv(1024)
            if not message:
                break
                
            formatted_message = f"{client_name}: {message.decode()}"
            print(formatted_message)
            broadcast(formatted_message.encode(), client_socket)
            
    except Exception as e:
        print(f"Error handling client {client_address}: {e}")
    finally:
        remove_client(client_socket)
        client_socket.close()

def start_server():
    """Start the chat server."""
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server_socket.bind((HOST, PORT))
        server_socket.listen(5)
        print(f"Chat server started on {HOST}:{PORT}")
        
        while True:
            client_socket, client_address = server_socket.accept()
            print(f"New connection from {client_address}")
            
            # Start a new thread to handle the client
            client_thread = threading.Thread(
                target=handle_client,
                args=(client_socket, client_address)
            )
            client_thread.daemon = True
            client_thread.start()
            
    except KeyboardInterrupt:
        print("Server shutting down...")
    except Exception as e:
        print(f"Server error: {e}")
    finally:
        server_socket.close()

if __name__ == "__main__":
    start_server() 