"""Read the bank's tool API (OpenAPI) into plain tool descriptions. Nothing is typed by hand."""
import json, urllib.parse


def _resolve(api, node):
    while isinstance(node, dict) and "$ref" in node:
        ref = node["$ref"]
        cur = api
        for part in ref.lstrip("#/").split("/"):
            cur = cur.get(part, {})
        node = cur
    return node if isinstance(node, dict) else {}


def _props(api, schema):
    schema = _resolve(api, schema)
    out = {}
    for name, p in (schema.get("properties") or {}).items():
        p = _resolve(api, p)
        item = {"type": p.get("type") or "string", "enum": p.get("enum") or [], "description": p.get("description") or "",
                "required": name in (schema.get("required") or [])}
        if p.get("type") == "array":
            item["items"] = _props(api, p.get("items") or {})
        elif p.get("properties"):
            item["type"] = "object"
            item["properties"] = _props(api, p)
        out[name] = item
    return out


def load(path, base=None):
    """base, when given (the mock's address), replaces the server address of the API file."""
    api = json.load(open(path))
    servers = api.get("servers") or [{}]
    srv = (servers[0].get("url") or "").rstrip("/")
    if base:
        # the mock answers on the same paths as the API: keep the server address's own path (e.g. /v1) under it
        spath = urllib.parse.urlparse(srv).path.rstrip("/") if "://" in srv else srv
        base = base.rstrip("/")
        base = base if not spath or base.endswith(spath) else base + spath
    else:
        base = srv
    tools = {}
    for path_, ops in (api.get("paths") or {}).items():
        for method, op in ops.items():
            if method.lower() not in ("post", "get", "put", "patch"):
                continue
            name = op.get("operationId") or path_.strip("/").replace("/", "_")
            body = (((op.get("requestBody") or {}).get("content") or {}).get("application/json") or {}).get("schema") or {}
            resp = ((((op.get("responses") or {}).get("200") or {}).get("content") or {}).get("application/json") or {}).get("schema") or {}
            params = []
            for prm in (op.get("parameters") or []) + (ops.get("parameters") or [] if isinstance(ops.get("parameters"), list) else []):
                prm = _resolve(api, prm)
                if prm.get("in") in ("path", "query") and prm.get("name"):
                    sch = _resolve(api, prm.get("schema") or {})
                    params.append({"name": prm["name"], "in": prm["in"], "required": bool(prm.get("required")), "type": sch.get("type") or "string",
                                   "enum": sch.get("enum") or [], "description": prm.get("description") or ""})
            tools[name] = {"name": name, "url": base + path_, "method": method.upper(), "summary": op.get("summary") or op.get("description") or "",
                           "fields": _props(api, body), "response": _props(api, resp), "params": params}
    return api, tools
