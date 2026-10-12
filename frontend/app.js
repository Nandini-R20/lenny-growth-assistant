import { esc, renderMarkdown, parseSSE, fmtSec, fmtTs, guestName } from "./lib.js";

const $ = (s) => document.querySelector(s);
const state = { sessions: [], sid: null, config: null, provider: localStorage.getItem("provider"), busy: false, ctrl: null,
  lastText: "", artifacts: new Map(), panel: { key: null, tab: "preview", live: false } };

const EXAMPLES = [
  ["Ask", "How do you hire a head of growth?"],
  ["Ask", "What does Todd Jackson say about measuring product-market fit?"],
  ["Essay", "Write an essay on hiring your first head of growth"],
  ["Artifact", "Make an HTML checklist for finding product-market fit"],
];
const ICON = {
  send: '<svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 16V4M5 9l5-5 5 5"/></svg>',
  stop: '<svg viewBox="0 0 20 20" width="16" height="16" fill="currentColor"><rect x="4" y="4" width="12" height="12" rx="3"/></svg>',
  doc: '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h4"/></svg>',
};
const KINDS = { qa: "Answer", essay: "Ship 30 essay", artifact: "Artifact" };

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) {
    let e = null; try { e = (await r.json()).error; } catch { /* not json */ }
    throw Object.assign(new Error(e?.message || `Request failed (${r.status})`), { code: e?.code, status: r.status });
  }
  return r.status === 204 ? null : r.json();
}
const el = (tag, cls, html) => { const n = document.createElement(tag); if (cls) n.className = cls; if (html != null) n.innerHTML = html; return n; };

