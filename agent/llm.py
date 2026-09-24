"""LLM + embedding access through OmniRoute (OpenAI-compatible), with Ollama Cloud as fallback."""
from __future__ import annotations
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
load_dotenv()
OMNI = os.environ.get("OMNIROUTE_BASE_URL", "http://127.0.0.1:20128").rstrip("/")
OMNI_KEY = os.environ.get("OMNIROUTE_API_KEY", "")
OLLAMA = os.environ.get("OLLAMA_BASE_URL", "https://ollama.com/v1").rstrip("/")
OLLAMA_KEYS = [v for k, v in sorted(os.environ.items()) if k.startswith("OLLAMA_API_KEY") and v]
EMBED_MODEL = "mistral/mistral-embed"  # 1024-d
CHAT_MODEL = os.environ.get("CHAT_MODEL", "auto/best-fast")


class Usage:
    tokens = 0
    calls = 0


def embed(texts: list[str]) -> list[list[float]]:
    out = []
    for i in range(0, len(texts), 32):
        for attempt in range(4):
            try:
                r = httpx.post(f"{OMNI}/v1/embeddings", headers={"Authorization": f"Bearer {OMNI_KEY}"},
                               json={"model": EMBED_MODEL, "input": [t[:6000] for t in texts[i:i + 32]]}, timeout=120)
                r.raise_for_status()
                out += [d["embedding"] for d in r.json()["data"]]
                break
            except Exception:
                if attempt == 3: raise
                time.sleep(2 * (attempt + 1))
    return out


def chat(messages: list[dict], model: str | None = None, max_tokens: int = 900, temperature: float = 0.2, json_mode: bool = False) -> str:
    body = {"model": model or CHAT_MODEL, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
    last = None
    for base, key, m in [(OMNI, OMNI_KEY, body["model"])] + [(OLLAMA, k, "gpt-oss:20b") for k in OLLAMA_KEYS[:2]]:
        try:
            r = httpx.post(f"{base}/v1/chat/completions" if base == OMNI else f"{base}/chat/completions",
                           headers={"Authorization": f"Bearer {key}"}, json={**body, "model": m}, timeout=120)
            r.raise_for_status()
            j = r.json()
            Usage.calls += 1
            Usage.tokens += j.get("usage", {}).get("total_tokens", 0)
            return j["choices"][0]["message"]["content"] or ""
        except Exception as e:
            last = e
    raise RuntimeError(f"all LLM endpoints failed: {last}")
