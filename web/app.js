/* WifiScope UI. Text only (Kit.el); canvases for charts. */
(() => {
  "use strict";
  const { $, el, clear, toast, api, post, num, ago, initTheme, confirmDialog, chart, css } = window.Kit;
  initTheme($("#theme"));
  const S = { view: "networks", status: null, nets: [], connBssid: "", band: "", q: "", openOnly: false, sort: { key: "signal", dir: -1 }, scans: -1, channels: null, sig: null, minutes: 5, timer: null };

  const unit = () => (S.status && S.status.settings.units === "dbm" ? "dbm" : "percent");
  const sigText = (pct, dbm) => (unit() === "dbm" ? dbm + " dBm" : pct + "%");
  const sigClass = (p) => (p >= 65 ? "good" : p >= 40 ? "ok" : "poor");
  const hue = (s) => { let h = 0; for (const c of s || "?") h = (h * 31 + c.charCodeAt(0)) % 360; return h; };

  const TITLES = { networks: "Networks", channels: "Channels", signal: "Signal graph", settings: "Settings & about" };
  function show(v) {
    S.view = v;
    document.querySelectorAll(".nav-btn").forEach((b) => b.classList.toggle("active", b.dataset.view === v));
    $("#view-title").textContent = TITLES[v];
    for (const k of Object.keys(TITLES)) $("#v-" + k).hidden = k !== v;
    if (v === "channels") loadChannels(); else if (v === "signal") loadSignal(); else if (v === "settings") renderSettings();
  }
  document.querySelectorAll(".nav-btn").forEach((b) => b.addEventListener("click", () => show(b.dataset.view)));

  // ------------------------------------------------------------------ polling
  async function tick() {
    try {
      S.status = await api("/api/status");
      renderStatus();
      if (S.status.scans !== S.scans) { S.scans = S.status.scans; await loadNetworks(); if (S.view === "channels") await loadChannels(); }
      if (S.view === "signal") await loadSignal();
    } catch (e) { $("#status").textContent = "Cannot reach WifiScope: " + e.message; $("#status").className = "status error"; }
    clearTimeout(S.timer); S.timer = setTimeout(tick, document.hidden ? 8000 : 2000);
  }
  document.addEventListener("visibilitychange", () => { if (!document.hidden) tick(); });
  async function loadNetworks() { const r = await api("/api/networks"); S.nets = r.networks; S.connBssid = r.connected_bssid; renderNets(); }

  // ------------------------------------------------------------------ status, banners, cards
  function renderStatus() {
    const st = S.status;
    $("#status").className = "status";
    $("#status").textContent = st.scanning ? "Scanning…" : st.last_scan ? "Last scan " + ago(st.last_scan) : "Starting…";
    $("#side-text").textContent = st.state === "ok" ? (st.connected ? "Connected to " + st.connected.ssid : "Not connected") + " · " + st.aps + " access points" : st.state === "location" ? "Needs location access" : st.state === "no_adapter" ? "No Wi-Fi adapter" : st.state === "starting" ? "Starting…" : st.message || "Problem";
    $("#n-aps").textContent = st.aps ? String(st.aps) : "";
    $("#btn-scan").disabled = st.scanning;
    const box = clear($("#banners"));
    if (st.state === "location") {
      const open = el("button", { type: "button", className: "primary", text: "Open location settings" });
      open.addEventListener("click", async () => { try { const r = await post("/api/open-location", {}); if (!r.ok) toast(r.error, true); } catch (e) { toast(e.message, true); } });
      box.appendChild(el("div", { className: "notice warn" }, el("b", { text: "Windows is hiding nearby Wi-Fi networks from apps. " }), el("span", { text: "Turn on Settings → Privacy & security → Location → “Location services” and “Let desktop apps access your location”, then press Scan now. WifiScope only needs this permission to read the list of networks; it does not use your location." }), el("div", { className: "actions" }, open)));
    } else if (st.state === "no_adapter" || st.state === "service" || st.state === "error") {
      box.appendChild(el("div", { className: "notice danger" }, el("b", { text: st.message + " " }), st.state === "no_adapter" ? el("span", { text: "Check that the PC has a Wi-Fi adapter and that Wi-Fi / Airplane mode is off. Wired-only desktops have nothing to scan." }) : null, st.detail ? el("div", { className: "small muted", text: "Windows said: " + st.detail }) : null));
    } else if (st.state === "empty") {
      box.appendChild(el("p", { className: "notice", text: st.message }));
    }
    renderCards();
  }
  function renderCards() {
    const st = S.status, c = clear($("#cards"));
    const card = (l, v, sub, cls) => el("div", { className: "card" + (cls ? " " + cls : "") }, el("div", { className: "label", text: l }), el("div", { className: "value", text: v }), el("div", { className: "sub", text: sub || "" }));
    c.appendChild(card("Access points", num(st.aps), num(st.ssids) + " named network" + (st.ssids === 1 ? "" : "s") + (st.hidden ? ", " + st.hidden + " hidden" : "")));
    c.appendChild(card("Open networks", num(st.open), st.open ? "no password: be careful" : "none nearby"));
    const k = st.connected;
    c.appendChild(card("Connected", k ? k.ssid || "(hidden)" : "No", k ? sigText(k.signal, k.rssi) + " · ch " + k.channel + " · " + (k.band || "?") + " GHz" : "not on Wi-Fi"));
    const rec = S.channels && S.channels.bands ? S.channels.bands.filter((b) => b.recommended).map((b) => b.label.replace(" GHz", "") + ": ch " + b.recommended.ch).join("  ·  ") : "";
    c.appendChild(card("Best channels", rec || "see Channels", "least crowded per band", "compact"));
  }

  // ------------------------------------------------------------------ networks table
  document.querySelectorAll(".chips [data-band]").forEach((b) => b.addEventListener("click", () => { document.querySelectorAll(".chips [data-band]").forEach((x) => x.classList.toggle("on", x === b)); S.band = b.dataset.band; renderNets(); }));
  $("#q").addEventListener("input", () => { S.q = $("#q").value.trim().toLowerCase(); renderNets(); });
  $("#f-open").addEventListener("change", () => { S.openOnly = $("#f-open").checked; renderNets(); });
  document.querySelectorAll("button.th").forEach((b) => b.addEventListener("click", () => {
    const k = b.dataset.sort; S.sort = { key: k, dir: S.sort.key === k ? -S.sort.dir : (k === "signal" ? -1 : 1) }; renderNets();
  }));
  function renderNets() {
    document.querySelectorAll("button.th").forEach((b) => { const on = b.dataset.sort === S.sort.key; b.className = "th" + (on ? " sorted" + (S.sort.dir > 0 ? " asc" : "") : ""); });
    let rows = S.nets.filter((n) => (!S.band || n.band === S.band) && (!S.openOnly || n.open) && (!S.q || (n.ssid || "(hidden)").toLowerCase().includes(S.q) || n.bssid.includes(S.q)));
    const k = S.sort.key, d = S.sort.dir;
    rows.sort((a, b) => { const x = a[k], y = b[k]; const c = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y), undefined, { numeric: true }); return (c || b.signal - a.signal) * d; });
    const tb = clear($("#rows"));
    for (const n of rows) {
      const name = el("td", { className: "ssid", title: n.ssid || "(hidden network)" }, n.ssid || "(hidden)");
      if (n.hidden) name.classList.add("muted");
      if (n.bssid === S.connBssid) name.appendChild(el("span", { className: "badge you", text: "YOU" }));
      if (n.open) name.appendChild(el("span", { className: "badge open", text: "OPEN" }));
      const fill = el("span", { className: sigClass(n.signal) }); fill.style.width = n.signal + "%";
      const sig = el("td", {}, el("span", { className: "sig" }, el("span", { className: "bar" }, fill), el("span", { text: sigText(n.signal, n.dbm) })));
      tb.appendChild(el("tr", { className: n.bssid === S.connBssid ? "me" : "" }, name, el("td", { className: "mono", text: n.bssid }), sig, el("td", { text: String(n.channel) }), el("td", { text: n.band + " GHz" }),
        el("td", { className: n.open ? "sec-open" : "", text: n.security }), el("td", { text: n.gen || n.radio || "" })));
    }
    const none = !rows.length, st = S.status;
    $("#empty").hidden = !none;
    $("#empty").textContent = !S.nets.length ? (st && st.state === "ok" ? "No networks." : st && st.state !== "starting" ? "No networks to show. See the message above." : "Scanning…") : "No networks match the filter.";
  }

  // ------------------------------------------------------------------ channels
  async function loadChannels() { try { S.channels = await api("/api/channels"); renderBands(); renderCards(); } catch (e) { toast(e.message, true); } }
  function renderBands() {
    const box = clear($("#bands"));
    if (!S.channels) return;
    for (const b of S.channels.bands) {
      const p = el("div", { className: "panel band-panel" });
      p.appendChild(el("h2", {}, b.label, el("span", { className: "small muted", text: b.seen ? num(b.ap_count) + " access point" + (b.ap_count === 1 ? "" : "s") : "" })));
      if (!b.seen) { p.appendChild(el("p", { className: "muted", text: "No networks seen on " + b.label + (b.band === "6" ? " (needs a Wi-Fi 6E/7 adapter and router)." : ". Your adapter may not support this band, or nothing nearby uses it.") })); box.appendChild(p); continue; }
      if (b.recommended) {
        const r = b.recommended;
        p.appendChild(el("p", { className: "rec" }, el("b", { text: "Recommended: channel " + r.ch }), " — " + r.reason, r.alternatives.length ? el("span", { className: "alts", text: "  Next best: " + r.alternatives.map((a) => "ch " + a.ch).join(", ") + "." }) : null));
      }
      const cv = el("canvas", { className: "arcs", height: "230", "aria-label": b.label + " channel chart" });
      p.appendChild(cv); box.appendChild(p);
      drawBand(cv, b);
    }
  }
  function drawBand(canvas, b) {
    const dpr = window.devicePixelRatio || 1, w = canvas.clientWidth || 800, h = canvas.clientHeight || 230;
    canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
    const g = canvas.getContext("2d"); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, w, h);
    const chans = b.channels.map((r) => r.ch), n = chans.length, padL = 36, padR = 14, padT = 18, padB = 24, pw = w - padL - padR, ph = h - padT - padB;
    const wide = b.band === "2.4", half = wide ? 2 : 0.55, margin = wide ? 2.2 : 0.8;
    const X = (i) => padL + ((i + margin) / (n - 1 + 2 * margin)) * pw, Y = (pct) => padT + ph - (pct / 100) * ph;
    const idx = new Map(chans.map((c, i) => [c, i]));
    g.font = "11px Segoe UI, system-ui, sans-serif"; g.strokeStyle = css("--grid"); g.fillStyle = css("--muted"); g.lineWidth = 1; g.textAlign = "right";
    for (const v of [0, 25, 50, 75, 100]) { const y = Math.round(Y(v)) + 0.5; g.beginPath(); g.moveTo(padL, y); g.lineTo(w - padR, y); g.stroke(); const dbm = Math.round(v / 2 - 100); g.fillText(unit() === "dbm" ? String(dbm) : v + "%", padL - 5, y + 3); }
    g.textAlign = "center";
    chans.forEach((c, i) => { if (n <= 32 || i % 4 === 0 || (b.recommended && c === b.recommended.ch) || (b.current && c === b.current.ch)) g.fillText(String(c), X(i), h - 8); });
    if (b.recommended && idx.has(b.recommended.ch)) {
      const i = idx.get(b.recommended.ch), x0 = X(i - half), x1 = X(i + half);
      g.fillStyle = css("--ok"); g.globalAlpha = 0.14; g.fillRect(x0, padT, x1 - x0, ph); g.globalAlpha = 1;
      g.fillStyle = css("--ok"); g.fillText("best", X(i), padT - 5);
    }
    if (b.current && idx.has(b.current.ch)) {
      const x = X(idx.get(b.current.ch)); g.strokeStyle = css("--accent-2"); g.setLineDash([5, 4]); g.beginPath(); g.moveTo(x, padT); g.lineTo(x, padT + ph); g.stroke(); g.setLineDash([]);
      g.fillStyle = css("--accent-2"); g.fillText("you", x, padT + ph + 0); 
    }
    const aps = b.aps.slice().sort((a, c) => a.signal - c.signal);
    for (const a of aps) {
      if (!idx.has(a.channel)) continue;
      const i = idx.get(a.channel), cx = X(i), x0 = X(i - half), x1 = X(i + half), top = Y(a.signal), base = Y(0), color = "hsl(" + hue(a.ssid) + " 70% 58%)";
      const mine = S.connBssid === a.bssid;
      g.beginPath(); g.moveTo(x0, base); g.bezierCurveTo(x0 + (cx - x0) * 0.35, base, cx - (cx - x0) * 0.4, top, cx, top); g.bezierCurveTo(cx + (x1 - cx) * 0.4, top, x1 - (x1 - cx) * 0.35, base, x1, base);
      g.globalAlpha = 0.28; g.fillStyle = color; g.fill(); g.globalAlpha = 1; g.strokeStyle = color; g.lineWidth = mine ? 3 : 1.6; g.stroke();
      g.fillStyle = css("--text"); g.textAlign = "center"; g.font = (mine ? "bold " : "") + "11px Segoe UI, system-ui, sans-serif";
      const label = (a.ssid || "(hidden)").slice(0, 18); g.fillText(label, cx, Math.max(padT + 8, top - 4));
    }
  }

  // ------------------------------------------------------------------ signal graph
  document.querySelectorAll(".chips [data-min]").forEach((b) => b.addEventListener("click", () => { document.querySelectorAll(".chips [data-min]").forEach((x) => x.classList.toggle("on", x === b)); S.minutes = Number(b.dataset.min); loadSignal(); }));
  async function loadSignal() {
    try { S.sig = await api("/api/signal?minutes=" + S.minutes); } catch (e) { return; }
    renderSignal();
  }
  function renderSignal() {
    const r = S.sig, c = r.connected, card = clear($("#conn-card"));
    if (!c) {
      card.appendChild(el("h2", { text: "Not connected to Wi-Fi" })); card.appendChild(el("p", { className: "muted", text: r.state === "ok" || r.state === "empty" ? "Connect to a network to see its live signal here." : "Wi-Fi is not available right now. See the Networks page for details." }));
    } else {
      card.appendChild(el("h2", { text: c.ssid || "(hidden network)" }));
      const kv = (k, v) => el("div", {}, el("div", { className: "k", text: k }), el("div", { className: "v", text: v == null || v === "" ? "—" : String(v) }));
      card.appendChild(el("div", { className: "conn-grid" }, kv("Signal now", sigText(c.signal, c.rssi)), kv("Channel", c.channel + (c.band ? " (" + c.band + " GHz)" : "")), kv("Access point", c.bssid), kv("Wi-Fi", (c.gen || c.radio) + (c.radio && c.gen ? " · " + c.radio : "")),
        kv("Link speed", c.rx != null ? num(c.rx, 1) + " Mbps down / " + num(c.tx, 1) + " up" : null), kv("Security", c.security), kv("Adapter", c.description || c.name)));
    }
    const pts = r.points, dbm = unit() === "dbm", val = (p) => (p.signal == null ? null : dbm ? (p.rssi != null ? p.rssi : Math.round(p.signal / 2 - 100)) : p.signal);
    const marks = []; let prev = null;
    for (const p of pts) { if (p.bssid && prev && p.bssid !== prev) marks.push([p.t, css("--warn")]); if (p.bssid) prev = p.bssid; }
    const cv = $("#sig-chart");
    chart(cv, [{ name: "Signal", color: css("--accent-2"), points: pts.filter((p) => p.signal != null).map((p) => [p.t, val(p)]) }],
      { yMin: dbm ? -100 : 0, yMax: dbm ? -30 : 100, tMin: pts.length ? Math.min(pts[0].t, Date.now() / 1000 - r.minutes * 60) : Date.now() / 1000 - r.minutes * 60, tMax: Date.now() / 1000, marks, maxGap: 8, fmtY: (v) => Math.round(v) + (dbm ? " dBm" : "%"),
        hline: dbm ? { v: -80, label: "weak", color: css("--danger") } : { v: 40, label: "weak below 40%", color: css("--danger") }, empty: "No signal samples yet" });
    const vals = pts.map(val).filter((v) => v != null);
    $("#sig-stats").textContent = vals.length ? "Min " + Math.min(...vals) + (dbm ? " dBm" : "%") + " · Average " + Math.round(vals.reduce((a, b) => a + b, 0) / vals.length) + (dbm ? " dBm" : "%") + " · Max " + Math.max(...vals) + (dbm ? " dBm" : "%") + " · " + vals.length + (vals.length === 1 ? " sample · " : " samples · ") + marks.length + " roam" + (marks.length === 1 ? "" : "s") : "";
  }

  // ------------------------------------------------------------------ settings, scan, quit
  function renderSettings() { const st = S.status; if (!st) return; $("#o-interval").value = String(st.settings.interval); $("#o-units").value = st.settings.units; }
  async function save(body) { try { await post("/api/settings", body); toast("Saved"); await tick(); renderNets(); if (S.view === "channels") renderBands(); } catch (e) { toast(e.message, true); } }
  $("#o-interval").addEventListener("change", () => save({ interval: Number($("#o-interval").value) }));
  $("#o-units").addEventListener("change", () => save({ units: $("#o-units").value }));
  $("#btn-scan").addEventListener("click", async () => {
    try { const r = await post("/api/scan", {}); if (!r.started) toast("A scan just ran. Give it a few seconds."); } catch (e) { toast(e.message, true); }
    setTimeout(tick, 300);
  });
  $("#btn-quit").addEventListener("click", async () => {
    if (await confirmDialog("Quit WifiScope?", "Scanning stops and this window closes.", "Quit", true)) { try { await post("/api/quit", {}); } catch { /* going away */ } document.body.textContent = "WifiScope has quit. You can close this window."; }
  });
  window.addEventListener("resize", () => { if (S.view === "channels") renderBands(); else if (S.view === "signal" && S.sig) renderSignal(); });
  tick();
})();
