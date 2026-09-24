"""TigerGraph MCP client. Per the HHGOA brief: 'Use TigerGraph MCP to expose graph
capabilities and data to the agent.' This runs a persistent tigergraph-mcp stdio session
on a background thread and exposes the same synchronous interface as GraphClient
(agent/data_access.py), so Investigator and memory.py work unchanged against either
backend. Every read (card_txns, device_txns, similar_cases, ...) goes through
tigergraph__run_installed_query; every write (case memory) goes through
tigergraph__add_node / tigergraph__add_edge. Both call the identical pyTigerGraph
runInstalledQuery / upsertVertex / upsertEdge methods the direct client uses.

The whole session lifetime (connect, every call, disconnect) runs inside ONE coroutine
on a dedicated event-loop thread, because an MCP ClientSession's async context manager
must be entered and exited from the same asyncio task -- scheduling __aenter__ and
__aexit__ as separate run_coroutine_threadsafe calls (separate tasks) raises
'cancel scope in a different task than it was entered in'. Requests cross the thread
boundary through an asyncio.Queue fed via call_soon_threadsafe."""
from __future__ import annotations
import asyncio
import json
import threading
from concurrent.futures import Future

from .data_access import GraphClient

_STOP = object()


class MCPGraphClient(GraphClient):
    def __init__(self, host="http://127.0.0.1", rest=9000, gs=14240, user="tigergraph", pw="tigergraph", graphname="FraudGraph"):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import get_default_environment, stdio_client
        self.calls = 0
        self.log: list[str] = []
        self._cache: dict = {}
        self.graphname = graphname
        env = {"TG_HOST": host, "TG_USERNAME": user, "TG_PASSWORD": pw,
               "TG_GRAPHNAME": graphname, "TG_RESTPP_PORT": str(rest), "TG_GS_PORT": str(gs)}

        self._loop = asyncio.new_event_loop()
        self._queue: asyncio.Queue | None = None
        ready: Future = Future()
        self._thread = threading.Thread(target=self._run_loop, args=(env, ready), daemon=True)
        self._thread.start()
        ready.result(timeout=60)  # blocks until the session is initialized (or raises)

    def _run_loop(self, env: dict, ready: Future):
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._worker(env, ready))

    async def _worker(self, env: dict, ready: Future):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import get_default_environment, stdio_client
        params = StdioServerParameters(command="tigergraph-mcp", args=[], env={**get_default_environment(), **env})
        self._queue = asyncio.Queue()
        try:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    ready.set_result(True)
                    while True:
                        item = await self._queue.get()
                        if item is _STOP:
                            break
                        fut, name, kwargs = item
                        try:
                            result = await session.call_tool(name, arguments=kwargs)
                            fut.set_result(result)
                        except Exception as e:
                            fut.set_exception(e)
        except Exception as e:
            if not ready.done():
                ready.set_exception(e)

    def _call_tool(self, name: str, **kwargs):
        fut: Future = Future()

        async def enqueue():
            await self._queue.put((fut, name, kwargs))

        asyncio.run_coroutine_threadsafe(enqueue(), self._loop).result(timeout=30)
        result = fut.result(timeout=120)
        text = "".join(getattr(c, "text", "") for c in result.content).strip()
        if text.startswith("```"):
            # Tool replies are markdown: a fenced JSON block first, then a duplicate
            # human-readable rendering. Take only the first fenced block.
            body = text.split("\n", 1)[1] if "\n" in text else ""
            text = body[:body.index("```")] if "```" in body else body
        env = json.loads(text) if text else {}
        if not env.get("success", True):
            raise RuntimeError(f"tigergraph-mcp {name} failed: {env.get('error', env)}")
        return env.get("data")

    def close(self):
        try:
            asyncio.run_coroutine_threadsafe(self._queue.put(_STOP), self._loop).result(timeout=10)
        except Exception:
            pass
        self._thread.join(timeout=10)
        self._loop.call_soon_threadsafe(self._loop.stop)

    # ---- overrides: route through MCP instead of a direct pyTigerGraph connection ----
    def q(self, name: str, **params):
        key = (name, tuple(sorted((k, tuple(v) if isinstance(v, list) else v) for k, v in params.items())))
        if key in self._cache:
            return self._cache[key]
        self.calls += 1
        fmt = lambda v: v[0] if isinstance(v, tuple) else ("<vector>" if isinstance(v, list) else v)
        self.log.append("mcp:%s(%s)" % (name, ", ".join("%s=%s" % (k, fmt(v)) for k, v in params.items())))
        wire = {k: (v[0] if isinstance(v, tuple) else v) for k, v in params.items()}
        data = self._call_tool("tigergraph__run_installed_query", query_name=name, params=wire, graph_name=self.graphname)
        r = data["result"]
        self._cache[key] = r
        return r

    def get_vertex(self, vtype: str, vid):
        try:
            data = self._call_tool("tigergraph__get_node", vertex_type=vtype, vertex_id=str(vid), graph_name=self.graphname)
            return data or None
        except Exception:
            return None

    def upsert_vertex(self, vtype: str, vid, attrs: dict):
        return self._call_tool("tigergraph__add_node", vertex_type=vtype, vertex_id=str(vid), attributes=attrs, graph_name=self.graphname)

    def upsert_edge(self, from_type: str, from_id, etype: str, to_type: str, to_id, attrs: dict | None = None):
        return self._call_tool("tigergraph__add_edge", source_vertex_type=from_type, source_vertex_id=str(from_id),
                                edge_type=etype, target_vertex_type=to_type, target_vertex_id=str(to_id),
                                attributes=attrs or {}, graph_name=self.graphname)

    def vertex_counts(self) -> dict:
        data = self._call_tool("tigergraph__get_vertex_count", graph_name=self.graphname)
        return data["counts_by_type"]
