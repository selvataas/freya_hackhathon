// The mock of the bank's services: for the bank's test customers it returns exactly the answers of the test data,
// HTTP status included, after the delay the data gives. data/routes.json maps each service to its method, paths and
// request field names; data/test-customers.json is the bank's test data. Every call is appended to the customer's
// ledger (one Durable Object per customer): GET /ledger/<customerNo>. GET /health lists the services.
import routes from "../data/routes.json";
import data from "../data/test-customers.json";

const CUSTOMERS = Object.fromEntries(data.customers.map((c) => [String(c.customerNo), c]));
const BY_PATH = {};
for (const [svc, r] of Object.entries(routes.services)) for (const p of r.paths) BY_PATH[p.replace(/\/+$/, "")] = svc;
const SECRET = /authorization|cookie|key|token|secret/i;
const json = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json; charset=utf-8" } });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function field(obj, names) {
  for (const n of names) if (obj[n] !== undefined && obj[n] !== null && obj[n] !== "") return String(obj[n]);
  const lower = Object.fromEntries(Object.entries(obj).map(([k, v]) => [k.toLowerCase(), v]));
  for (const n of names) if (lower[n.toLowerCase()] !== undefined && lower[n.toLowerCase()] !== "") return String(lower[n.toLowerCase()]);
  return null;
}

// a card the request names: the masked number as cards.list gives it, another masking, or the last four digits
function cardKey(keys, asked) {
  if (!asked) return keys.length === 1 ? keys[0] : null;
  if (keys.includes(asked)) return asked;
  const digits = asked.replace(/\D/g, "");
  const last4 = digits.slice(-4), first = digits.slice(0, 4);
  const hits = keys.filter((k) => k.replace(/\D/g, "").slice(-4) === last4);
  if (hits.length === 1) return hits[0];
  const better = hits.filter((k) => k.replace(/\D/g, "").startsWith(first));
  return better.length === 1 ? better[0] : null;
}

const notFound = (msg) => ({ http: 404, response: { result: { returnCode: "MOCK_404", messageText: msg, code: "MOCK_404", message: msg, type: "WARNING" } } });

function answer(svc, body) {
  const no = field(body, routes.customer_fields);
  const cust = no && CUSTOMERS[no];
  if (!cust) return { cust: null, entry: notFound("Müşteri bulunamadı.") };
  let node = cust.services[svc];
  if (!node) return { cust, entry: notFound("Servis cevabı yok.") };
  if (node.http === undefined) {                       // keyed by card
    const k = cardKey(Object.keys(node), field(body, routes.card_fields));
    if (!k) return { cust, entry: notFound("Kart bulunamadı.") };
    node = node[k];
    if (node.http === undefined) {                     // keyed by the requested week
      const w = field(body, routes.week_fields);
      const wk = w && Object.keys(node).find((x) => String(Number(x)) === String(Number(w)));
      if (!wk) return { cust, entry: notFound("Hafta için cevap yok.") };
      node = node[wk];
    }
  }
  return { cust, entry: node };
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "");
    if (path === "/health") return json({ ok: true, services: Object.keys(routes.services), customers: data.customers.length });
    if (request.method === "GET" && path.startsWith("/ledger/")) {
      const id = decodeURIComponent(path.slice("/ledger/".length));
      return env.LEDGER.get(env.LEDGER.idFromName(id)).fetch("https://ledger/read");
    }
    const svc = BY_PATH[path];
    if (!svc) return json({ result: { returnCode: "MOCK_404", messageText: "unknown path " + path } }, 404);
    let body = {};
    if (request.method === "GET") body = Object.fromEntries(url.searchParams);
    else { try { body = await request.json(); } catch (e) { body = {}; } }
    const { cust, entry } = answer(svc, body);
    const delay = Number(entry.delaySeconds ?? entry.gecikmeSaniye ?? 0);
    if (delay > 0) await sleep(delay * 1000);
    const status = Number(entry.http) || 200;
    const resp = entry.response ?? entry.yanit ?? {};
    if (cust) {
      const headers = {};
      for (const [k, v] of request.headers) if (!SECRET.test(k)) headers[k] = v;
      const st = request.headers.get("sentry-trace");
      await env.LEDGER.get(env.LEDGER.idFromName(String(cust.customerNo))).fetch("https://ledger/append", {
        method: "POST", body: JSON.stringify({ at: new Date().toISOString(), service: svc, path, request: body, http: status, delay,
          conversation: st ? "trace:" + st.split("-")[0] : null, headers }),
      });
    }
    return json(resp, status);
  },
};

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
