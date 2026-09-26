import os

# config.py requires these at import time; main.py imports config. Placeholder values only —
# nothing in the test suite talks to a real Hydra.
os.environ.setdefault("PEER_CLIENT_ID", "test-peer-client")
os.environ.setdefault("PEER_CLIENT_SECRET", "test-peer-secret")