/* ---------- theme, banner, scrolling ---------- */
function setTheme(t) { document.documentElement.dataset.theme = t; localStorage.setItem("theme", t); }
setTheme(localStorage.getItem("theme") || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"));
$("#themeBtn").onclick = () => setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");

let bannerTimer;
function banner(msg) { const b = $("#banner"); b.textContent = msg; b.hidden = false; clearTimeout(bannerTimer); bannerTimer = setTimeout(() => (b.hidden = true), 7000); }
const nearBottom = () => { const s = $("#scroll"); return s.scrollHeight - s.scrollTop - s.clientHeight < 140; };
const toBottom = (force) => { const s = $("#scroll"); if (force || nearBottom()) s.scrollTop = s.scrollHeight; };

/* ---------- providers ---------- */
function renderProviders() {
  const seg = $("#providerSeg"); seg.innerHTML = "";
  for (const p of state.config.providers) {
    const b = el("button", null, `<b>${esc(p.label)}</b><small>${esc(p.model)}</small>`);
    b.setAttribute("role", "radio"); b.setAttribute("aria-checked", String(state.provider === p.id));
    if (!p.available) { b.disabled = true; b.title = p.reason || "Unavailable"; }
    b.onclick = () => { state.provider = p.id; localStorage.setItem("provider", p.id); renderProviders(); };
    seg.append(b);
  }
}
function pickProvider() {
  const ok = (id) => state.config.providers.some((p) => p.id === id && p.available);
  if (!ok(state.provider)) state.provider = ok(state.config.default_provider) ? state.config.default_provider : "ollama";
}

/* ---------- sessions sidebar ---------- */
async function loadSessions() {
  try { state.sessions = (await api("/api/sessions")).sessions; } catch { state.sessions = []; }
  const nav = $("#sessions"); nav.innerHTML = "";
  if (!state.sessions.length) nav.append(el("div", "empty-s", "No chats yet"));
  state.sessions.forEach((s, i) => {
    const row = el("div", "sess" + (s.id === state.sid ? " on" : ""));
    row.style.animationDelay = `${i * 25}ms`; row.tabIndex = 0;
    row.append(el("span", null, esc(s.title)));
    const x = el("button", "x", "×"); x.setAttribute("aria-label", "Delete chat");
    x.onclick = async (e) => { e.stopPropagation(); if (!confirm("Delete this chat?")) return; await api(`/api/sessions/${s.id}`, { method: "DELETE" }).catch(() => {}); if (s.id === state.sid) newChat(); else loadSessions(); };
    row.append(x);
    row.onclick = () => openSession(s.id);
    row.onkeydown = (e) => { if (e.key === "Enter") openSession(s.id); };
    nav.append(row);
  });
}
function closeSide() { $("#side").classList.remove("open"); $("#scrim").hidden = true; }
$("#menuBtn").onclick = () => { $("#side").classList.add("open"); $("#scrim").hidden = false; };
$("#scrim").onclick = closeSide;

function newChat() {
  if (state.busy) state.ctrl?.abort();
  state.sid = null; state.artifacts.clear(); closePanel(); closeSide();
  $("#chatTitle").textContent = "New chat"; showHero(); loadSessions(); $("#input").focus();
}
$("#newChat").onclick = newChat;

async function openSession(id) {
  if (state.busy) state.ctrl?.abort();
  closeSide(); closePanel();
  try {
    const s = await api(`/api/sessions/${id}`);
    state.sid = id; state.artifacts.clear();
    $("#chatTitle").textContent = s.title;
    const th = $("#thread"); th.innerHTML = ""; th.append(el("div", "thread-pad"));
    for (const m of s.messages) th.firstChild.append(m.role === "user" ? userMsg(m.content) : historyAssistant(m));
    toBottom(true); loadSessions();
  } catch (e) { banner(e.message); }
}

/* ---------- message building ---------- */
function showHero() {
  const th = $("#thread"); th.innerHTML = "";
  const h = el("div", "hero");
  h.innerHTML = `<h2>Ask the archive, <em>get the receipts.</em></h2><p>Conversations with the people who built and grew some of the best-known products. Every answer is grounded in transcripts and cites the exact moment.</p>`;
  const ex = el("div", "ex");
  EXAMPLES.forEach(([k, t], i) => { const b = el("button", null, `<small>${k}</small><span>${esc(t)}</span>`); b.style.animationDelay = `${120 + i * 70}ms`; b.onclick = () => send(t); ex.append(b); });
  h.append(ex); th.append(h);
}
function userMsg(text) {
  const m = el("div", "msg user"); m.append(el("div", "who", '<span class="dot"></span>You'));
  const b = el("div", "body"); b.textContent = text; m.append(b); return m;
}
function assistantShell() {
  const m = el("div", "msg assistant streaming");
  m.append(el("div", "who", '<span class="dot"></span>Assistant'));
  const body = el("div", "body"); const extra = el("div", "extra"); m.append(body, extra);
  return { m, body, extra };
}
function sourcesEl(sources) {
  const wrap = el("div"); wrap.append(el("div", "slabel", `Sources · ${sources.length}`));
  const grid = el("div", "sources");
  sources.forEach((s, i) => {
    const a = el("a", "src"); a.href = s.url; a.target = "_blank"; a.rel = "noopener noreferrer"; a.dataset.n = s.n; a.style.animationDelay = `${i * 70}ms`;
    a.innerHTML = `<div><span class="n">${s.n}</span><b>${esc(guestName(s))}</b></div><p>${esc(s.quote)}</p><div class="m"><span>${esc(fmtTs(s.at) || "full episode")}</span><span class="sim"><i style="width:${Math.round(s.similarity * 100)}%"></i></span><span>${Math.round(s.similarity * 100)}%</span></div>`;
    grid.append(a);
  });
  wrap.append(grid); return wrap;
}
function artifactChip(key, art, live) {
  const b = el("button", "chip-art", `${ICON.doc}<div><b>${esc(art.title)}</b><small>${live ? "Writing…" : art.type === "html" ? "HTML page · open viewer" : "Markdown document · open viewer"}</small></div>`);
  b.onclick = () => openPanel(key); return b;
}
function metaLine(d) {
  const bits = [d.provider && d.provider !== "none" ? (d.provider === "ollama" ? "Local" : "Cloud") + " · " + (d.model || "") : null,
    KINDS[d.route] || null, d.latency_ms ? "total " + fmtSec(d.latency_ms) : null, d.ttft_ms ? "first word " + fmtSec(d.ttft_ms) : null,
    d.fallback ? "fallback used" : null].filter(Boolean);
  return el("div", "metaline", bits.map((b) => `<span>${esc(b)}</span>`).join(""));
}
function noAnswer(m, body, extra) {
  m.classList.add("noanswer");
  const s = el("div", "suggest"); EXAMPLES.slice(0, 3).forEach(([, t]) => { const b = el("button", null, esc(t)); b.onclick = () => send(t); s.append(b); });
  extra.append(s);
}
function historyAssistant(msg) {
  const { m, body, extra } = assistantShell(); m.classList.remove("streaming"); m.style.animation = "none";
  const sources = msg.sources || []; m._sources = sources;
  body.innerHTML = renderMarkdown(msg.content, { sources: sources.length });
  if (msg.artifact) { const key = "m" + msg.id; state.artifacts.set(key, msg.artifact); extra.append(artifactChip(key, msg.artifact)); }
  if (msg.provider === "none") noAnswer(m, body, extra);
  else if (sources.length) extra.append(sourcesEl(sources));
  extra.append(metaLine({ provider: msg.provider, model: msg.model, route: msg.route, latency_ms: msg.latency_ms }));
  return m;
}

/* ---------- sending + streaming ---------- */
function setBusy(b) {
  state.busy = b; const s = $("#send"); s.innerHTML = b ? ICON.stop : ICON.send; s.classList.toggle("stop", b);
  s.setAttribute("aria-label", b ? "Stop" : "Send"); s.disabled = !b && !$("#input").value.trim();
}
async function send(text) {
  text = (text ?? $("#input").value).trim();
  if (!text || state.busy) return;
  state.lastText = text; $("#input").value = ""; autoGrow();
  const th = $("#thread");
  if (!th.querySelector(".thread-pad")) { th.innerHTML = ""; th.append(el("div", "thread-pad")); }
  const pad = th.firstChild;
  pad.append(userMsg(text));
  const ui = assistantShell(); pad.append(ui.m); toBottom(true);
  const ctx = { ...ui, text: "", sources: [], n: 0, art: null, artKey: null, first: true, t0: performance.now(), raf: 0 };
  ctx.think = el("div", "thinking", `<div class="think-row"><span class="what"><b>Searching</b> the transcripts…</span><span class="t">0s</span></div><div class="bars"><i></i><i></i><i></i></div>`);
  ctx.body.after(ctx.think);
  ctx.timer = setInterval(() => {
    const s = Math.round((performance.now() - ctx.t0) / 1000); const t = ctx.think.querySelector(".t"); if (t) t.textContent = s + "s";
    if (s === 20 && !ctx.think.querySelector(".slow")) ctx.think.append(el("div", "slow", "Local models on a CPU can take a minute or two to start writing. Switch to Cloud for faster answers."));
  }, 1000);
  setBusy(true); state.ctrl = new AbortController();
  try {
    if (!state.sid) { const s = await api("/api/sessions", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ client_id: clientId() }) }); state.sid = s.id; }
    const r = await fetch(`/api/sessions/${state.sid}/messages`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ content: text, provider: state.provider }), signal: state.ctrl.signal });
    if (!r.ok) { let e = null; try { e = (await r.json()).error; } catch { /* */ } throw Object.assign(new Error(e?.message || `Request failed (${r.status})`), { code: e?.code }); }
    const reader = r.body.getReader(); const dec = new TextDecoder(); let buf = "";
    for (;;) {
      const { value, done } = await reader.read(); if (done) break;
      buf += dec.decode(value, { stream: true });
      const { events, rest } = parseSSE(buf); buf = rest;
      for (const ev of events) handle(ev, ctx);
    }
  } catch (e) {
    if (e.name === "AbortError") { ctx.note = "Stopped."; } else fail(ctx, e.message);
  } finally {
    clearInterval(ctx.timer); ctx.think.remove(); ctx.m.classList.remove("streaming"); flush(ctx);
    if (ctx.note && !ctx.text) ctx.extra.append(el("div", "note", ctx.note));
    setBusy(false); await loadSessions(); const t = state.sessions.find((x) => x.id === state.sid); if (t) $("#chatTitle").textContent = t.title;
  }
}
function clientId() { let c = localStorage.getItem("cid"); if (!c) { c = crypto.randomUUID(); localStorage.setItem("cid", c); } return c; }
function fail(ctx, msg) {
  ctx.m.classList.remove("streaming");
  const box = el("div", "errbox", `<b>That didn't work.</b><div>${esc(msg)}</div>`); const b = el("button", null, "Try again");
  b.onclick = () => { box.remove(); send(state.lastText); }; box.append(b); ctx.extra.append(box);
}
function flush(ctx) { cancelAnimationFrame(ctx.raf); ctx.body.innerHTML = renderMarkdown(ctx.text, { sources: ctx.n }); }
function schedule(ctx) { if (ctx.raf) return; ctx.raf = requestAnimationFrame(() => { ctx.raf = 0; const stick = nearBottom(); ctx.body.innerHTML = renderMarkdown(ctx.text, { sources: ctx.n }); if (stick) toBottom(true); }); }

