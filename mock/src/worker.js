// The mock of the bank's services. Generic: data/config.json maps each operation (its path) to a role and names its
// request and response fields; data/customers.json holds the test customers. One Durable Object per customer keeps
// that customer's ledger. A call that was closed, or idle for config.new_call_after_idle_minutes, starts a new one.
//
//   POST <path of an operation>   the bank's services, as the contract names them
//   GET  /ledger/<customer_id>    every call and its result, the current call and the earlier ones
//   GET  /health                  {ok: true, tools: [...], customers: n}
import config from "../data/config.json";
import customers from "../data/customers.json";

const CUSTOMERS = Object.fromEntries(customers.map((c) => [String(c.customer_id), c]));
const ROUTES = Object.fromEntries(Object.entries(config.tools).map(([name, t]) => [t.path.replace(/\/+$/, ""), { name, ...t }]));

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
    // request fields -> roles
    const args = {};
    for (const [role, field] of Object.entries(tool.fields || {})) if (body[field] !== undefined) args[role] = body[field];
    const id = String(args.customer_id ?? "");
    if (!CUSTOMERS[id]) return json(out(tool, { ok: false, error: "unknown customer_id" }));
    const r = await env.LEDGER.get(env.LEDGER.idFromName(id)).fetch("https://ledger/call", {
      method: "POST", body: JSON.stringify({ role: tool.role || tool.name, args, raw: body }),
    });
    return json(out(tool, await r.json()));
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

export class Ledger {
  constructor(state) { this.storage = state.storage; }

  async fetch(request) {
    const url = new URL(request.url);
    let led = (await this.storage.get("ledger")) || { calls: [], earlier: [] };
    if (url.pathname === "/read") return json(led);
    const { role, args, raw } = await request.json();
    const cust = CUSTOMERS[String(args.customer_id)];
    const idle = (config.new_call_after_idle_minutes || 15) * 60000;
    const now = Date.now();
    if (led.current && (led.current.closed || now - led.current.last > idle)) {
      led.earlier.push(led.current);
      led.earlier = led.earlier.slice(-20);
      led.current = null;
    }
    if (!led.current) led.current = { started: new Date(now).toISOString(), wrong: 0, verified: [], promises: [], notes: [], callbacks: [], transfers: [], outcome: null, closed: false, calls: [] };
    const c = led.current;
    c.last = now;
    const result = handle(role, args, cust, c);
    c.calls.push({ at: new Date(now).toISOString(), tool: role, args: raw, result });
    await this.storage.put("ledger", led);
    return json(result);
  }
}

function handle(role, a, cust, c) {
  if (c.closed) return { ok: false, error: "the call is already closed" };
  const fields = Object.keys(cust.identity || {});
  const allVerified = () => fields.every((f) => c.verified.includes(f));
  const maxWrong = config.max_wrong_total || 3;
  switch (role) {
    case "verify_identity": {
      if (c.wrong >= maxWrong) return { ok: false, error: "too many wrong answers" };
      const field = String(a.field ?? ""), want = cust.identity[field];
      if (want === undefined) return { ok: false, error: "unknown field " + field };
      const answer = String(a.answer ?? "").trim();
      const right = norm(answer) === norm(want);
      const hint = config.hints && config.hints.day_month_swapped;
      if (!right && hint && /^\d{4}-\d{2}-\d{2}$/.test(want) && answer === want.slice(0, 5) + want.slice(8, 10) + "-" + want.slice(5, 7) && want.slice(5, 7) !== want.slice(8, 10))
        return { ok: true, verified: false, hint, wrong_answers_left: maxWrong - c.wrong, all_verified: false };
      if (right) { if (!c.verified.includes(field)) c.verified.push(field); } else c.wrong += 1;
      return { ok: true, verified: right, wrong_answers_left: Math.max(0, maxWrong - c.wrong), all_verified: allVerified() };
    }
    case "get_account":
      if (!allVerified()) return { ok: false, error: "identity not verified" };
      return { ok: true, products: cust.products };
    case "create_promise": {
      if (!allVerified()) return { ok: false, error: "identity not verified" };
      const p = (cust.products || []).find((x) => String(x.product_id) === String(a.product_id));
      if (!p) return { ok: false, error: "unknown product_id" };
      if (c.promises.some((x) => String(x.product_id) === String(a.product_id))) return { ok: false, error: "this product already has a promise" };
      const amount = Number(a.amount);
      if (!(amount > 0)) return { ok: false, error: "the amount must be a positive number" };
      if (!/^\d{4}-\d{2}-\d{2}$/.test(String(a.date ?? ""))) return { ok: false, error: "the date must be YYYY-MM-DD" };
      const promise_id = "pr_" + (c.promises.length + 1);
      c.promises.push({ product_id: p.product_id, amount, date: a.date, promise_id });
      return { ok: true, promise_id };
    }
    case "add_note":
      c.notes.push({ product_id: a.product_id ?? null, reason: a.reason ?? null, text: a.text ?? null });
      return { ok: true };
    case "schedule_callback":
      c.callbacks.push({ date: a.date ?? null, time: a.time ?? null });
      return { ok: true };
    case "transfer_to_agent":
      c.transfers.push({ queue: a.queue ?? null });
      return { ok: true };
    case "close_call":
      c.outcome = { outcome: a.outcome ?? null, reason: a.reason ?? null };
      c.closed = true;
      return { ok: true };
    default:
      return { ok: true };
  }
}
