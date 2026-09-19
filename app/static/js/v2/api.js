/* ===== Tiny fetch helpers ===== */
const API = {
    async get(url) {
        const r = await fetch(url);
        if (!r.ok) throw new Error(await API._err(r));
        return r.json();
    },
    async send(method, url, body) {
        const r = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
        if (!r.ok) throw new Error(await API._err(r));
        const t = await r.text();
        try { return t ? JSON.parse(t) : null; } catch (_) { return t; }
    },
    post(url, body) { return API.send('POST', url, body); },
    put(url, body) { return API.send('PUT', url, body); },
    del(url) { return API.send('DELETE', url); },
    async _err(r) {
        try { const j = await r.json(); return typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail || j); }
        catch (_) { return `${r.status} ${r.statusText}`; }
    },
};

function esc(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function pad2(n) { return String(n).padStart(2, '0'); }
function fmtDate(d) { return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`; }
function toast(msg, isErr) {
    let el = document.getElementById('toast');
    if (!el) { el = document.createElement('div'); el.id = 'toast'; document.body.appendChild(el); }
    el.textContent = msg; el.className = 'show' + (isErr ? ' err' : '');
    clearTimeout(el._t); el._t = setTimeout(() => el.className = '', 2600);
}
