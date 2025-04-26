import socket
import struct
import json
import re
from shared.logger import logger

# Config - Remove module-level defaults, use passed args or config
# DEFAULT_PORT = 25565
# TIMEOUT = 0.4

# Regex to strip Minecraft color/formatting codes (e.g. §a, §l)
STRIP_FORMATTING = re.compile(r'§.')

def pack_varint(value):
    out = bytearray()
    while True:
        temp = value & 0b01111111
        value >>= 7
        if value:
            temp |= 0b10000000
        out.append(temp)
        if not value:
            break
    return out

def read_varint(sock):
    num = 0
    for i in range(5):
        byte = sock.recv(1)
        if not byte:
            return None
        byte_val = byte[0]
        num |= (byte_val & 0x7F) << (7 * i)
        if not (byte_val & 0x80):
            break
    return num

def sanitize_motd(motd):
    if not motd:
        return None
    motd = STRIP_FORMATTING.sub('', motd).strip()
    return motd if motd else None

def ping_modern(ip: str, port: int, timeout: float):
    """Performs modern server list ping, using the provided timeout."""
    sock = None # Define sock outside try for finally block
    try:
        # Establish connection with the specified timeout
        sock = socket.create_connection((ip, port), timeout=timeout)

        # Handshake packet
        host_bytes = ip.encode('utf-8')
        packet = bytearray()
        packet += pack_varint(0x00)                      # Packet ID
        packet += pack_varint(754)                       # Protocol version (1.20.4)
        packet += pack_varint(len(host_bytes)) + host_bytes
        packet += struct.pack('>H', port)
        packet += pack_varint(1)                         # Next state: status

        # Send handshake and status request
        sock.sendall(pack_varint(len(packet)) + packet)
        sock.sendall(b'\x01\x00')

        # Read response length and JSON data (read_varint needs the socket)
        # Set socket read timeout as well to avoid blocking indefinitely on recv
        sock.settimeout(timeout)
        packet_len = read_varint(sock)
        if packet_len is None: return None # Handle potential read error
        packet_id = read_varint(sock)
        if packet_id is None: return None # Handle potential read error
        json_len = read_varint(sock)
        if json_len is None: return None

        data = b''
        while len(data) < json_len:
            chunk = sock.recv(json_len - len(data))
            if not chunk: # Socket closed prematurely
                raise socket.error("Socket closed while reading JSON data")
            data += chunk

        # Decode and parse JSON result
        result = json.loads(data.decode("utf-8"))

        # Parse result
        description = result.get("description", {})
        if isinstance(description, dict):
            motd = description.get("text", "")
        else:
            motd = str(description)
        motd = sanitize_motd(motd)

        players = result.get("players", {})
        version = result.get("version", {}).get("name", "unknown")

        sample = players.get("sample", [])
        player_names = [p.get("name") for p in sample if isinstance(p.get("name"), str)]
        if len(player_names) > 20:
            player_names = player_names[:20]

        return {
            "motd": motd,
            "players_online": players.get("online", 0),
            "players_max": players.get("max", 0),
            "version": version or "unknown",
            "player_names": player_names
        }

    except socket.timeout:
        logger.debug(f"[Ping Modern] Timeout for {ip}:{port} after {timeout}s")
        return None
    except Exception as e:
        # Log other exceptions, but maybe not full trace unless debugging specific issues
        logger.warning(f"[Ping Modern] Error for {ip}:{port}: {e}", exc_info=False)
        return None
    finally:
        if sock:
            sock.close()

# ------------------------------------
# Legacy Ping (pre-1.7 Minecraft)
# ------------------------------------

def ping_legacy(ip: str, port: int, timeout: float):
    """Performs legacy server list ping, using the provided timeout."""
    sock = None # Define sock outside try for finally block
    try:
        # Establish connection with the specified timeout
        sock = socket.create_connection((ip, port), timeout=timeout)
        sock.sendall(b'\xfe')
        # Set read timeout
        sock.settimeout(timeout)
        response = sock.recv(1024)
        return response
    except socket.timeout:
        logger.debug(f"[Ping Legacy] Timeout for {ip}:{port} after {timeout}s")
        return None
    except Exception as e:
        logger.warning(f"[Ping Legacy] Error for {ip}:{port}: {e}", exc_info=False)
        return None
    finally:
        if sock:
            sock.close()

def parse_legacy_ping(response):
    try:
        data = response.decode("utf-16be")[3:].split("§")
        if len(data) >= 5:
            motd = sanitize_motd(data[0])
            return {
                "motd": motd,
                "players_online": int(data[1]),
                "players_max": int(data[2]),
                "version": data[3],
                "player_names": []  # Legacy doesn't return sample list
            }
    except Exception as e:
        logger.warning(f"[Ping Legacy] Parse failed: {e}")
    return None

# ------------------------------------
# Unified Ping Entry Point
# ------------------------------------

def ping_server(ip: str, port: int, timeout: float):
    """Attempt to ping server using modern protocol, fallback to legacy, using the provided timeout."""
    # Try modern ping first with the specified timeout
    result = ping_modern(ip, port=port, timeout=timeout)
    if result:
        return result

    # If modern failed, try legacy ping with the same timeout
    legacy_response = ping_legacy(ip, port=port, timeout=timeout)
    if legacy_response:
        return parse_legacy_ping(legacy_response)

    # If both failed, return None
    return None