function handle({ event, data: d }, ctx) {
  const what = ctx.think.querySelector(".what");
  switch (event) {
    case "status": if (what && d.phase === "thinking") what.innerHTML = ctx.n ? `<b>Reading</b> ${ctx.n} excerpts…` : "<b>Thinking</b>…"; break;
    case "meta": ctx.sources = d.sources; ctx.n = d.sources.length; ctx.m._sources = d.sources; ctx.meta = d;
      if (what) what.innerHTML = ctx.n ? `<b>Reading</b> ${ctx.n} excerpts…` : "<b>Checking</b> the archive…"; break;
    case "fallback": ctx.extra.append(el("div", "note", "The cloud model failed, so this answer comes from the local model.")); break;
    case "token":
      if (ctx.first) { ctx.first = false; ctx.ttft = performance.now() - ctx.t0; ctx.think.remove(); clearInterval(ctx.timer); }
      ctx.text += d.text; schedule(ctx); break;
    case "replace_text": ctx.text = d.text; schedule(ctx); break;
    case "artifact_start":
      if (ctx.first) { ctx.first = false; ctx.think.remove(); clearInterval(ctx.timer); }
      ctx.art = { type: d.type, title: d.title, content: "" }; ctx.artKey = "n" + Date.now();
      state.artifacts.set(ctx.artKey, ctx.art); ctx.chip = artifactChip(ctx.artKey, ctx.art, true); ctx.extra.prepend(ctx.chip);
      openPanel(ctx.artKey, true); setTimeout(() => toBottom(true), 560); break;
    case "artifact_delta": if (ctx.art) { ctx.art.content += d.text; liveSource(ctx.art); } break;
    case "artifact_end": {
      const k = ctx.artKey || "n" + Date.now(); const art = { ...d }; state.artifacts.set(k, art); ctx.artKey = k;
      if (ctx.chip) ctx.chip.replaceWith((ctx.chip = artifactChip(k, art))); else { ctx.chip = artifactChip(k, art); ctx.extra.prepend(ctx.chip); }
      state.panel.tab = "preview"; openPanel(k, false); setTimeout(() => toBottom(true), 560); break;
    }
    case "error": fail(ctx, d.message); break;
    case "done": finish(d, ctx); break;
  }
}
function finish(d, ctx) {
  clearInterval(ctx.timer); ctx.think.remove(); ctx.m.classList.remove("streaming"); flush(ctx);
  const supported = d.grounding?.supported !== false;
  if (!supported) noAnswer(ctx.m, ctx.body, ctx.extra);
  else if (ctx.sources.length) ctx.extra.append(sourcesEl(ctx.sources));
  d.ttft_ms = d.ttft_ms ?? (ctx.ttft ? Math.round(ctx.ttft) : null);
  ctx.extra.append(metaLine(d)); toBottom(true);
}

