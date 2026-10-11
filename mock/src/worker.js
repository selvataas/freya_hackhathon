// The mock of the bank's statement and debt services, as the service contract (2026-10-01) and the test data give
// them. POST /voice/v1/<service> with the envelope {data, call}; for the bank's test customers it returns exactly the
// answers of test-customers.json (status code and body) after the delay the data gives. Lookup as the test data's
// table says: cards.list, contact.email.get and statement.pdf.send by data.customerNo; cards.balance and
// statement.week.get by data.cardNumber (across all customers); statement.week.decide and .change by data.cardNumber,
// then data.newStatementWeek. No entry: the service's 404 from the contract, or a 400 INVALID_ARGUMENTS_ERROR where
// the service has no 404; a missing lookup field: 400. Fields at the top level of the body and the earlier provisional
// paths are accepted too. An unfilled template ("{{...}}") gets a valid record. POST /oauth2/token answers a harmless
// token. Every call is appended to the customer's ledger: GET /ledger/<customerNo>. GET /health lists the services.
import routes from "../data/routes.json";
import data from "../data/test-customers.json";

const CUSTOMERS = Object.fromEntries(data.customers.map((c) => [String(c.customerNo), c]));
const SERVICES = Object.keys(routes.services);
const BY_PATH = {};
for (const svc of SERVICES) {
  for (const p of [routes.base + svc, ...(routes.services[svc].paths || [])]) BY_PATH[p.replace(/\/+$/, "")] = svc;
}
const SECRET = /authorization|cookie|key|token|secret/i;
const json = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json; charset=utf-8" } });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const isTemplate = (v) => typeof v === "string" && v.includes("{{");

let n = 0;
function result(code, message, type, http) {
  n += 1;
  const guid = (Date.now().toString(16) + n.toString(16)).padStart(32, "0").slice(-32);
  return { http, response: { result: { guid, returnCode: code, messageText: message, code, message, type,
    details: { guid, rootCause: http === 400 ? "InvalidArguments" : "NotFound", errorOrigin: "fides-mock" } } } };
}
const invalid = (msg) => result("INVALID_ARGUMENTS_ERROR", msg, "ERROR", 400);
function notFound(svc) {
  const nf = routes.services[svc].not_found;
  return nf ? result(nf.code, nf.message, "WARNING", 404) : invalid(routes.services[svc].not_found_400_message || "record not found");
}

function field(body, name) {
  const d = body && typeof body.data === "object" && body.data !== null ? body.data : {};
  for (const src of [d, body || {}]) {
    if (src[name] !== undefined && src[name] !== null && String(src[name]).trim() !== "") return String(src[name]).trim();
  }
  return null;
}

// every card of the test data, for the services looked up by card: masked number -> {customer, node}
const CARDS = {};
for (const c of data.customers) {
  for (const svc of ["cards.balance", "statement.week.get", "statement.week.decide", "statement.week.change"]) {
    const node = c.services[svc];
    if (node && node.http === undefined) for (const k of Object.keys(node)) (CARDS[k] ||= []).push(c);
  }
}
const digits = (s) => String(s).replace(/\D/g, "");
function cardKey(svc, asked) {
  const owners = (k) => (CARDS[k] || []).filter((c) => c.services[svc] && c.services[svc][k]);
  if (owners(asked).length) return asked;
  // another masking of the same card (first 4 + last 4): match the visible digits, only when one card fits
  const m = String(asked).match(/^(\d{4,6})\D+(\d{4})$/);
  if (!m) return null;
  const hits = Object.keys(CARDS).filter((k) => owners(k).length && digits(k).startsWith(m[1]) && digits(k).endsWith(m[2]));
  return hits.length === 1 ? hits[0] : null;
}

function answer(svc, body) {
  const by = routes.services[svc].lookup;   // "customer" or "card"
  if (by === "customer") {
    let no = field(body, "customerNo");
    if (no === null) return { cust: null, entry: invalid("customer number cannot be empty") };
    if (isTemplate(no)) no = String(data.customers[0].customerNo);
    const cust = CUSTOMERS[String(Number(no)) === "NaN" ? no : String(Number(no))] || CUSTOMERS[no];
    const node = cust && cust.services[svc];
    return { cust, entry: node && node.http !== undefined ? node : notFound(svc) };
  }
  let card = field(body, "cardNumber");
  if (card === null) return { cust: null, entry: invalid("card number cannot be empty") };
  if (isTemplate(card)) card = Object.keys(CARDS).find((k) => CARDS[k].some((c) => c.services[svc] && c.services[svc][k])) || card;
  const key = cardKey(svc, card);
  if (!key) return { cust: null, entry: notFound(svc) };
  const cust = CARDS[key].find((c) => c.services[svc] && c.services[svc][key]);
  let node = cust.services[svc][key];
  if (node.http === undefined) {                       // keyed by the requested week
    let w = field(body, "newStatementWeek");
    if (w === null) return { cust, entry: invalid("newStatementWeek cannot be empty") };
    if (isTemplate(w)) w = Object.keys(node)[0];
    const wk = Object.keys(node).find((x) => String(Number(x)) === String(Number(w)));
    node = wk ? node[wk] : null;
  }
  return { cust, entry: node && node.http !== undefined ? node : notFound(svc) };
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "");
    if (path === "/health") return json({ ok: true, services: SERVICES, paths: SERVICES.map((s) => routes.base + s), customers: data.customers.length });
    if (path === "/oauth2/token") return json({ access_token: "mock-token-not-checked", token_type: "Bearer", expires_in: 1800 });
    if (request.method === "GET" && path.startsWith("/ledger/")) {
      const id = decodeURIComponent(path.slice("/ledger/".length));
      return env.LEDGER.get(env.LEDGER.idFromName(id)).fetch("https://ledger/read");
    }
    const svc = BY_PATH[path];
    if (!svc) return json(invalid("unknown service " + path).response, 404);
    let body = {};
    try { body = await request.json(); } catch (e) { body = {}; }
    const { cust, entry } = answer(svc, body);
    const delay = Number(entry.delaySeconds ?? 0);
    if (delay > 0) await sleep(delay * 1000);
    const status = Number(entry.http) || 200;
    if (cust) {
      const headers = {};
      for (const [k, v] of request.headers) if (!SECRET.test(k)) headers[k] = v;
      const st = request.headers.get("sentry-trace");
      await env.LEDGER.get(env.LEDGER.idFromName(String(cust.customerNo))).fetch("https://ledger/append", {
        method: "POST", body: JSON.stringify({ at: new Date().toISOString(), service: svc, path, request: body, http: status, delay,
          conversation: st ? "trace:" + st.split("-")[0] : null, headers }),
      });
    }
    return json(entry.response ?? {}, status);
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
