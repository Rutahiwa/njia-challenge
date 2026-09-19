import os

MOCK_URL = os.getenv("MOCK_URL", "http://localhost:9311")

# Pinned. The grader reads the model back off the run trace.
MODEL = "claude-haiku-4-5"
MAX_OUTPUT_TOKENS = 4096

MAX_TOOL_CALLS = 12
MAX_INPUT_TOKENS = 25_000

PAY_KEY = os.getenv("PAY_KEY", "pk_live_mock_9f2a41c8")

# how long we wait for more messages before treating a burst as one request
DEBOUNCE_SECONDS = 0.8

# mobile money
CHARGE_POLL_ATTEMPTS = 5
CHARGE_POLL_INTERVAL = 0.5
MAX_PAYMENT_ATTEMPTS = 3

# seat hold lifetime, seconds
HOLD_TTL = 90

RETRY_STATUSES = {429, 500, 502, 503, 504}
RETRY_ATTEMPTS = 3
RETRY_BACKOFF = 0.2

LOG_PATH = os.path.join(os.getcwd(), "logs", "agent.jsonl")
LOG_LEVEL = os.getenv("LOG_LEVEL", "info")