/* ---------- citation popover ---------- */
const pop = $("#pop");
function showPop(c) {
  const msg = c.closest(".msg"); const s = msg?._sources?.find((x) => String(x.n) === c.dataset.n); if (!s) return;
  pop.innerHTML = `<b>${esc(guestName(s))}</b><small>${esc(s.episode)} · ${esc(fmtTs(s.at) || "full episode")}</small><p>${esc(s.quote)}…</p>`;
  pop.hidden = false; const r = c.getBoundingClientRect(); const w = pop.offsetWidth;
  pop.style.left = Math.max(8, Math.min(innerWidth - w - 8, r.left - 20)) + "px";
  const below = r.bottom + 10 + pop.offsetHeight < innerHeight; pop.style.top = (below ? r.bottom + 10 : r.top - pop.offsetHeight - 10) + "px";
  msg.querySelectorAll(".src").forEach((e) => e.classList.toggle("hl", e.dataset.n === c.dataset.n));
}
const hidePop = () => { pop.hidden = true; document.querySelectorAll(".src.hl").forEach((e) => e.classList.remove("hl")); };
const thread = $("#thread");
thread.addEventListener("mouseover", (e) => { const c = e.target.closest(".cite"); if (c) showPop(c); });
thread.addEventListener("mouseout", (e) => { if (e.target.closest(".cite")) hidePop(); });
thread.addEventListener("focusin", (e) => { const c = e.target.closest(".cite"); if (c) showPop(c); });
thread.addEventListener("focusout", hidePop);
thread.addEventListener("click", (e) => { const c = e.target.closest(".cite"); if (!c) return; const s = c.closest(".msg")?._sources?.find((x) => String(x.n) === c.dataset.n); if (s) window.open(s.url, "_blank", "noopener"); });

