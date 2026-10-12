"""Env-based configuration. No secrets in code — everything comes from env vars."""
import os


def _load_dotenv(path=".env"):
    """Tiny stdlib .env loader so the app runs even without python-dotenv."""
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except FileNotFoundError:
        pass


_load_dotenv()

NEBIUS_API_KEY = os.environ.get("NEBIUS_API_KEY", "")
# Confirm the exact value in the Token Factory dashboard; studio.nebius.com is legacy.
NEBIUS_BASE_URL = os.environ.get(
    "NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1"
)
# Model IDs on Nebius are namespaced & case-sensitive — copy the exact string
# from the Token Factory console / playground.
NEMOTRON_MODEL = os.environ.get(
    "NEMOTRON_MODEL", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"
)
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")
TAVILY_URL = "https://api.tavily.com/search"
MEMORY_DB = os.environ.get("MEMORY_DB", "data/memory.db")
PORT = int(os.environ.get("PORT", "8000"))
PROVIDER = os.environ.get("PROVIDER", "auto")  # auto | nebius | mock


def active_provider() -> str:
    if PROVIDER == "mock":
        return "mock"
    if PROVIDER == "nebius":
        return "nebius"
    # auto: use Nebius when a key is present, otherwise offline mock
    return "nebius" if NEBIUS_API_KEY else "mock"
