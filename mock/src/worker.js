// The mock of the bank's services. Generic: data/config.json maps each operation (its path) to a role and names its
// request and response fields; data/customers.json holds the test customers.
//
// Like the practice bank it accepts every record and only answers in the contract's form: no business rule is kept
// (no one-promise limit, no closed call, no wrong-answer lock), and every answer depends only on the request and the
// customer's data, so conversations with the same customer at the same time cannot disturb each other. An identity
// answer is compared with the customer's data. Every call is appended to the customer's ledger (one Durable Object per
// customer), tagged with a conversation id when the request carries one (config.conversation_fields, or a header
// named in config.conversation_headers); the request headers are kept too, without any credential.
//
//   POST <path of an operation>   the bank's services, as the contract names them
//   GET  /ledger/<customer_id>    the customer's last calls, newest last
//   GET  /health                  {ok: true, tools: [...], customers: n}
import config from "../data/config.json";
import customers from "../data/customers.json";

const CUSTOMERS = Object.fromEntries(customers.map((c) => [String(c.customer_id), c]));
const ROUTES = Object.fromEntries(Object.entries(config.tools).map(([name, t]) => [t.path.replace(/\/+$/, ""), { name, ...t }]));
const SECRET = /authorization|cookie|key|token|secret/i;

const json = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "");
    if (path === "/health") return json({ ok: true, tools: Object.keys(config.tools), customers: customers.length });
    if (request.method === "GET" && path.startsWith("/ledger/")) {
      const id = decodeURIComponent(path.slice("/ledger/".length));
      return env.LEDGER.get(env.LEDGER.idFromName(id)).fetch("https://ledger/read");
    }
    const tool = ROUTES[path];
    if (!tool) return json({ ok: false, error: "unknown operation " + path }, 404);
    let body = {};
    try { body = await request.json(); } catch (e) { body = {}; }
    const args = {};
    for (const [role, field] of Object.entries(tool.fields || {})) if (body[field] !== undefined) args[role] = body[field];
    const id = String(args.customer_id ?? "");
    const cust = CUSTOMERS[id];
    const headers = {};
    for (const [k, v] of request.headers) if (!SECRET.test(k)) headers[k] = v;
    const conv = conversationOf(request, body);
    const role = tool.role || tool.name;
    let result;
    if (!cust) result = { ok: false, error: "unknown customer_id" };
    else {
      // the customer's Durable Object appends the call to the ledger; for an identity answer it also keeps what this
      // conversation has verified, so that all_verified and wrong_answers_left are right for this conversation only
      const r = await env.LEDGER.get(env.LEDGER.idFromName(id)).fetch("https://ledger/call", {
        method: "POST", body: JSON.stringify({ at: new Date().toISOString(), tool: tool.name, role, conversation: conv, args, raw: body, headers }),
      });
      result = await r.json();
    }
    return json(out(tool, result));
  },
};

// the conversation a request belongs to: a field or a header the contract names, else the platform's sentry-trace id
function conversationOf(request, body) {
  for (const f of config.conversation_fields || []) if (body[f] !== undefined && body[f] !== "") return String(body[f]);
  for (const h of config.conversation_headers || []) { const v = request.headers.get(h); if (v) return v; }
  const st = request.headers.get("sentry-trace");
  return st ? "trace:" + st.split("-")[0] : null;
}

// response roles -> the contract's field names
function out(tool, result) {
  const names = tool.response || {};
  const o = {};
  for (const [k, v] of Object.entries(result)) o[names[k] || k] = v;
  return o;
}

const norm = (x) => String(x ?? "").trim().toLowerCase().replace(/\s+/g, " ");
let counter = 0;

// conv: this conversation's {verified: [fields], wrong: n}, or null when the request names no conversation (then
// all_verified stays false and wrong_answers_left at the limit: an agent counts for itself)
function handle(role, a, cust, conv) {
  const fields = Object.keys(cust.identity || {});
  const maxWrong = config.max_wrong_total || 3;
  switch (role) {
    case "verify_identity": {
      const field = String(a.field ?? ""), want = cust.identity[field];
      if (want === undefined) return { ok: false, error: "unknown field " + field };
      const answer = String(a.answer ?? "").trim();
      const right = norm(answer) === norm(want);
      const left = () => (conv ? Math.max(0, maxWrong - conv.wrong) : maxWrong);
      const hint = config.hints && config.hints.day_month_swapped;
      if (!right && hint && /^\d{4}-\d{2}-\d{2}$/.test(want) && answer === want.slice(0, 5) + want.slice(8, 10) + "-" + want.slice(5, 7) && want.slice(5, 7) !== want.slice(8, 10))
        return { ok: true, verified: false, hint, wrong_answers_left: left(), all_verified: false };
      if (conv) { if (right) { if (!conv.verified.includes(field)) conv.verified.push(field); } else conv.wrong += 1; }
      return { ok: true, verified: right, wrong_answers_left: left(), all_verified: !!conv && fields.every((f) => conv.verified.includes(f)) };
    }
    case "get_account":
      return { ok: true, products: cust.products };
    case "create_promise":
      counter += 1;
      return { ok: true, promise_id: "pr_" + Date.now().toString(36) + "_" + counter };
    default:
      return { ok: true };
  }
}

export class Ledger {
  constructor(state) { this.storage = state.storage; }

  async fetch(request) {
    const url = new URL(request.url);
    let calls = (await this.storage.get("calls")) || [];
    if (url.pathname === "/call") {
      const c = await request.json();
      const convs = (await this.storage.get("conversations")) || {};
      const conv = c.conversation ? (convs[c.conversation] ||= { verified: [], wrong: 0, started: c.at }) : null;
      const result = handle(c.role, c.args, CUSTOMERS[String(c.args.customer_id)], conv);
      calls.push({ at: c.at, tool: c.tool, conversation: c.conversation, args: c.raw, result, headers: c.headers });
      calls = calls.slice(-500);
      const keep = Object.entries(convs).sort((x, y) => String(y[1].started).localeCompare(String(x[1].started))).slice(0, 200);
      await this.storage.put({ calls, conversations: Object.fromEntries(keep) });
      return json(result);
    }
    return json({ calls });
  }
}
