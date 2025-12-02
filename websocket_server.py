#!/usr/bin/env python3
import asyncio
import json
import websockets
from datetime import datetime
from pathlib import Path

# Keep track of connected clients
connected_clients = set()

async def handler(websocket):
    """
    Handle incoming websocket connections.
    """
    # Add new client
    connected_clients.add(websocket)
    print(f"-> CLIENT CONNECTED. Total clients: {len(connected_clients)}")
    
    try:
        # Listen for messages from the client (e.g., from the TUI)
        async for message in websocket:
            print(f"   [Message Received] Length: {len(message)}")
            # When a message is received, broadcast it to all other clients
            clients_to_send = [client for client in connected_clients if client != websocket]
            if clients_to_send:
                print(f"   [Broadcasting] Sending to {len(clients_to_send)} client(s)...")
                for client in clients_to_send:
                    try:
                        await client.send(message)
                    except websockets.exceptions.ConnectionClosed:
                        # Handle case where client disconnects during broadcast
                        pass
            else:
                print("   [No other clients to broadcast to]")

    except websockets.exceptions.ConnectionClosedError as e:
        print(f"-> CLIENT DISCONNECTED (unexpectedly). Reason: {e}")
    except Exception as e:
        print(f"[!!!] UNEXPECTED ERROR in handler: {e}")
    finally:
        # Remove client on disconnect
        if websocket in connected_clients:
            connected_clients.remove(websocket)
        print(f"-> CLIENT SESSION ENDED. Total clients: {len(connected_clients)}")

async def main():
    """
    Start the websocket server.
    """
    host = "127.0.0.1"

    # Read port from config file, fallback to 8765
    port = 8765
    config_file = Path(__file__).parent / "ws_config.json"
    if config_file.exists():
        try:
            with open(config_file) as f:
                config = json.load(f)
                port = config.get("port", 8765)
        except Exception as e:
            print(f"Warning: Could not read ws_config.json: {e}")
            print("Using default port 8765")

    print("="*50)
    print("Attempting to start WebSocket server...")
    print(f"  Host: {host}")
    print(f"  Port: {port}")
    print("="*50)

    try:
        async with websockets.serve(handler, host, port) as server:
            print("\n[SUCCESS] Server is running and listening for connections.")
            print("You can now connect your browser and the TUI.")
            await asyncio.Future()  # run forever
    except OSError as e:
        print(f"\n[!!!] FAILED TO START SERVER: {e}")
        print("This might mean another process is already using this port.")
        print("Please check for other running instances of this server or other applications on this port.")
    except Exception as e:
        print(f"\n[!!!] AN UNEXPECTED ERROR OCCURRED: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Server shutting down.")
