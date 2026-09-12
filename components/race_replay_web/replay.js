(function () {
  const payload = JSON.parse(document.getElementById("replayPayload").textContent);
  const root = document.getElementById("f1-replay-root");
  const canvas = document.getElementById("trackCanvas");
  const ctx = canvas.getContext("2d");
  const frames = payload.frames || [];
  const drivers = payload.drivers || {};
  const centerline = (payload.track && payload.track.centerline) || [];
  const inner = (payload.track && payload.track.inner_boundary) || [];
  const outer = (payload.track && payload.track.outer_boundary) || [];
  const drsZones = (payload.track && payload.track.drs_zones) || [];
  const startFinish = payload.track && payload.track.start_finish;
  const duration = payload.meta ? payload.meta.duration_seconds || 0 : 0;

  let playing = false;
  let currentTime = 0;
  let selectedDriver = Object.keys(drivers)[0] || "";
  let lastTick = performance.now();
  let speed = 1;
  let showLabels = true;
  let showDrs = true;
  let showLeaderboard = true;
  let transform = null;

  const tyreColors = {
    SOFT: "#ff3b30",
    MEDIUM: "#facc15",
    HARD: "#f5f7fa",
    INTERMEDIATE: "#2ccb70",
    WET: "#38bdf8",
    UNKNOWN: "#9da7b4",
  };

  const playBtn = document.getElementById("playPause");
  const timeline = document.getElementById("timeline");
  const speedSelect = document.getElementById("speedSelect");
  const labelsToggle = document.getElementById("labelsToggle");
  const drsToggle = document.getElementById("drsToggle");
  const lbToggle = document.getElementById("leaderboardToggle");
  const sidePanel = document.getElementById("sidePanel");

  function fmtTime(sec) {
    sec = Math.max(0, Number(sec) || 0);
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }

  function resizeCanvas() {
    const rect = canvas.getBoundingClientRect();
    const ratio = window.devicePixelRatio || 1;
    canvas.width = Math.max(1, Math.floor(rect.width * ratio));
    canvas.height = Math.max(1, Math.floor(rect.height * ratio));
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    buildTransform();
  }

  function allPoints() {
    return [...centerline, ...inner, ...outer].filter((p) => p && p.length >= 2);
  }

  function buildTransform() {
    const pts = allPoints();
    if (!pts.length) return;
    const xs = pts.map((p) => p[0]);
    const ys = pts.map((p) => p[1]);
    const minX = Math.min(...xs), maxX = Math.max(...xs);
    const minY = Math.min(...ys), maxY = Math.max(...ys);
    const rect = canvas.getBoundingClientRect();
    const pad = 20;
    const scale = Math.min((rect.width - pad * 2) / Math.max(1, maxX - minX), (rect.height - pad * 2) / Math.max(1, maxY - minY));
    transform = {
      minX,
      minY,
      scale,
      offX: (rect.width - (maxX - minX) * scale) / 2,
      offY: (rect.height - (maxY - minY) * scale) / 2,
      height: rect.height,
    };
  }

  function mapPoint(p) {
    if (!transform || !p) return [0, 0];
    return [
      transform.offX + (p[0] - transform.minX) * transform.scale,
      transform.height - (transform.offY + (p[1] - transform.minY) * transform.scale),
    ];
  }

  function drawPath(points, style, width, close = false) {
    if (!points || points.length < 2) return;
    ctx.beginPath();
    const first = mapPoint(points[0]);
    ctx.moveTo(first[0], first[1]);
    for (let i = 1; i < points.length; i += 1) {
      const p = mapPoint(points[i]);
      ctx.lineTo(p[0], p[1]);
    }
    if (close) ctx.closePath();
    ctx.strokeStyle = style;
    ctx.lineWidth = width;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.stroke();
  }

  function frameAt(t) {
    if (!frames.length) return [{ t: 0, drivers: {} }, { t: 0, drivers: {} }, 0];
    if (t <= frames[0].t) return [frames[0], frames[0], 0];
    for (let i = 0; i < frames.length - 1; i += 1) {
      if (frames[i].t <= t && t <= frames[i + 1].t) {
        const span = Math.max(0.001, frames[i + 1].t - frames[i].t);
        return [frames[i], frames[i + 1], (t - frames[i].t) / span];
      }
    }
    const last = frames[frames.length - 1];
    return [last, last, 0];
  }

  function lerp(a, b, k) {
    if (a == null) return b;
    if (b == null) return a;
    return a + (b - a) * k;
  }

  function driverSnapshot(code, a, b, k) {
    const da = a.drivers ? a.drivers[code] : null;
    const db = b.drivers ? b.drivers[code] : null;
    const d = da || db;
    if (!d) return null;
    return {
      ...d,
      x: lerp(da && da.x, db && db.x, k),
      y: lerp(da && da.y, db && db.y, k),
      speed: Math.round(lerp(da && da.speed, db && db.speed, k) || 0),
      throttle: Math.round(lerp(da && da.throttle, db && db.throttle, k) || 0),
      brake: Boolean((db || da).brake),
      gear: Math.round(lerp(da && da.gear, db && db.gear, k) || 0),
      position: Math.round(lerp(da && da.position, db && db.position, k) || d.position || 0),
      lap: Math.round(lerp(da && da.lap, db && db.lap, k) || d.lap || 0),
    };
  }

  function drawTrack() {
    const rect = canvas.getBoundingClientRect();
    ctx.clearRect(0, 0, rect.width, rect.height);
    drawPath(centerline, "rgba(255,255,255,0.12)", 30);
    drawPath(centerline, "rgba(35,40,52,0.96)", 24);
    drawPath(inner, "rgba(245,247,250,0.36)", 2);
    drawPath(outer, "rgba(245,247,250,0.36)", 2);
    if (showDrs) {
      drsZones.forEach((zone) => drawPath(zone.points || [], "rgba(56,189,248,0.82)", 5));
    }
    if (startFinish) {
      const p = mapPoint(startFinish);
      ctx.strokeStyle = "#f5f7fa";
      ctx.lineWidth = 4;
      ctx.beginPath();
      ctx.moveTo(p[0] - 14, p[1] - 14);
      ctx.lineTo(p[0] + 14, p[1] + 14);
      ctx.stroke();
    }
  }

  function drawCars(a, b, k) {
    const occupiedLabels = [];
    Object.keys(drivers).forEach((code) => {
      const snap = driverSnapshot(code, a, b, k);
      if (!snap || snap.x == null || snap.y == null) return;
      const meta = drivers[code] || {};
      const p = mapPoint([snap.x, snap.y]);
      const selected = code === selectedDriver;
      ctx.beginPath();
      ctx.arc(p[0], p[1], selected ? 9 : 6, 0, Math.PI * 2);
      ctx.fillStyle = meta.color || "#e10600";
      ctx.fill();
      ctx.lineWidth = selected ? 3 : 1.5;
      ctx.strokeStyle = selected ? "#f5f7fa" : "rgba(255,255,255,0.66)";
      ctx.stroke();
      if (showLabels) {
        ctx.font = selected ? "800 13px Inter, sans-serif" : "700 11px Inter, sans-serif";
        const width = ctx.measureText(code).width + 10;
        const labelX = p[0] + 10;
        let labelY = p[1] - 8;
        let attempts = 0;
        while (
          attempts < 4 &&
          occupiedLabels.some((box) =>
            labelX < box.x + box.w &&
            labelX + width > box.x &&
            labelY - 14 < box.y + box.h &&
            labelY > box.y
          )
        ) {
          labelY += 15;
          attempts += 1;
        }
        if (selected || attempts < 4) {
          ctx.fillStyle = selected ? "rgba(9,11,16,0.88)" : "rgba(9,11,16,0.68)";
          ctx.fillRect(labelX - 3, labelY - 12, width, 16);
          ctx.fillStyle = "#f5f7fa";
          ctx.fillText(code, labelX + 2, labelY);
          occupiedLabels.push({ x: labelX - 3, y: labelY - 12, w: width, h: 16 });
        }
      }
    });
    if (a.safety_car || b.safety_car) {
      const sc = b.safety_car || a.safety_car;
      const p = mapPoint([sc.x, sc.y]);
      ctx.fillStyle = "#facc15";
      ctx.fillRect(p[0] - 8, p[1] - 8, 16, 16);
      ctx.fillStyle = "#090b10";
      ctx.font = "900 9px Inter, sans-serif";
      ctx.fillText("SC", p[0] - 6, p[1] + 3);
    }
  }

  function renderLeaderboard(a, b, k) {
    const rows = Object.keys(drivers)
      .map((code) => ({ code, snap: driverSnapshot(code, a, b, k) }))
      .filter((row) => row.snap)
      .sort((x, y) => (x.snap.position || 99) - (y.snap.position || 99));
    const el = document.getElementById("leaderboard");
    el.innerHTML = "";
    rows.forEach((row) => {
      const meta = drivers[row.code] || {};
      const d = row.snap;
      const div = document.createElement("div");
      div.className = "leader-row" + (row.code === selectedDriver ? " selected" : "");
      div.innerHTML = `<b>${d.position || "-"}</b><span class="driver-code">${row.code}</span><span class="driver-gap">${d.gap || ""}</span><span class="tyre" style="color:${tyreColors[d.tyre] || tyreColors.UNKNOWN}" title="${d.tyre || "UNKNOWN"}"></span>`;
      div.onclick = () => { selectedDriver = row.code; render(); };
      el.appendChild(div);
    });
  }

  function renderDriverCard(a, b, k) {
    const meta = drivers[selectedDriver] || {};
    const d = driverSnapshot(selectedDriver, a, b, k) || {};
    document.getElementById("driverCard").innerHTML = `
      <h3>${selectedDriver || "-"}</h3>
      <div class="driver-meta">${meta.name || ""}<br>${meta.team || ""}</div>
      <div class="driver-grid">
        <div class="stat"><span>Position</span><b>${d.position || "-"}</b></div>
        <div class="stat"><span>Lap</span><b>${d.lap || "-"}</b></div>
        <div class="stat"><span>Speed</span><b>${d.speed || 0} km/h</b></div>
        <div class="stat"><span>Gear</span><b>${d.gear || "-"}</b></div>
        <div class="stat"><span>Throttle</span><b>${d.throttle || 0}%</b></div>
        <div class="stat"><span>Brake</span><b>${d.brake ? "ON" : "OFF"}</b></div>
        <div class="stat"><span>Tyre</span><b>${d.tyre || "-"}</b></div>
        <div class="stat"><span>DRS</span><b>${d.drs_active ? "ACTIVE" : (d.drs_raw ?? "-")}</b></div>
      </div>
    `;
  }

  function render() {
    const [a, b, k] = frameAt(currentTime);
    drawTrack();
    drawCars(a, b, k);
    const status = b.track_status || a.track_status || "GREEN";
    document.getElementById("trackStatus").textContent = status;
    document.getElementById("trackStatus").style.color = status.includes("SC") || status.includes("YELLOW") ? "#facc15" : "#2ccb70";
    document.getElementById("elapsed").textContent = fmtTime(currentTime);
    document.getElementById("totalTime").textContent = fmtTime(duration);
    document.getElementById("currentLap").textContent = b.lap || a.lap || "-";
    timeline.value = duration ? Math.round((currentTime / duration) * 1000) : 0;
    sidePanel.classList.toggle("leaderboard-hidden", !showLeaderboard);
    if (showLeaderboard) renderLeaderboard(a, b, k);
    renderDriverCard(a, b, k);
  }

  function tick(now) {
    const dt = (now - lastTick) / 1000;
    lastTick = now;
    if (playing) {
      currentTime = Math.min(duration, currentTime + dt * speed);
      if (currentTime >= duration) playing = false;
      playBtn.textContent = playing ? "Pause" : "Play";
    }
    render();
    requestAnimationFrame(tick);
  }

  playBtn.onclick = () => { playing = !playing; playBtn.textContent = playing ? "Pause" : "Play"; root.focus(); };
  document.getElementById("restart").onclick = () => { currentTime = 0; playing = false; playBtn.textContent = "Play"; };
  document.getElementById("back10").onclick = () => { currentTime = Math.max(0, currentTime - 10); };
  document.getElementById("forward10").onclick = () => { currentTime = Math.min(duration, currentTime + 10); };
  speedSelect.onchange = () => { speed = Number(speedSelect.value) || 1; };
  labelsToggle.onchange = () => { showLabels = labelsToggle.checked; };
  drsToggle.onchange = () => { showDrs = drsToggle.checked; };
  lbToggle.onchange = () => { showLeaderboard = lbToggle.checked; };
  timeline.oninput = () => { currentTime = (Number(timeline.value) / 1000) * duration; };
  document.getElementById("fitTrack").onclick = () => { buildTransform(); render(); };
  document.getElementById("fullscreen").onclick = () => {
    if (root.requestFullscreen) root.requestFullscreen();
  };
  root.addEventListener("keydown", (event) => {
    if (event.code === "Space") { event.preventDefault(); playBtn.click(); }
    if (event.code === "ArrowLeft") currentTime = Math.max(0, currentTime - 10);
    if (event.code === "ArrowRight") currentTime = Math.min(duration, currentTime + 10);
    if (event.key === "1") { speed = 0.5; speedSelect.value = "0.5"; }
    if (event.key === "2") { speed = 1; speedSelect.value = "1"; }
    if (event.key === "3") { speed = 2; speedSelect.value = "2"; }
    if (event.key === "4") { speed = 4; speedSelect.value = "4"; }
    if (event.key.toLowerCase() === "r") currentTime = 0;
    if (event.key.toLowerCase() === "d") { drsToggle.checked = !drsToggle.checked; showDrs = drsToggle.checked; }
    if (event.key.toLowerCase() === "l") { labelsToggle.checked = !labelsToggle.checked; showLabels = labelsToggle.checked; }
  });
  window.addEventListener("resize", resizeCanvas);
  resizeCanvas();
  requestAnimationFrame(tick);
})();
