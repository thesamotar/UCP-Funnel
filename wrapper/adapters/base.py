"""RetailerAdapter — the contract every attached backend API implements.

Attaching a new API to the node (digieca, ashiyana, ...) means:
  1. subclass RetailerAdapter in wrapper/adapters/<name>.py — implement
     `search`, and the four commerce methods if the API supports them;
  2. insert one row into the Supabase `connectors` table pointing at the
     class (`adapter_path`), its `base_url`, optional `auth`, and a
     `description` the LLM router uses to decide when to route there.

Search-only backends (e.g. a listings API) are legal: leave the commerce
methods unimplemented and the cart routes return 501 for their items.
"""
import os

import httpx


class RetailerError(Exception):
    """The backend rejected or failed a native call."""


class Unsupported(RetailerError):
    """The backend does not implement this capability."""


COMMERCE_METHODS = ("cart_create", "cart_add", "place_order", "pay")


class RetailerAdapter:
    # subclasses may set a default description; the connectors row wins
    description: str = ""

    # extra structured search params this backend understands, merged into the
    # LLM translate prompt: {"field_name": "<prompt hint>"}
    intent_fields: dict[str, str] = {}

    # optional gap-fill declaration for the enhance stage:
    # {"field": attribute that may be blank, "fill_as": attribute to write,
    #  "ask": what to look up, "example": example JSON mapping}
    enhance_spec: dict | None = None

    def __init__(self, connector: dict):
        self.name = connector["name"]
        self.description = connector.get("description") or self.description
        # env override (e.g. BIGBASKET_URL) wins over the registry row — handy
        # for local ports vs deployed URLs
        self.base_url = os.environ.get(f"{self.name.upper()}_URL") or connector["base_url"]
        # auth = {"header": "X-Api-Key", "env": "DIGIECA_KEY"} — the secret
        # itself lives in the environment, never in the database
        self.headers: dict[str, str] = {}
        auth = connector.get("auth") or {}
        if auth.get("header"):
            secret = os.environ.get(auth.get("env", ""))
            if not secret:
                raise RuntimeError(
                    f"connector {self.name!r} needs auth env var {auth.get('env')!r} — not set")
            self.headers[auth["header"]] = secret

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.base_url, headers=self.headers, timeout=10)

    @property
    def capabilities(self) -> set[str]:
        caps = {"search"}
        caps.update(m for m in COMMERCE_METHODS
                    if getattr(type(self), m) is not getattr(RetailerAdapter, m))
        return caps

    @property
    def supports_commerce(self) -> bool:
        return set(COMMERCE_METHODS) <= self.capabilities

    # --- capability surface ---------------------------------------------------

    async def search(self, intent: dict) -> tuple[dict, list[dict]]:
        """Translate a routed intent into the native search call.
        Returns (native_request_sent, ucp_items)."""
        raise NotImplementedError(f"{self.name} adapter must implement search()")

    async def cart_create(self) -> str:
        raise Unsupported(f"{self.name} does not support carts")

    async def cart_add(self, cart_id: str, native_id: str, qty: int) -> dict:
        raise Unsupported(f"{self.name} does not support carts")

    async def place_order(self, cart_id: str) -> dict:
        """Returns {"order_id", "amount"}."""
        raise Unsupported(f"{self.name} does not support orders")

    async def pay(self, order_id: str) -> dict:
        """Returns {"payment_id", "status", "method"}."""
        raise Unsupported(f"{self.name} does not support payments")
