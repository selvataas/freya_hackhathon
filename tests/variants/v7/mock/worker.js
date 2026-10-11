// A test service for the synthetic clinic case (tests/variants/v7/veteriner): fixed answers, every request logged.
const APPTS = { "05321234567": [
  { appointment_id: "a1", pet_name: "Boncuk", service: "muayene", date: "2026-11-05", time: "10:00" },
  { appointment_id: "a2", pet_name: "Pamuk", service: "asi", date: "2026-11-06", time: "11:30" } ] };
const LOG = [];
const json = (b, s = 200) => new Response(JSON.stringify(b), { status: s, headers: { "content-type": "application/json" } });
export default {
  async fetch(req) {
    const u = new URL(req.url);
    let body = {};
    try { body = await req.json(); } catch (e) {}
    LOG.push({ at: new Date().toISOString(), method: req.method, path: u.pathname, body });
    if (u.pathname === "/log") return json(LOG.slice(-50));
    const m = u.pathname.match(/^\/owners\/([^/]+)\/appointments$/);
    if (m) return json({ ok: true, appointments: APPTS[decodeURIComponent(m[1])] || [] });
    if (u.pathname === "/slots/free") return json({ ok: true, slots: ["10:00", "11:30", "15:00"] });
    if (u.pathname === "/appointments/move" || u.pathname === "/appointments/cancel") return json({ ok: true });
    return json({ ok: false, error: "unknown path" }, 404);
  },
};
