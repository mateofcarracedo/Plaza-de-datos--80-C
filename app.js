(() => {
  "use strict";

  const C = CONFIG;
  let umbral = C.UMBRAL_ALARMA;
  let margen = C.MARGEN_AVISO;

  const $ = (s) => document.querySelector(s);
  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  };
  const setText = (node, txt) => { if (node.textContent !== txt) node.textContent = txt; };

  const fmtNum = new Intl.NumberFormat("es-AR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const fmtTemp = (t) => `${fmtNum.format(t)}°C`;

  /* ============================================================
     Estado
     ============================================================ */
  const equipos = new Map(); // id -> {id, numero, grupo, piso, estado, temp, ts}
  const rows = new Map();    // id -> referencias DOM
  let structureDirty = false;
  let currentAlarms = 0;

  function getEquipo(id) {
    let e = equipos.get(id);
    if (!e) {
      e = { id, numero: id, grupo: "—", piso: "", estado: "funcionando", temp: null, ts: 0 };
      equipos.set(id, e);
      structureDirty = true;
    }
    return e;
  }

  function lista() {
    return [...equipos.values()].sort((a, b) =>
      (Number(a.numero) - Number(b.numero)) ||
      (Number(a.piso) - Number(b.piso)) ||
      a.id.localeCompare(b.id));
  }

  function nivel(e) {
    if (e.estado !== "funcionando") return "off";
    if (e.temp == null || Number.isNaN(e.temp) ||
        (C.STALE_MS && Date.now() - e.ts > C.STALE_MS)) return "nodata";
    if (e.temp > umbral) return "alarm";
    if (e.temp > umbral - margen) return "warn";
    return "ok";
  }

  /* ============================================================
     Render: Inicio
     ============================================================ */
  const COLS = ["Número de Equipo", "Grupo", "Piso", "Temperatura"];

  function buildCol(items) {
    const col = el("div", "col");
    const head = el("div", "row row--head");
    COLS.forEach((h, i) => head.append(el("div", `cell c${i}`, h)));
    col.append(head);

    items.forEach((e) => {
      const row = el("div", "row");
      const num = el("div", "cell c0");
      const grupo = el("div", "cell c1");
      const piso = el("div", "cell c2");
      const temp = el("div", "cell c3 temp");
      row.append(num, grupo, piso, temp);
      col.append(row);
      rows.set(e.id, { row, num, grupo, piso, temp });
    });
    return col;
  }

  function renderGrid() {
    structureDirty = false;
    const items = lista();
    const half = Math.ceil(items.length / 2);
    const grid = $("#grid");
    grid.style.setProperty("--rows", Math.max(half, 1));
    rows.clear();
    grid.replaceChildren(buildCol(items.slice(0, half)), buildCol(items.slice(half)));
    renderHistList();
  }

  function paintRow(e) {
    const r = rows.get(e.id);
    if (!r) return;
    const lvl = nivel(e);
    r.row.className = `row row--${lvl}`;
    r.temp.className = `cell c3 temp temp--${lvl}`;
    setText(r.num, String(e.numero));
    setText(r.grupo, String(e.grupo));
    setText(r.piso, String(e.piso));
    setText(r.temp, lvl === "off" ? "—" : lvl === "nodata" ? "Sin datos" : fmtTemp(e.temp));
  }

  function refreshAll() {
    if (structureDirty) renderGrid();
    let alarms = 0;
    for (const e of equipos.values()) {
      paintRow(e);
      if (nivel(e) === "alarm") alarms++;
    }
    updateAlarmUI(alarms);
  }

  let scheduled = false;
  function schedule() {
    if (scheduled) return;
    scheduled = true;
    setTimeout(() => { scheduled = false; refreshAll(); }, 0);
  }

  /* ============================================================
     Alarma: indicador + sonido
     ============================================================ */
  const baseTitle = document.title;
  let audioCtx = null;
  let soundOn = false;
  let userMuted = false;
  let soundTimer = null;

  function ensureAudio() {
    if (!audioCtx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (AC) audioCtx = new AC();
    }
    if (audioCtx && audioCtx.state === "suspended") audioCtx.resume();
    return audioCtx;
  }

  function beep() {
    if (!audioCtx || audioCtx.state !== "running") return;
    const t0 = audioCtx.currentTime;
    [880, 660].forEach((freq, i) => {
      const o = audioCtx.createOscillator();
      const g = audioCtx.createGain();
      const s = t0 + i * 0.28;
      o.type = "square";
      o.frequency.value = freq;
      g.gain.setValueAtTime(0.0001, s);
      g.gain.exponentialRampToValueAtTime(0.25, s + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, s + 0.25);
      o.connect(g).connect(audioCtx.destination);
      o.start(s);
      o.stop(s + 0.27);
    });
  }

  function syncSound() {
    const should = currentAlarms > 0 && soundOn;
    if (should && !soundTimer) {
      beep();
      soundTimer = setInterval(beep, 1200);
    } else if (!should && soundTimer) {
      clearInterval(soundTimer);
      soundTimer = null;
    }
  }

  function setSound(on) {
    if (on && !ensureAudio()) return;
    soundOn = on;
    updateSoundBtn();
    syncSound();
  }

  function updateSoundBtn() {
    const b = $("#sound-btn");
    b.textContent = soundOn ? "🔔 Sonido activado" : "🔇 Activar sonido";
    b.classList.toggle("btn--attn", !soundOn && currentAlarms > 0);
  }

  function updateAlarmUI(n) {
    currentAlarms = n;
    const badge = $("#alarm-summary");
    badge.hidden = n === 0;
    badge.textContent = n === 1 ? "⚠ 1 EQUIPO EN ALARMA" : `⚠ ${n} EQUIPOS EN ALARMA`;
    document.title = n > 0 ? `🚨 (${n}) ALARMA — ${baseTitle}` : baseTitle;
    updateSoundBtn();
    syncSound();
  }

  // Los navegadores exigen un gesto del usuario para reproducir audio:
  // se activa solo con el primer clic/tecla, salvo que lo silencien a mano.
  function onFirstGesture(e) {
    if (e.target.closest && e.target.closest("#sound-btn")) return;
    removeGestureListeners();
    if (!userMuted) setSound(true);
  }
  function removeGestureListeners() {
    window.removeEventListener("pointerdown", onFirstGesture);
    window.removeEventListener("keydown", onFirstGesture);
  }
  window.addEventListener("pointerdown", onFirstGesture);
  window.addEventListener("keydown", onFirstGesture);

  $("#sound-btn").addEventListener("click", () => {
    removeGestureListeners();
    userMuted = soundOn;       // si estaba activo, ahora lo silencian
    setSound(!soundOn);
  });

  /* ============================================================
     Conexión / mensajes MQTT
     ============================================================ */
  function setConn(mode) {
    const c = $("#conn");
    c.className = `conn conn--${mode}`;
    c.textContent = mode === "on" ? "● Conectado" : mode === "demo" ? "● Modo demo" : "● Sin conexión";
  }

  function parseTemp(text) {
    const s = text.trim();
    try {
      const j = JSON.parse(s);
      if (typeof j === "number") return j;
      if (j && typeof j === "object") return Number(j.temp ?? j.temperatura ?? j.value);
    } catch { /* no era JSON */ }
    return parseFloat(s.replace(",", "."));
  }

  function handleMessage(topic, text) {
    const p = topic.split("/");
    if (p[0] !== C.TOPIC_BASE) return;

    if (p.length === 2 && p[1] === "config") {
      try {
        const j = JSON.parse(text);
        if (Number.isFinite(Number(j.umbral))) umbral = Number(j.umbral);
        if (Number.isFinite(Number(j.margen))) margen = Number(j.margen);
        schedule();
      } catch { /* ignorar */ }
      return;
    }
    if (p.length !== 3) return;

    const [, id, campo] = p;
    const e = getEquipo(id);

    if (campo === "temperatura") {
      const t = parseTemp(text);
      if (Number.isFinite(t)) { e.temp = t; e.ts = Date.now(); }
    } else if (campo === "estado") {
      let v = text.trim();
      try { const j = JSON.parse(v); v = typeof j === "object" && j ? j.estado : String(j); } catch { /* texto plano */ }
      e.estado = ["funcionando", "1", "true", "on"].includes(String(v).trim().toLowerCase())
        ? "funcionando" : "no funcionando";
    } else if (campo === "info") {
      try {
        const j = JSON.parse(text);
        if (j.numero != null) e.numero = j.numero;
        if (j.grupo != null) e.grupo = j.grupo;
        if (j.piso != null) e.piso = j.piso;
        structureDirty = true;
      } catch { /* ignorar */ }
    }
    schedule();
  }

  function startMqtt() {
    if (typeof mqtt === "undefined") {
      console.error("No se pudo cargar mqtt.js (¿sin acceso a la CDN?)");
      setConn("off");
      return;
    }
    const client = mqtt.connect(C.MQTT_URL, {
      username: C.MQTT_USER || undefined,
      password: C.MQTT_PASS || undefined,
      reconnectPeriod: 3000,
      clientId: "freezers_web_" + Math.random().toString(16).slice(2, 8),
    });
    client.on("connect", () => {
      setConn("on");
      client.subscribe(`${C.TOPIC_BASE}/+/+`);
      client.subscribe(`${C.TOPIC_BASE}/config`);
    });
    client.on("close", () => setConn("off"));
    client.on("error", (err) => console.error("MQTT:", err));
    client.on("message", (topic, payload) => handleMessage(topic, payload.toString()));
  }

  async function loadEquipos() {
    if (!C.API_EQUIPOS) return;
    try {
      const r = await fetch(C.API_EQUIPOS);
      if (!r.ok) throw new Error("HTTP " + r.status);
      const list = await r.json();
      list.forEach((x) => {
        const e = getEquipo(String(x.id));
        if (x.numero != null) e.numero = x.numero;
        if (x.grupo != null) e.grupo = x.grupo;
        if (x.piso != null) e.piso = x.piso;
        if (x.estado != null) e.estado = String(x.estado).toLowerCase() === "funcionando" ? "funcionando" : "no funcionando";
      });
      structureDirty = true;
      schedule();
    } catch (err) {
      console.warn("No se pudo cargar la lista de equipos:", err);
    }
  }

  /* ============================================================
     Modo demo
     ============================================================ */
  const DEMO_EQUIPOS = [
    [60, "Pérez", 3], [59, "Kukiernik", 2], [58, "González", 1], [57, "Rodríguez", 0], [56, "Fernández", -1],
    [55, "Kukiernik", 3], [54, "López", 2], [53, "Martínez", 1], [52, "Sánchez", 0], [51, "Romero", -1],
    [50, "Díaz", 3], [60, "Torres", 1], [59, "Álvarez", 0], [58, "Ruiz", -1], [57, "Gómez", 2],
    [56, "Benítez", 3], [55, "Acosta", 0], [54, "Herrera", -1], [53, "Medina", 2], [52, "Silva", 1],
  ];
  const DEMO_OFF = new Set([3, 14]);              // índices "no funcionando"
  const DEMO_TARGET = { 6: -72.5, 9: -66 };       // 6 = amarillo, 9 = alarma

  function startDemo() {
    const target = {};
    DEMO_EQUIPOS.forEach(([numero, grupo, piso], i) => {
      const id = "eq" + String(i + 1).padStart(2, "0");
      const e = getEquipo(id);
      target[id] = DEMO_TARGET[i] ?? -79.5;
      Object.assign(e, {
        numero, grupo, piso,
        estado: DEMO_OFF.has(i) ? "no funcionando" : "funcionando",
        temp: target[id] + (Math.random() - 0.5),
        ts: Date.now(),
      });
    });
    setConn("demo");
    schedule();

    setInterval(() => {
      for (const e of equipos.values()) {
        if (e.estado !== "funcionando") continue;
        e.temp += (target[e.id] - e.temp) * 0.15 + (Math.random() - 0.5) * 0.4;
        e.ts = Date.now();
      }
      schedule();
    }, 2000);
  }

  /* ============================================================
     Historial
     ============================================================ */
  function renderHistList() {
    const ul = $("#hist-ul");
    ul.replaceChildren();
    lista().forEach((e) => {
      const li = el("li");
      const a = el("a", e.estado === "funcionando" ? "" : "is-off", `${e.numero} (${e.grupo})`);
      a.href = "#historial/" + encodeURIComponent(e.id);
      li.append(a);
      ul.append(li);
    });
  }

  function mulberry32(a) {
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function demoHistory(id) {
    const seed = [...id].reduce((a, c) => (a * 31 + c.charCodeAt(0)) >>> 0, 7);
    const rnd = mulberry32(seed);
    const now = Date.now(), step = 5 * 60e3, N = 288; // 24 h cada 5 min
    const pts = [];
    let v = -80 + (rnd() - 0.5) * 2;
    for (let i = N - 1; i >= 0; i--) {
      v += (-79.5 - v) * 0.1 + (rnd() - 0.5) * 0.6;
      pts.push({ t: now - i * step, temp: v + Math.sin(i / 12) * 0.4 });
    }
    const e = equipos.get(id);
    if (e && e.temp != null && e.temp > umbral - margen) { // empalmar con la temperatura actual
      const k = 40, from = pts.length - k, base = pts[from].temp;
      for (let i = from; i < pts.length; i++) pts[i].temp = base + (e.temp - base) * ((i - from) / (k - 1));
    }
    return Promise.resolve(pts);
  }

  async function fetchHistorial(id) {
    if (C.DEMO) return demoHistory(id);
    const url = C.API_HISTORIAL.replace("{id}", encodeURIComponent(id));
    const r = await fetch(url);
    if (!r.ok) throw new Error("HTTP " + r.status);
    const data = await r.json();
    return data
      .map((p) => {
        let t = typeof p.t === "number" ? p.t : Date.parse(p.t);
        if (t < 1e12) t *= 1000; // segundos -> ms
        return { t, temp: Number(p.temp) };
      })
      .filter((p) => Number.isFinite(p.t) && Number.isFinite(p.temp))
      .sort((a, b) => a.t - b.t);
  }

  /* ---------- Gráfico (canvas, sin dependencias) ---------- */
  const canvas = $("#chart");
  let chartPts = [];
  let hoverIdx = -1;
  let geom = null;
  const M = { l: 62, r: 20, t: 20, b: 38 };

  function drawChart() {
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (!w || !h) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    const g = canvas.getContext("2d");
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    if (!chartPts.length) return;

    let tMin = Infinity, tMax = -Infinity, vMin = umbral, vMax = umbral;
    for (const p of chartPts) {
      if (p.t < tMin) tMin = p.t;
      if (p.t > tMax) tMax = p.t;
      if (p.temp < vMin) vMin = p.temp;
      if (p.temp > vMax) vMax = p.temp;
    }
    vMin -= 2; vMax += 2;
    const span = tMax - tMin || 1;
    const plotW = w - M.l - M.r, plotH = h - M.t - M.b;
    const X = (t) => M.l + ((t - tMin) / span) * plotW;
    const Y = (v) => M.t + (1 - (v - vMin) / (vMax - vMin)) * plotH;
    geom = { tMin, span, plotW, X, Y };

    g.font = "12px system-ui, sans-serif";
    g.lineWidth = 1;

    // grilla + eje Y
    g.fillStyle = "#8b95a5";
    g.strokeStyle = "#22304d";
    g.textAlign = "right";
    g.textBaseline = "middle";
    for (let i = 0; i <= 5; i++) {
      const v = vMin + ((vMax - vMin) * i) / 5, y = Y(v);
      g.beginPath(); g.moveTo(M.l, y); g.lineTo(w - M.r, y); g.stroke();
      g.fillText(fmtNum.format(v), M.l - 8, y);
    }

    // eje X
    const long = span > 36 * 3600e3;
    const fmtX = new Intl.DateTimeFormat("es-AR", long
      ? { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }
      : { hour: "2-digit", minute: "2-digit" });
    g.textAlign = "center";
    g.textBaseline = "top";
    for (let i = 0; i <= 5; i++) {
      const t = tMin + (span * i) / 5, x = X(t);
      g.beginPath(); g.moveTo(x, M.t); g.lineTo(x, h - M.b); g.stroke();
      g.fillText(fmtX.format(t), x, h - M.b + 8);
    }

    // umbral
    g.strokeStyle = "#ff3b30";
    g.setLineDash([6, 4]);
    g.beginPath(); g.moveTo(M.l, Y(umbral)); g.lineTo(w - M.r, Y(umbral)); g.stroke();
    g.setLineDash([]);
    g.fillStyle = "#ff3b30";
    g.textAlign = "left";
    g.textBaseline = "bottom";
    g.fillText(`Umbral ${fmtTemp(umbral)}`, M.l + 6, Y(umbral) - 3);

    // serie
    g.strokeStyle = "#4fc3f7";
    g.lineWidth = 2;
    g.beginPath();
    chartPts.forEach((p, i) => (i ? g.lineTo(X(p.t), Y(p.temp)) : g.moveTo(X(p.t), Y(p.temp))));
    g.stroke();

    // hover
    if (hoverIdx >= 0) {
      const p = chartPts[hoverIdx], x = X(p.t), y = Y(p.temp);
      g.strokeStyle = "rgba(255,255,255,.35)";
      g.lineWidth = 1;
      g.beginPath(); g.moveTo(x, M.t); g.lineTo(x, h - M.b); g.stroke();
      g.fillStyle = "#4fc3f7";
      g.beginPath(); g.arc(x, y, 4, 0, Math.PI * 2); g.fill();

      const label = `${new Intl.DateTimeFormat("es-AR", { dateStyle: "short", timeStyle: "short" }).format(p.t)}  ·  ${fmtTemp(p.temp)}`;
      g.font = "13px system-ui, sans-serif";
      const tw = g.measureText(label).width + 16;
      const bx = Math.min(Math.max(x - tw / 2, M.l), w - M.r - tw);
      const by = Math.max(y - 36, M.t);
      g.fillStyle = "#0b1220";
      g.strokeStyle = "#4fc3f7";
      g.fillRect(bx, by, tw, 24);
      g.strokeRect(bx, by, tw, 24);
      g.fillStyle = "#e8eef7";
      g.textAlign = "left";
      g.textBaseline = "middle";
      g.fillText(label, bx + 8, by + 12);
    }
  }

  canvas.addEventListener("pointermove", (ev) => {
    if (!chartPts.length || !geom) return;
    const x = ev.clientX - canvas.getBoundingClientRect().left;
    const t = geom.tMin + ((x - M.l) / geom.plotW) * geom.span;
    let best = 0, bd = Infinity;
    chartPts.forEach((p, i) => { const d = Math.abs(p.t - t); if (d < bd) { bd = d; best = i; } });
    hoverIdx = best;
    drawChart();
  });
  canvas.addEventListener("pointerleave", () => { hoverIdx = -1; drawChart(); });
  window.addEventListener("resize", () => { if (!$("#hist-detail").hidden) drawChart(); });

  function renderStats(pts) {
    let min = Infinity, max = -Infinity, sum = 0;
    pts.forEach((p) => { min = Math.min(min, p.temp); max = Math.max(max, p.temp); sum += p.temp; });
    const items = [
      ["Mínima", fmtTemp(min)],
      ["Máxima", fmtTemp(max)],
      ["Promedio", fmtTemp(sum / pts.length)],
      ["Última", fmtTemp(pts[pts.length - 1].temp)],
    ];
    const box = $("#hist-stats");
    box.replaceChildren();
    items.forEach(([k, v]) => {
      const d = el("div", "stat");
      d.append(el("b", "", v), el("span", "", k));
      box.append(d);
    });
  }

  let detailToken = 0;
  async function showDetail(id) {
    $("#hist-list").hidden = true;
    $("#hist-detail").hidden = false;
    const e = equipos.get(id);
    $("#hist-title").textContent = e ? `${e.numero} (${e.grupo})` : id;
    $("#hist-sub").textContent = e ? `Piso ${e.piso}` : "";
    const msg = $("#hist-msg");
    msg.hidden = false;
    msg.textContent = "Cargando historial…";
    $("#hist-stats").replaceChildren();
    chartPts = [];
    hoverIdx = -1;
    drawChart();

    const token = ++detailToken;
    try {
      const pts = await fetchHistorial(id);
      if (token !== detailToken) return;
      if (!pts.length) { msg.textContent = "No hay datos de historial para este equipo."; return; }
      msg.hidden = true;
      chartPts = pts;
      renderStats(pts);
      drawChart();
    } catch (err) {
      if (token !== detailToken) return;
      msg.textContent = `No se pudo cargar el historial (${err.message}).`;
    }
  }

  /* ============================================================
     Navegación por solapas (#inicio / #historial / #historial/<id>)
     ============================================================ */
  function route() {
    const [tab = "inicio", arg] = (location.hash.slice(1) || "inicio").split("/");
    const isHist = tab === "historial";
    $("#view-inicio").hidden = isHist;
    $("#view-historial").hidden = !isHist;
    document.querySelectorAll(".tab").forEach((a) =>
      a.classList.toggle("active", a.dataset.tab === (isHist ? "historial" : "inicio")));

    detailToken++; // cancela cargas pendientes
    if (isHist && arg) {
      showDetail(decodeURIComponent(arg));
    } else {
      $("#hist-list").hidden = false;
      $("#hist-detail").hidden = true;
    }
  }
  window.addEventListener("hashchange", route);

  /* ============================================================
     Inicio
     ============================================================ */
  renderGrid();
  route();
  setInterval(refreshAll, 1000); // detecta "Sin datos" y mantiene la alarma al día

  if (C.DEMO) {
    startDemo();
  } else {
    setConn("off");
    loadEquipos();
    startMqtt();
  }
})();