/* ---------- artifact viewer ---------- */
const panelKey = () => state.panel.key; const curArt = () => state.artifacts.get(state.panel.key);
function openPanel(key, live = false) {
  state.panel.key = key; state.panel.live = live; if (live) state.panel.tab = "source";
  $("#app").classList.add("panel-open"); renderPanel();
}
function closePanel() { $("#app").classList.remove("panel-open"); state.panel.key = null; }
$("#closePanel").onclick = closePanel;
$("#tabPreview").onclick = () => { state.panel.tab = "preview"; renderPanel(); };
$("#tabSource").onclick = () => { state.panel.tab = "source"; renderPanel(); };
function liveSource(art) {
  if (panelKey() == null || curArt() !== art) return;
  const pre = $("#pbody pre.src-view"); if (pre) { pre.textContent = art.content; const b = $("#pbody"); b.scrollTop = b.scrollHeight; const w = $("#pbody .writing span:last-child"); if (w) w.textContent = `Writing… ${art.content.split(/\s+/).filter(Boolean).length} words`; }
  else renderPanel();
}
function htmlDoc(content) {
  return `<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:"><base target="_blank"><style>body{font:16px/1.6 Georgia,serif;margin:24px;color:#1B1A17;background:#fff}h1,h2,h3{line-height:1.2}a{color:#0F5C4D}table{border-collapse:collapse}td,th{border:1px solid #ddd;padding:6px 10px}</style>${content}`;
}
function renderPanel() {
  const art = curArt(); if (!art) return; const live = state.panel.live; const tab = live ? "source" : state.panel.tab;
  $("#ptitle").textContent = art.title; $("#pkind").textContent = art.type === "html" ? "HTML artifact" : "Markdown artifact";
  $("#tabPreview").setAttribute("aria-selected", String(tab === "preview")); $("#tabSource").setAttribute("aria-selected", String(tab === "source"));
  const note = $("#pnote"); const removed = art.removed || [];
  note.hidden = !(art.type === "html" && art.sanitized); if (!note.hidden) note.textContent = removed.length ? `Sanitized for safety. Removed: ${removed.join(", ")}. Shown in a sandbox with scripts disabled.` : "Sanitized and shown in a sandbox with scripts disabled.";
  const body = $("#pbody"); body.innerHTML = "";
  if (tab === "source" || live) {
    if (live) body.append(el("div", "writing", '<span class="pulse"></span><span>Writing…</span>'));
    const pre = el("pre", "src-view"); pre.textContent = art.content; body.append(pre);
  } else if (art.type === "html") {
    const f = document.createElement("iframe"); f.setAttribute("sandbox", ""); f.title = art.title; f.srcdoc = htmlDoc(art.content); body.append(f);
  } else { const d = el("div", "body"); d.innerHTML = renderMarkdown(art.content, { sources: 0 }); body.append(d); }
}
$("#copyBtn").onclick = async () => { const a = curArt(); if (!a) return; try { await navigator.clipboard.writeText(a.content); $("#copyBtn").textContent = "Copied"; } catch { banner("Copy failed. Select the text in Source view instead."); } setTimeout(() => ($("#copyBtn").textContent = "Copy"), 1400); };
$("#dlBtn").onclick = () => {
  const a = curArt(); if (!a) return; const blob = new Blob([a.type === "html" ? htmlDoc(a.content) : a.content], { type: a.type === "html" ? "text/html" : "text/markdown" });
  const l = document.createElement("a"); l.href = URL.createObjectURL(blob); l.download = (a.title || "artifact").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 60) + (a.type === "html" ? ".html" : ".md"); l.click(); setTimeout(() => URL.revokeObjectURL(l.href), 2000);
};

/* ---------- composer ---------- */
const input = $("#input");
function autoGrow() { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 180) + "px"; if (!state.busy) $("#send").disabled = !input.value.trim(); }
input.addEventListener("input", autoGrow);
input.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); } });
$("#send").onclick = () => (state.busy ? state.ctrl?.abort() : send());
document.addEventListener("keydown", (e) => { if (e.key === "Escape") { hidePop(); if ($("#app").classList.contains("panel-open")) closePanel(); closeSide(); } });

/* ---------- boot ---------- */
(async function init() {
  setBusy(false); showHero(); autoGrow();
  try {
    state.config = await api("/api/config"); pickProvider(); renderProviders();
    const ix = state.config.index; $("#indexNote").textContent = ix ? `${ix.episodes} episodes indexed` : "index offline";
    $("#input").maxLength = state.config.limits.max_message_chars;
  } catch (e) { banner("Cannot reach the server. Is the API running on port 8000?"); $("#indexNote").textContent = "offline"; }
  loadSessions();
})();
