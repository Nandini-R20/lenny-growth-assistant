// Pure helpers (no DOM): safe markdown, citation chips, SSE parsing, formatting. Unit-tested in Node.

export const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

const safeUrl = (u) => (/^(https?:\/\/|mailto:|#)/i.test(u.trim()) ? u.trim() : "#");

function inline(text, maxCite) {
  const codes = [];
  let t = text.replace(/`([^`]+)`/g, (_, c) => { codes.push(c); return `\u0000${codes.length - 1}\u0000`; });
  t = esc(t);
  t = t.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_, label, url) => `<a href="${esc(safeUrl(url.replace(/&amp;/g, "&")))}" target="_blank" rel="noopener noreferrer">${label}</a>`);
  t = t.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>").replace(/(^|[\s(])\*([^*\s][^*]*)\*/g, "$1<em>$2</em>");
  if (maxCite > 0) {
    t = t.replace(/\[(\d{1,2})\](?!\()/g, (m, n) => (+n >= 1 && +n <= maxCite ? `<sup class="cite" data-n="${n}" tabindex="0" role="button" aria-label="Source ${n}">${n}</sup>` : m));
  }
  return t.replace(/\u0000(\d+)\u0000/g, (_, i) => `<code>${esc(codes[+i])}</code>`);
}

// Small, safe Markdown subset. Everything is HTML-escaped first; only our own tags are emitted.
export function renderMarkdown(src, { sources = 0 } = {}) {
  const lines = String(src).replace(/\r\n/g, "\n").split("\n");
  const out = [];
  let i = 0;
  const isTableSep = (l) => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(l || "");
  const cells = (l) => l.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
  while (i < lines.length) {
    const line = lines[i];
    if (/^```/.test(line)) {
      const buf = []; i++;
      while (i < lines.length && !/^```/.test(lines[i])) buf.push(lines[i++]);
      i++; out.push(`<pre><code>${esc(buf.join("\n"))}</code></pre>`); continue;
    }
    if (!line.trim()) { i++; continue; }
    let m;
    if ((m = /^(#{1,4})\s+(.*)$/.exec(line))) { out.push(`<h${m[1].length}>${inline(m[2], sources)}</h${m[1].length}>`); i++; continue; }
    if (/^\s*(-{3,}|\*{3,})\s*$/.test(line)) { out.push("<hr>"); i++; continue; }
    if (line.includes("|") && isTableSep(lines[i + 1])) {
      const head = cells(line); i += 2; const rows = [];
      while (i < lines.length && lines[i].includes("|") && lines[i].trim()) rows.push(cells(lines[i++]));
      out.push(`<div class="tablewrap"><table><thead><tr>${head.map((c) => `<th>${inline(c, sources)}</th>`).join("")}</tr></thead><tbody>${rows.map((r) => `<tr>${r.map((c) => `<td>${inline(c, sources)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`);
      continue;
    }
    if (/^\s*>\s?/.test(line)) {
      const buf = []; while (i < lines.length && /^\s*>\s?/.test(lines[i])) buf.push(lines[i++].replace(/^\s*>\s?/, ""));
      out.push(`<blockquote>${inline(buf.join(" "), sources)}</blockquote>`); continue;
    }
    if (/^\s*([-*+])\s+/.test(line) || /^\s*\d+[.)]\s+/.test(line)) {
      const ordered = /^\s*\d+[.)]\s+/.test(line); const items = [];
      while (i < lines.length && (ordered ? /^\s*\d+[.)]\s+/ : /^\s*([-*+])\s+/).test(lines[i])) {
        items.push(lines[i++].replace(ordered ? /^\s*\d+[.)]\s+/ : /^\s*([-*+])\s+/, ""));
      }
      const tag = ordered ? "ol" : "ul";
      const task = items.length > 0 && items.every((x) => /^(\[[ xX]\]|\u2610|\u2611)\s/.test(x));
      const li = (x) => {
        const m = /^(\[[ xX]\]|\u2610|\u2611)\s+(.*)$/.exec(x);
        return m ? `<li class="task"><span class="chk" aria-hidden="true">${/[xX\u2611]/.test(m[1]) ? "\u2611" : "\u2610"}</span>${inline(m[2], sources)}</li>` : `<li>${inline(x, sources)}</li>`;
      };
      out.push(`<${tag}${task ? ' class="tasks"' : ""}>${items.map(li).join("")}</${tag}>`); continue;
    }
    const para = [line]; i++;
    while (i < lines.length && lines[i].trim() && !/^(#{1,4}\s|```|\s*>|\s*([-*+]|\d+[.)])\s+|\s*(-{3,}|\*{3,})\s*$)/.test(lines[i])) para.push(lines[i++]);
    // A paragraph that is only citation markers ("[3] [2] [4]") adds nothing: the source cards already show them.
    if (sources > 0 && /^(\s*\[\d{1,2}\]\s*[.,;]?)+\s*$/.test(para.join(" "))) continue;
    out.push(`<p>${inline(para.join(" "), sources)}</p>`);
  }
  return out.join("\n");
}

// Server-Sent Events: feed text chunks, get complete events back (handles splits anywhere).
export function parseSSE(buffer) {
  const events = [];
  const parts = buffer.split("\n\n");
  const rest = parts.pop();
  for (const block of parts) {
    let event = "message"; const data = [];
    for (const l of block.split("\n")) {
      if (l.startsWith("event:")) event = l.slice(6).trim();
      else if (l.startsWith("data:")) data.push(l.slice(5).trim());
    }
    if (data.length) { try { events.push({ event, data: JSON.parse(data.join("\n")) }); } catch { /* ignore bad frame */ } }
  }
  return { events, rest };
}

export const fmtSec = (ms) => (ms == null ? "" : ms < 10000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms / 1000)}s`);
export const fmtTs = (ts) => { if (!ts) return ""; const [h, m, s] = ts.split(":").map(Number); return h ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}` : `${m}:${String(s).padStart(2, "0")}`; };
export const guestName = (s) => (s.guest || "").trim() || "Lenny's Podcast";
