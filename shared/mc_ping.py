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
    sock = None
    try:
        logger.debug(f"[Ping Modern DEBUG {ip}:{port}] Attempting connection with timeout {timeout}s...")
        sock = socket.create_connection((ip, port), timeout=timeout)
        logger.debug(f"[Ping Modern DEBUG {ip}:{port}] Connection successful.")

        # Handshake packet
        host_bytes = ip.encode('utf-8')
        packet = bytearray()
        packet += pack_varint(0x00)                      # Packet ID
        packet += pack_varint(754)                       # Protocol version (1.20.4)
        packet += pack_varint(len(host_bytes)) + host_bytes
        packet += struct.pack('>H', port)
        packet += pack_varint(1)                         # Next state: status

        logger.debug(f"[Ping Modern DEBUG {ip}:{port}] Sending handshake packet ({len(packet)} bytes)...")
        sock.sendall(pack_varint(len(packet)) + packet)
        logger.debug(f"[Ping Modern DEBUG {ip}:{port}] Sending status request (2 bytes)...")
        sock.sendall(b'\x01\x00')
        logger.debug(f"[Ping Modern DEBUG {ip}:{port}] Packets sent. Setting read timeout to {timeout}s.")

        sock.settimeout(timeout)
        logger.debug(f"[Ping Modern DEBUG {ip}:{port}] Reading packet length...")
        packet_len = read_varint(sock)
        if packet_len is None:
            logger.debug(f"[Ping Modern DEBUG {ip}:{port}] Failed to read packet length.")
            return None
        logger.debug(f"[Ping Modern DEBUG {ip}:{port}] Packet length: {packet_len}. Reading packet ID...")
        packet_id = read_varint(sock)
        if packet_id is None:
            logger.debug(f"[Ping Modern DEBUG {ip}:{port}] Failed to read packet ID.")
            return None
        logger.debug(f"[Ping Modern DEBUG {ip}:{port}] Packet ID: {packet_id}. Reading JSON length...")
        json_len = read_varint(sock)
        if json_len is None:
            logger.debug(f"[Ping Modern DEBUG {ip}:{port}] Failed to read JSON length.")
            return None
        logger.debug(f"[Ping Modern DEBUG {ip}:{port}] JSON length: {json_len}. Reading JSON data...")

        data = b''
        while len(data) < json_len:
            chunk = sock.recv(json_len - len(data))
            if not chunk:
                logger.warning(f"[Ping Modern DEBUG {ip}:{port}] Socket closed unexpectedly while reading JSON.")
                raise socket.error("Socket closed while reading JSON data")
            data += chunk
            logger.debug(f"[Ping Modern DEBUG {ip}:{port}] Received chunk ({len(chunk)} bytes), total {len(data)}/{json_len}.")
        logger.debug(f"[Ping Modern DEBUG {ip}:{port}] Finished reading JSON data ({len(data)} bytes). Decoding...")

        result_str = data.decode("utf-8")
        logger.debug(f"[Ping Modern DEBUG {ip}:{port}] Decoding successful. Parsing JSON...")
        result = json.loads(result_str)
        logger.debug(f"[Ping Modern DEBUG {ip}:{port}] JSON parsing successful. Extracting data...")

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

        logger.debug(f"[Ping Modern DEBUG {ip}:{port}] Extracted MOTD: '{motd}'. Returning result.")

        return {
            "motd": motd,
            "players_online": players.get("online", 0),
            "players_max": players.get("max", 0),
            "version": version or "unknown",
            "player_names": player_names
        }

    except socket.timeout:
        logger.debug(f"[Ping Modern DEBUG {ip}:{port}] Socket timeout occurred after {timeout}s.")
        return None
    except Exception as e:
        logger.warning(f"[Ping Modern DEBUG {ip}:{port}] Exception: {e}", exc_info=False)
        return None
    finally:
        if sock:
            logger.debug(f"[Ping Modern DEBUG {ip}:{port}] Closing socket.")
            sock.close()

# ------------------------------------
# Legacy Ping (pre-1.7 Minecraft)
# ------------------------------------

def ping_legacy(ip: str, port: int, timeout: float):
    """Performs legacy server list ping, using the provided timeout."""
    sock = None
    try:
        logger.debug(f"[Ping Legacy DEBUG {ip}:{port}] Attempting connection with timeout {timeout}s...")
        sock = socket.create_connection((ip, port), timeout=timeout)
        logger.debug(f"[Ping Legacy DEBUG {ip}:{port}] Connection successful. Sending request (1 byte)...")
        sock.sendall(b'\xfe')
        logger.debug(f"[Ping Legacy DEBUG {ip}:{port}] Request sent. Setting read timeout to {timeout}s.")
        sock.settimeout(timeout)
        logger.debug(f"[Ping Legacy DEBUG {ip}:{port}] Receiving response...")
        response = sock.recv(1024)
        logger.debug(f"[Ping Legacy DEBUG {ip}:{port}] Received {len(response)} bytes.")
        return response
    except socket.timeout:
        logger.debug(f"[Ping Legacy DEBUG {ip}:{port}] Socket timeout occurred after {timeout}s.")
        return None
    except Exception as e:
        logger.warning(f"[Ping Legacy DEBUG {ip}:{port}] Exception: {e}", exc_info=False)
        return None
    finally:
        if sock:
            logger.debug(f"[Ping Legacy DEBUG {ip}:{port}] Closing socket.")
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
