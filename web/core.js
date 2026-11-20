/* Shared UI helpers: safe DOM building (text only, no innerHTML), API calls with the per-launch token,
   formatting, themes, toast, and a small line-chart renderer. */
(() => {
  "use strict";
  const $ = (s, root) => (root || document).querySelector(s);
  const TOKEN = ($('meta[name="app-token"]') || {}).content || "";
  const ATTRS = /^(id|class|type|value|title|href|download|for|role|tabindex|colspan|src|alt|loading|width|height|name|min|max|step|placeholder|maxlength|checked|disabled|selected|open|data-[a-z-]+|aria-[a-z-]+)$/;

  function el(tag, attrs, ...kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === "text") n.textContent = String(v);
      else if (k === "className") n.className = v;
      else if (k === "on") { for (const [ev, fn] of Object.entries(v)) n.addEventListener(ev, fn); }
      else if (ATTRS.test(k)) n.setAttribute(k, v === true ? "" : String(v));
      else throw new Error("attribute not allowed: " + k);
    }
    for (const c of kids.flat()) {
      if (c == null || c === false) continue;
      n.appendChild(typeof c === "string" || typeof c === "number" ? document.createTextNode(String(c)) : c);
    }
    return n;
  }
  const clear = (n) => { while (n.firstChild) n.removeChild(n.firstChild); return n; };

  let toastTimer;
  function toast(msg, isError) {
    const t = $("#toast");
    if (!t) return;
    t.textContent = msg;
    t.className = "show" + (isError ? " error" : "");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.className = ""; }, isError ? 6000 : 3200);
  }

  async function api(path) {
    const r = await fetch(path, { cache: "no-store" });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error || r.statusText);
    return j;
  }
  async function post(path, body) {
    const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json", "X-App-Token": TOKEN },
                                  body: JSON.stringify(body || {}) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error || r.statusText);
    return j;
  }

  function bytes(n) {
    if (n == null || isNaN(n)) return "—";
    const u = ["B", "KB", "MB", "GB", "TB", "PB"];
    let i = 0, v = Number(n);
    while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
    return (i === 0 ? v.toFixed(0) : v >= 100 ? v.toFixed(0) : v.toFixed(1)) + " " + u[i];
  }
  const num = (n, d) => (n == null || isNaN(n) ? "—" : Number(n).toLocaleString(undefined, { maximumFractionDigits: d == null ? 0 : d }));
  const dt = (t) => (t ? new Date(t * 1000).toLocaleString() : "—");
  const dshort = (t) => (t ? new Date(t * 1000).toLocaleDateString() : "—");
  function ago(t, now) {
    const s = Math.max(0, Math.round((now || Date.now() / 1000) - t));
    if (s < 60) return "just now";
    if (s < 3600) return Math.round(s / 60) + " min ago";
    if (s < 86400) return Math.round(s / 3600) + " h ago";
    return Math.round(s / 86400) + " d ago";
  }
  function dur(s) {
    s = Math.max(0, Math.round(s));
    if (s < 60) return s + " s";
    if (s < 3600) return Math.floor(s / 60) + " min " + (s % 60) + " s";
    return Math.floor(s / 3600) + " h " + Math.round((s % 3600) / 60) + " min";
  }

  // themes
  const THEMES = ["dark", "light", "green", "amber", "blue", "mono"];
  function applyTheme(t) {
    if (!THEMES.includes(t)) t = "dark";
    if (t === "dark") document.documentElement.removeAttribute("data-theme");
    else document.documentElement.setAttribute("data-theme", t);
    try { localStorage.setItem("app.theme", t); } catch { /* ignore */ }
  }
  function initTheme(sel) {
    let t = "dark";
    try { t = localStorage.getItem("app.theme") || "dark"; } catch { /* ignore */ }
    applyTheme(t);
    if (sel) { sel.value = THEMES.includes(t) ? t : "dark"; sel.addEventListener("change", () => applyTheme(sel.value)); }
  }
  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#888";

  /* Line chart. series: [{name,color,points:[[t,v],...], dashed?}], opts: {yLabel, yMin, yMax, tMin, tMax, band?:[[t,lo,hi]], marks?:[[t,color]], fmtY, hline?:{v,label,color}} */
  function chart(canvas, series, opts) {
    opts = opts || {};
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth || 600, h = canvas.clientHeight || 240;
    canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
    const g = canvas.getContext("2d");
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    const padL = 54, padR = 12, padT = 10, padB = 24;
    const pw = w - padL - padR, ph = h - padT - padB;
    const all = series.flatMap((s) => s.points);
    const fmtY = opts.fmtY || ((v) => String(Math.round(v * 10) / 10));
    const grid = css("--grid"), muted = css("--muted");
    g.font = "11px Segoe UI, system-ui, sans-serif";
    if (!all.length && !opts.hline) {
      g.fillStyle = muted; g.textAlign = "center"; g.fillText(opts.empty || "No data yet", w / 2, h / 2); return;
    }
    let tMin = opts.tMin != null ? opts.tMin : Math.min(...all.map((p) => p[0]));
    let tMax = opts.tMax != null ? opts.tMax : Math.max(...all.map((p) => p[0]));
    if (tMax <= tMin) tMax = tMin + 60;
    let yMin = opts.yMin != null ? opts.yMin : 0;
    let yMax = opts.yMax != null ? opts.yMax : Math.max(1, ...all.map((p) => p[1]), opts.hline ? opts.hline.v : 0) * 1.12;
    if (yMax <= yMin) yMax = yMin + 1;
    const X = (t) => padL + ((t - tMin) / (tMax - tMin)) * pw;
    const Y = (v) => padT + ph - ((v - yMin) / (yMax - yMin)) * ph;
    g.strokeStyle = grid; g.lineWidth = 1; g.fillStyle = muted; g.textAlign = "right";
    for (let i = 0; i <= 4; i++) {
      const v = yMin + ((yMax - yMin) * i) / 4, y = Math.round(Y(v)) + 0.5;
      g.beginPath(); g.moveTo(padL, y); g.lineTo(w - padR, y); g.stroke();
      g.fillText(fmtY(v), padL - 6, y + 3);
    }
    g.textAlign = "center";
    const span = tMax - tMin;
    for (let i = 0; i <= 4; i++) {
      const t = tMin + (span * i) / 4;
      const d = new Date(t * 1000);
      const label = span > 2 * 86400 ? d.toLocaleDateString(undefined, { month: "short", day: "numeric" })
        : d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
      g.fillText(label, Math.min(w - 24, Math.max(padL + 10, X(t))), h - 6);
    }
    (opts.marks || []).forEach(([t, color]) => {
      if (t < tMin || t > tMax) return;
      g.fillStyle = color; g.globalAlpha = 0.18; g.fillRect(X(t) - 3, padT, 6, ph); g.globalAlpha = 1;
    });
    if (opts.hline) {
      g.strokeStyle = opts.hline.color || css("--warn"); g.setLineDash([6, 4]); g.beginPath();
      g.moveTo(padL, Y(opts.hline.v)); g.lineTo(w - padR, Y(opts.hline.v)); g.stroke(); g.setLineDash([]);
      g.fillStyle = opts.hline.color || css("--warn"); g.textAlign = "left"; g.fillText(opts.hline.label || "", padL + 6, Y(opts.hline.v) - 4);
    }
    for (const s of series) {
      const pts = s.points.filter((p) => p[1] != null);
      g.strokeStyle = s.color; g.fillStyle = s.color; g.lineWidth = 2; g.setLineDash(s.dashed ? [6, 4] : []);
      g.beginPath();
      let pen = false, prev = null;
      for (const [t, v] of pts) {
        const gap = opts.maxGap && prev != null && t - prev > opts.maxGap;
        if (!pen || gap) { g.moveTo(X(t), Y(v)); pen = true; } else g.lineTo(X(t), Y(v));
        prev = t;
      }
      g.stroke(); g.setLineDash([]);
      if (pts.length <= 60) pts.forEach(([t, v]) => { g.beginPath(); g.arc(X(t), Y(v), 2.5, 0, Math.PI * 2); g.fill(); });
    }
  }


  /* Modal dialog (text only). children: array of nodes. Returns {close, back}. Escape closes. */
  function modal(children) {
    const root = $("#modal-root");
    const back = el("div", { className: "modal-back", role: "presentation" }, el("div", { className: "modal", role: "dialog", "aria-modal": "true" }, children));
    root.appendChild(back);
    const close = () => { if (back.parentNode) back.parentNode.removeChild(back); document.removeEventListener("keydown", onKey); };
    const onKey = (e) => { if (e.key === "Escape") close(); };
    document.addEventListener("keydown", onKey);
    return { close, back };
  }
  /* Confirm dialog: resolves true on the confirm button, false on cancel/Escape/backdrop. */
  function confirmDialog(title, text, okLabel, danger, extra) {
    return new Promise((resolve) => {
      const ok = el("button", { type: "button", className: danger ? "danger" : "primary", text: okLabel });
      const no = el("button", { type: "button", text: "Cancel" });
      const m = modal([el("h2", { text: title }), el("p", { text }), extra || null, el("div", { className: "actions" }, no, ok)]);
      let done = false; const fin = (v) => { if (!done) { done = true; m.close(); resolve(v); } };
      no.addEventListener("click", () => fin(false)); ok.addEventListener("click", () => fin(true));
      m.back.addEventListener("click", (e) => { if (e.target === m.back) fin(false); });
      document.addEventListener("keydown", function esc(e) { if (e.key === "Escape") { document.removeEventListener("keydown", esc); fin(false); } });
      no.focus();
    });
  }

  window.Kit = { modal, confirmDialog, $, el, clear, toast, api, post, bytes, num, dt, dshort, ago, dur, initTheme, chart, css, THEMES };
})();
