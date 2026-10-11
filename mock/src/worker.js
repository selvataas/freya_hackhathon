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
    const result = cust ? handle(tool.role || tool.name, args, cust) : { ok: false, error: "unknown customer_id" };
    const headers = {};
    for (const [k, v] of request.headers) if (!SECRET.test(k)) headers[k] = v;
    const conv = (config.conversation_fields || []).map((f) => body[f]).find((x) => x !== undefined && x !== "")
      ?? (config.conversation_headers || []).map((h) => request.headers.get(h)).find((x) => x) ?? null;
    if (cust) {
      await env.LEDGER.get(env.LEDGER.idFromName(id)).fetch("https://ledger/append", {
        method: "POST", body: JSON.stringify({ at: new Date().toISOString(), tool: tool.name, conversation: conv, args: body, result, headers }),
      });
    }
    return json(out(tool, result));
  },
};

// response roles -> the contract's field names
function out(tool, result) {
  const names = tool.response || {};
  const o = {};
  for (const [k, v] of Object.entries(result)) o[names[k] || k] = v;
  return o;
}

const norm = (x) => String(x ?? "").trim().toLowerCase().replace(/\s+/g, " ");
let counter = 0;

function handle(role, a, cust) {
  const fields = Object.keys(cust.identity || {});
  const maxWrong = config.max_wrong_total || 3;
  switch (role) {
    case "verify_identity": {
      const field = String(a.field ?? ""), want = cust.identity[field];
      if (want === undefined) return { ok: false, error: "unknown field " + field };
      const answer = String(a.answer ?? "").trim();
      const right = norm(answer) === norm(want);
      const hint = config.hints && config.hints.day_month_swapped;
      if (!right && hint && /^\d{4}-\d{2}-\d{2}$/.test(want) && answer === want.slice(0, 5) + want.slice(8, 10) + "-" + want.slice(5, 7) && want.slice(5, 7) !== want.slice(8, 10))
        return { ok: true, verified: false, hint, wrong_answers_left: maxWrong, all_verified: false };
      // no state: all_verified when the last of the customer's questions is answered right
      return { ok: true, verified: right, wrong_answers_left: maxWrong, all_verified: right && field === fields[fields.length - 1] };
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
    if (url.pathname === "/append") {
      calls.push(await request.json());
      calls = calls.slice(-500);
      await this.storage.put("calls", calls);
      return json({ ok: true });
    }
    return json({ calls });
  }
}
