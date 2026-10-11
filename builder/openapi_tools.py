"""Read the bank's tool API (OpenAPI) into plain tool descriptions. Nothing is typed by hand."""
import json


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
        out[name] = item
    return out


def load(path, base=None):
    """base, when given (the mock's address), replaces the server address of the API file."""
    api = json.load(open(path))
    servers = api.get("servers") or [{}]
    base = (base or servers[0].get("url") or "").rstrip("/")
    tools = {}
    for path_, ops in (api.get("paths") or {}).items():
        for method, op in ops.items():
            if method.lower() not in ("post", "get", "put", "patch"):
                continue
            name = op.get("operationId") or path_.strip("/").replace("/", "_")
            body = (((op.get("requestBody") or {}).get("content") or {}).get("application/json") or {}).get("schema") or {}
            resp = ((((op.get("responses") or {}).get("200") or {}).get("content") or {}).get("application/json") or {}).get("schema") or {}
            tools[name] = {"name": name, "url": base + path_, "method": method.upper(), "summary": op.get("summary") or "",
                           "fields": _props(api, body), "response": _props(api, resp)}
    return api, tools
