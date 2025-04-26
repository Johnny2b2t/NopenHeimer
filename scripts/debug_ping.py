import sys
import os
import logging

# Ensure the script can find the shared modules
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Now import necessary components
from shared.mc_ping import ping_server
# Import timeouts and port from config
from shared.config import TARGET_PORT, CONNECT_TIMEOUT, MC_PING_TIMEOUT
# Import the specific port checking function from the worker module
from worker.worker import is_port_open
from shared.logger import logger # Use the configured logger

# --- Configuration ---
ips_to_test = [
    "172.65.255.251", "172.65.255.253", "172.65.255.254", "172.65.255.244",
    "172.65.255.245", "172.65.255.250", "172.65.255.255", "172.65.255.247",
    "172.65.255.246", "172.65.255.252", "172.65.255.248", "172.65.255.249",
    "172.65.255.199", "172.65.255.184", "172.65.255.188", "172.65.255.194",
    "172.65.255.200", "172.65.255.203", "172.65.255.196", "172.65.255.190",
    "172.65.255.189", "172.65.255.201", "172.65.255.186", "172.65.255.198",
    "172.65.255.197", "172.65.255.187", "172.65.255.191", "172.65.255.195",
    "172.65.255.193", "172.65.255.192", "172.65.255.204", "172.65.255.214",
    "172.65.255.211", "172.65.255.218", "172.65.255.206", "172.65.255.217",
    "172.65.255.219", "172.65.255.209", "172.65.255.208", "172.65.255.210",
    "172.65.255.223", "172.65.255.207", "172.65.255.216", "172.65.255.215",
    "172.65.255.213", "172.65.255.205", "172.65.255.220", "172.65.255.212",
    "172.65.255.221", "172.65.255.168", "172.65.255.164", "172.65.255.180",
    "172.65.255.183", "172.65.255.181", "172.65.255.176", "172.65.255.165",
    "172.65.255.178", "172.65.255.177", "172.65.255.170", "172.65.255.171",
    "172.65.255.169", "172.65.255.172", "172.65.255.174", "172.65.255.173",
    "172.65.255.175", "172.65.255.179", "172.65.255.167", "172.65.255.166", # Known good one
    "172.65.255.234", "172.65.255.235", "172.65.255.231", "172.65.255.242",
    "172.65.255.232", "172.65.255.236", "172.65.255.228", "172.65.255.229",
    "172.65.255.230", "172.65.255.237", "172.65.255.233", "172.65.255.239",
    "172.65.255.224", "172.65.255.227", "172.65.255.225", "172.65.255.226",
    "172.65.255.240", "172.65.255.238", "172.65.255.128", "172.65.255.129",
    "172.65.255.139", "172.65.255.133", "172.65.255.134", "172.65.255.141",
    "172.65.255.131", "172.65.255.132", "172.65.255.135", "172.65.255.142",
    "172.65.255.130", "172.65.255.136", "172.65.255.140", "172.65.255.137",
]

# --- Main Execution ---
if __name__ == "__main__":
    # Set logger level to DEBUG to see detailed ping output
    logger.setLevel(logging.DEBUG)
    # Optional: Remove other handlers if they exist to only see console output clearly
    # for handler in logger.handlers[:]: logger.removeHandler(handler)
    # stream_handler = logging.StreamHandler(sys.stdout)
    # stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    # logger.addHandler(stream_handler)

    print(f"--- Starting Debug Ping Script (Worker Logic Simulation) ---")
    print(f"Using Port: {TARGET_PORT}")
    print(f"Using Connect Timeout (Port Check): {CONNECT_TIMEOUT}s")
    print(f"Using MC Ping Timeout (MC Ping): {MC_PING_TIMEOUT}s")
    print("-" * 30)

    for ip in ips_to_test:
        print(f"\n>>> Testing IP: {ip}")

        # Step 1: Check if port is open using the short timeout
        logger.info(f"Checking port {TARGET_PORT} on {ip} with timeout {CONNECT_TIMEOUT}s...")
        port_open_result = False # Default to False
        try:
            port_open_result = is_port_open(ip=ip, port=TARGET_PORT)
            logger.info(f"Port Check Result for {ip}: {'OPEN' if port_open_result else 'CLOSED'}")
        except Exception as e:
            print(f"!!! EXCEPTION during is_port_open call for {ip}: {e}")
            logger.error(f"!!! EXCEPTION during is_port_open call for {ip}", exc_info=True)

        # Step 2: If port was open, attempt the Minecraft ping with the longer timeout
        if port_open_result:
            logger.info(f"Port OPEN. Calling ping_server for {ip}:{TARGET_PORT} with timeout {MC_PING_TIMEOUT}s")
            ping_final_result = None # Default to None
            try:
                ping_final_result = ping_server(ip=ip, port=TARGET_PORT, timeout=MC_PING_TIMEOUT)

                if ping_final_result:
                    print(f"<<< Final Result for {ip}: {ping_final_result}") # Print dictionary
                else:
                    # Mimic worker behavior: port was open, but ping failed/returned None
                    print(f"<<< Final Result for {ip}: [OFFLINE] (Ping failed/timeout after port open)")
            except Exception as e:
                # Catch any unexpected errors during the ping_server call itself
                print(f"!!! EXCEPTION during ping_server call for {ip}: {e}")
                logger.error(f"!!! EXCEPTION during ping_server call for {ip}", exc_info=True)
                print(f"<<< Final Result for {ip}: [EXCEPTION] (During ping_server)")
        else:
            # Port was closed according to is_port_open
            print(f"<<< Final Result for {ip}: [PORT CLOSED]")

        print("-" * 10)

    print("\n--- Debug Ping Script Finished ---") 