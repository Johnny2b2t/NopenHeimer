import logging
import sys
import os

# Configuration (consider making level configurable via env var)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
numeric_level = getattr(logging, LOG_LEVEL, logging.INFO)

# Create logger instance (THIS is the crucial part for the import)
# Make sure the variable is named exactly 'logger'
logger = logging.getLogger("NopenHeimerApp") # You can name the logger instance
logger.setLevel(numeric_level)

# Create handler (e.g., StreamHandler to log to console)
handler = logging.StreamHandler(sys.stdout) # Log to standard out
handler.setLevel(numeric_level)

# Create formatter and add it to the handler
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)

# Add the handler to the logger
# Check if handlers already exist to prevent duplicates if imported multiple times
if not logger.handlers:
    logger.addHandler(handler)

# Optional: Prevent log messages from propagating to the root logger
# logger.propagate = False