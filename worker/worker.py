import socket
import time
import uuid
import redis
import psycopg2 # Need this for retry exceptions later
from celery import Celery
from shared.db import insert_server_info, insert_server_batch, initialize_pool # Added batch insert and pool init
from shared.mc_ping import ping_server  # Unified Minecraft ping
from shared.config import REDIS_URL, TARGET_PORT, CONNECT_TIMEOUT, MC_PING_TIMEOUT # Import config vars
from shared.logger import logger # Import logger

# Initialize Celery and Redis
app = Celery("worker", broker=REDIS_URL)
redis_client = redis.Redis.from_url(REDIS_URL)

# Initialize DB Pool (call once at startup)
try:
    initialize_pool()
except Exception as e:
    # Log the error, but allow the worker process to continue.
    # Task failures due to DB issues will be handled by Celery retries.
    logger.critical(f"Worker failed to initialize DB pool during startup: {e}", exc_info=True)

# Configuration is now imported from shared.config
# target_port = 25565
# timeout = 0.3
# chunk_size = 20  # used by controller too

def is_port_open(ip, port=TARGET_PORT): # Use imported TARGET_PORT
    try:
        # Use the short CONNECT_TIMEOUT for the initial check
        with socket.create_connection((ip, port), timeout=CONNECT_TIMEOUT):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False # Explicitly handle common non-open errors
    except Exception as e:
        logger.warning(f"Unexpected error in is_port_open for {ip}:{port} - {e}")
        return False

@app.task(name="worker.worker.scan_ip_batch",
          bind=True, # Needed for self.retry
          autoretry_for=(socket.timeout, psycopg2.OperationalError), # Example exceptions for retry
          retry_kwargs={'max_retries': 3},
          retry_backoff=True,
          retry_backoff_max=60, # seconds
          acks_late=True) # Acknowledge task *after* it runs successfully
def scan_ip_batch(self, ip_list, cidr_ref=None): # Added cidr_ref placeholder
    hostname = socket.gethostname()
    total_found_in_batch = 0
    db_batch_data = [] # List to hold data for batch insert
    timestamp = int(time.time()) # Use same timestamp for batch if needed

    logger.info(f"[{hostname}] Received batch of {len(ip_list)} IPs. CIDR Ref: {cidr_ref}") # Log task entry

    for ip in ip_list:
        logger.debug(f"[{hostname}] Checking IP: {ip}") # Log each IP
        # Use short timeout for initial check
        port_is_open = is_port_open(ip, port=TARGET_PORT)
        if not port_is_open:
            logger.debug(f"[{hostname}] Port CLOSED for {ip}")
            continue # Skip to next IP

        logger.info(f"[{hostname}] Port OPEN for {ip}. Attempting ping...") # Log open port

        ping_result = None
        try:
            # Use the LONGER MC_PING_TIMEOUT for the actual Minecraft ping
            ping_result = ping_server(ip, port=TARGET_PORT, timeout=MC_PING_TIMEOUT)
        except Exception as ping_exc:
            logger.warning(f"[{hostname}] Ping EXCEPTION for {ip}: {ping_exc}", exc_info=False)

        if ping_result:
            # Get the actual result (careful with variable names if copying)
            # Assuming ping_result is the dictionary we expect
            motd = ping_result.get("motd") or ""
            players_online = ping_result.get("players_online") or 0
            players_max = ping_result.get("players_max") or 0
            version = ping_result.get("version") or "unknown"
            # Ensure player_names is a list of strings for DB array
            player_names = ping_result.get("player_names") or []
            player_names_str = [str(name) for name in player_names]

            logger.info(f"[{hostname}] [+] SUCCESS Ping: {ip} - MOTD:'{motd}' Players:{players_online}/{players_max} V:{version}") # Log success details
            redis_client.sadd("found_servers", ip) # Keep Redis set for dashboard quick view
            total_found_in_batch += 1

            # Append data for batch insert
            db_batch_data.append((
                ip,
                motd,
                players_online,
                players_max,
                player_names_str, # Use list of strings
                version,
                cidr_ref
            ))

        else:
            # Logged if port was open but ping failed/timed out/returned None
            logger.info(f"[{hostname}] [-] FAILED Ping for {ip} (port was open)") # Log failure
            # Append data for offline server batch insert
            db_batch_data.append((
                ip,
                "[OFFLINE]",
                0,
                0,
                [], # Empty list
                "unknown",
                cidr_ref
            ))

    # --- Batch Insert to Database ---
    if db_batch_data:
        logger.info(f"[{hostname}] Attempting DB batch insert for {len(db_batch_data)} records...") # Log before insert
        try:
            inserted_count = insert_server_batch(db_batch_data)
            logger.info(f"[{hostname}] DB Batch Insert: {inserted_count}/{len(db_batch_data)} records.")
        except (psycopg2.OperationalError) as db_exc: # Catch retryable DB errors here
            logger.warning(f"[{hostname}] DB Operational Error during batch insert: {db_exc}. Task will retry.")
            raise self.retry(exc=db_exc) # Trigger Celery retry
        except Exception as db_exc:
            logger.error(f"[{hostname}] Unhandled DB Error during batch insert: {db_exc}", exc_info=True)
            # Decide if non-retryable DB errors should fail the task or just be logged
    else:
        logger.info(f"[{hostname}] No data to insert into DB for this batch.") # Log if nothing to insert

    # --- Redis Stats --- (Update stats even if DB insert has issues?)
    try:
        pipe = redis_client.pipeline()
        pipe.incrby("stats:total_scanned", len(ip_list))
        # Use the count of servers actually found (responded to ping)
        pipe.incrby("stats:total_found", total_found_in_batch)
        pipe.zadd("stats:scans", {f"{timestamp}:{len(ip_list)}:{uuid.uuid4()}": timestamp})
        pipe.setex(f"stats:worker:{hostname}", 90, "online") # Heartbeat
        pipe.execute()
        logger.info(f"[{hostname}] Updated Redis stats: Scanned={len(ip_list)}, Found={total_found_in_batch}")
    except Exception as redis_exc:
        logger.error(f"[{hostname}] Failed to update Redis stats: {redis_exc}", exc_info=True)

    logger.info(f"[{hostname}] Finished batch processing.") # Log end of task
