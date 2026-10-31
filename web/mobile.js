"use strict";
// Afgooien – telefoonscherm: meekijken en pijlen corrigeren tijdens een potje.
// Koppelen: scan de QR-code op het hoofdscherm (knop 📱) of open http://<ip>:<poort>/m

const COLORS = ["#4f9cff", "#ff7043", "#3ecf8e", "#ba68c8", "#ffca28", "#26c6da",
                "#ec407a", "#9ccc65", "#8d6e63", "#78909c", "#ff8a80", "#b388ff"];
const SEG = [20, 1, 18, 4, 13, 6, 10, 15, 2, 17, 3, 19, 7, 16, 8, 11, 14, 9, 12, 5];
const R = { bullIn: 6.35, bullOut: 15.9, triIn: 99, triOut: 107, dblIn: 162, dblOut: 170 };
const NS = "http://www.w3.org/2000/svg";
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* */ } },
};

// ------------------------------------------------------------------- taal
const UI = window.AFGOOIEN_UI;
let LANG = "nl";
function t(key, p) {
  let v = (UI[LANG] || UI.nl)[key];
  if (v === undefined) v = UI.nl[key] !== undefined ? UI.nl[key] : key;
  if (Array.isArray(v)) v = v[p && p.n === 1 ? 0 : 1];
  return String(v).replace(/\{(\w+)\}/g, (m, k) => (p && k in p ? p[k] : m));
}
function applyI18n() {
  document.documentElement.lang = LANG;
  document.querySelectorAll("[data-i18n]").forEach((e) => { e.textContent = t(e.dataset.i18n); });
}

// ------------------------------------------------------------------ server
let S = null;
let sel = null;                          // geselecteerde pijl (index) om te corrigeren of in te voeren
let keysMode = store.get("afgooien.m.keys", false);
let mult = 1;
let alloc = {}, allocKey = null;

async function send(cmd) {
  try {
    const r = await fetch("/api/cmd", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cmd) });
    const j = await r.json();
    if (!j.ok) { $("mnotice").textContent = j.error; buzz(80); return false; }
    render(j.state);
    return true;
  } catch (e) {
    $("mnotice").textContent = t("no_conn");
    return false;
  }
}
const buzz = (ms) => { try { if (navigator.vibrate) navigator.vibrate(ms); } catch (e) { /* */ } };

function connect() {
  const es = new EventSource("/events");
  es.onmessage = (ev) => { $("moffline").classList.add("hidden"); $("mconn").classList.add("on"); render(JSON.parse(ev.data)); };
  es.onerror = () => { $("moffline").classList.remove("hidden"); $("mconn").classList.remove("on"); };
}

// ------------------------------------------------------------------- bord
function el(tag, attrs, parent) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs || {})) e.setAttribute(k, v);
  if (parent) parent.appendChild(e);
  return e;
}
const pt = (r, deg) => [r * Math.cos(deg * Math.PI / 180), -r * Math.sin(deg * Math.PI / 180)];
function sector(r1, r2, a1, a2) {
  const [x1, y1] = pt(r2, a1), [x2, y2] = pt(r2, a2), [x3, y3] = pt(r1, a2), [x4, y4] = pt(r1, a1);
  return `M${x1} ${y1}A${r2} ${r2} 0 0 1 ${x2} ${y2}L${x3} ${y3}A${r1} ${r1} 0 0 0 ${x4} ${y4}Z`;
}
const B = { own: {}, hl: {} };
function buildBoard() {
  const svg = $("mboard");
  el("circle", { r: 225.5, class: "boardedge" }, svg);
  SEG.forEach((num, i) => {
    const mid = 90 - i * 18, a1 = mid + 9, a2 = mid - 9, dark = i % 2 === 0;
    el("path", { d: sector(R.bullOut, R.triIn, a1, a2), class: dark ? "s-dark" : "s-light" }, svg);
    el("path", { d: sector(R.triIn, R.triOut, a1, a2), class: dark ? "r-red" : "r-green" }, svg);
    el("path", { d: sector(R.triOut, R.dblIn, a1, a2), class: dark ? "s-dark" : "s-light" }, svg);
    el("path", { d: sector(R.dblIn, R.dblOut, a1, a2), class: dark ? "r-red" : "r-green" }, svg);
    B.own[num] = el("path", { d: sector(173, 202, a1, a2), class: "ownring", fill: "#1a1f26" }, svg);
    B.hl[num] = el("path", { d: sector(R.bullOut, R.dblOut, a1, a2), class: "hl" }, svg);
    const [lx, ly] = pt(187.5, mid);
    el("text", { x: lx, y: ly, class: "lbl" }, svg).textContent = num;
  });
  el("circle", { r: R.bullOut, class: "r-green" }, svg);
  el("circle", { r: R.bullIn, class: "r-red" }, svg);
  for (const r of [R.bullIn, R.bullOut, R.triIn, R.triOut, R.dblIn, R.dblOut]) el("circle", { r, class: "wire" }, svg);
  B.bullhl = el("circle", { r: R.bullOut, class: "hl" }, svg);
  B.darts = el("g", {}, svg);
  bindLoupe(svg);
}

// --------------------------------------------------- inzoomen + vergrootglas
// Zoom: bij het kiezen van een pijl zoomt het bord in op die pijl; + / − om zelf te zoomen.
const ZOOMS = [1, 1.8, 2.8, 4];
let zoom = { lvl: 0, cx: 0, cy: 0 };
const autoZoom = () => store.get("afgooien.m.autozoom", true);
function setViewBox() {
  if (typeof vbAnim !== "undefined") vbAnim++;          // lopende zoom-animatie stoppen
  const half = 240 / ZOOMS[zoom.lvl];
  const lim = 240 - half;                               // niet buiten het bord schuiven
  zoom.cx = Math.max(-lim, Math.min(lim, zoom.cx));
  zoom.cy = Math.max(-lim, Math.min(lim, zoom.cy));
  $("mboard").setAttribute("viewBox", `${zoom.cx - half} ${zoom.cy - half} ${half * 2} ${half * 2}`);
  $("mzout").disabled = zoom.lvl === 0;
  $("mzin").disabled = zoom.lvl === ZOOMS.length - 1;
  $("mzlvl").textContent = zoom.lvl ? ZOOMS[zoom.lvl] + "×" : "";
  $("mzlvl").classList.toggle("hidden", !zoom.lvl);
  if (S && active()) updateBoard(S.current !== null ? S.players[S.current] : null);
}
function zoomTo(lvl, cx, cy) {
  zoom = { lvl: Math.max(0, Math.min(ZOOMS.length - 1, lvl)), cx: cx === undefined ? zoom.cx : cx, cy: cy === undefined ? zoom.cy : cy };
  if (!zoom.lvl) { zoom.cx = 0; zoom.cy = 0; }
  setViewBox();
}
// in- of uitzoomen op de geselecteerde pijl
function focusDart(i) {
  const d = S && S.darts[i];
  if (d && d.x !== undefined && autoZoom()) zoomTo(Math.max(zoom.lvl, 1), d.x * R.dblOut, -d.y * R.dblOut);
}

// Plaatsen: vinger op het bord = de pijl springt naar je vinger en schuift mee tot je loslaat.
// Houd je langer dan 0,7 s vast, dan zoomt het bord in rond je vinger: daarna beweegt de pijl
// veel fijner. Boven je vinger toont een vergrootglas het vak (bijv. "T5"). Loslaten = plaatsen.
const HOLD_MS = 700, HOLD_TOTAL = 3, LOUPE_ZOOM = 2.6;   // vasthouden: in totaal 3× ingezoomd
const EDGE = 0.13, EDGE_SPEED = 0.6;    // rand (deel van het bord) waar het beeld meeschuift; snelheid (bordbreedtes/s)
let loupeSvg = null, lastLbl = "";
function svgPoint(svg, x, y) {
  const p = svg.createSVGPoint();
  p.x = x; p.y = y;
  return p.matrixTransform(svg.getScreenCTM().inverse());
}
function dartLabel(d) {
  if (!d.multiplier) return t("miss");
  if (d.number === 25) return d.multiplier === 2 ? "Bullseye" : "Bull";
  return "SDT"[d.multiplier - 1] + d.number;
}
function vb(svg) { const b = svg.viewBox.baseVal; return [b.x, b.y, b.width, b.height]; }
// viewBox vloeiend veranderen (≈180 ms)
let vbAnim = 0;
function animateVB(svg, to, ms = 180, done) {
  const from = vb(svg), run = ++vbAnim, t0 = performance.now();
  const step = (now) => {
    if (run !== vbAnim) return;
    const k = Math.min(1, (now - t0) / ms), e = 1 - (1 - k) * (1 - k);
    svg.setAttribute("viewBox", from.map((v, i) => v + (to[i] - v) * e).join(" "));
    if (k < 1) requestAnimationFrame(step);
    else if (done) done();
  };
  requestAnimationFrame(step);
}
const redraw = () => { if (S && active()) updateBoard(S.current !== null ? S.players[S.current] : null); };
function bindLoupe(svg) {
  let drag = null;               // { id, x, y (scherm), timer, zoomed, saved }
  const ghost = el("g", { class: "ghost", visibility: "hidden" });
  const gc = el("circle", { r: 9, class: "dart" }, ghost);
  const gt = el("text", { class: "dnum" }, ghost);
  const place = () => {
    const q = svgPoint(svg, drag.x, drag.y);
    const k = vb(svg)[2] / 480;                        // even groot op het scherm bij elke zoom
    const cur = S.current !== null ? S.players[S.current] : null;
    gc.setAttribute("cx", q.x); gc.setAttribute("cy", q.y); gc.setAttribute("r", 11 * k);
    gc.setAttribute("fill", cur ? COLORS[cur.color % COLORS.length] : "#fff");
    gt.setAttribute("x", q.x); gt.setAttribute("y", q.y); gt.setAttribute("font-size", 10 * k);
    gt.textContent = sel + 1;
    if (!ghost.parentNode) svg.appendChild(ghost);
    ghost.setAttribute("visibility", "visible");
    // vergrootglas boven de vinger
    const wrap = $("mboardwrap").getBoundingClientRect(), lp = $("mloupe");
    const size = lp.offsetWidth || 150;
    let left = drag.x - wrap.left - size / 2, top = drag.y - wrap.top - size - 70;
    if (drag.y - size - 70 < 8) top = drag.y - wrap.top + 60;
    left = Math.max(-10, Math.min(wrap.width - size + 10, left));
    lp.style.transform = `translate(${left}px, ${top}px)`;
    if (!loupeSvg) {
      loupeSvg = svg.cloneNode(true);
      loupeSvg.removeAttribute("id");
      loupeSvg.classList.add("mlsvg");
      lp.prepend(loupeSvg);
    }
    const half = vb(svg)[2] / 2 / (drag.zoomed ? 1.6 : LOUPE_ZOOM);   // ingezoomd is minder vergroting nodig
    loupeSvg.setAttribute("viewBox", `${q.x - half} ${q.y - half} ${half * 2} ${half * 2}`);
    const lg = loupeSvg.querySelector(".ghost");
    if (lg) lg.replaceWith(ghost.cloneNode(true));
    else loupeSvg.appendChild(ghost.cloneNode(true));
    const hit = hitTest(q.x, -q.y), lbl = dartLabel(hit);
    $("mllabel").textContent = lbl;
    if (lbl !== lastLbl) { lastLbl = lbl; buzz(6); }
    lp.classList.remove("hidden");
    return hit;
  };
  // inzoomen rond de vinger: het punt onder je vinger blijft onder je vinger
  const holdZoom = () => {
    if (!drag) return;
    const [x, y, w, h] = vb(svg);
    const r = svg.getBoundingClientRect();
    const fx = (drag.x - r.left) / r.width, fy = (drag.y - r.top) / r.height;
    const q = svgPoint(svg, drag.x, drag.y);
    const factor = Math.max(1.25, (w / 480) * HOLD_TOTAL);   // naar 3× in totaal (al verder ingezoomd: nog iets extra)
    const w2 = w / factor, h2 = h / factor;
    drag.saved = drag.saved || [x, y, w, h];
    drag.zoomed = true;
    vbAnim++;
    svg.setAttribute("viewBox", `${q.x - fx * w2} ${q.y - fy * h2} ${w2} ${h2}`);
    $("mzlvl").textContent = Math.round(480 / w2 * 10) / 10 + "×";
    $("mzlvl").classList.remove("hidden");
    svg.classList.add("holdzoom");
    buzz(20);
    redraw();
    if (loupeSvg) { loupeSvg.remove(); loupeSvg = null; }   // vergrootglas opnieuw opbouwen met de nieuwe stippen
    place();
  };
  // vinger bij de rand van het bord: het beeld schuift die kant op (sneller naarmate je dichter bij de rand bent)
  const edgeLoop = (now) => {
    if (!drag) return;
    const dt = Math.min(0.05, (now - (drag.last || now)) / 1000);
    drag.last = now;
    const [x, y, w, h] = vb(svg);
    if (w < 479 && (drag.moved || drag.zoomed)) {     // pas schuiven als je echt naar de rand beweegt
      const r = svg.getBoundingClientRect();
      const fx = (drag.x - r.left) / r.width, fy = (drag.y - r.top) / r.height;
      const push = (f) => (f < EDGE ? -(1 - Math.max(0, f) / EDGE) : f > 1 - EDGE ? (1 - Math.max(0, 1 - f) / EDGE) : 0);
      const px = push(fx), py = push(fy);
      if (px || py) {
        const step = EDGE_SPEED * 480 * dt / Math.sqrt(480 / w);          // ingezoomd iets rustiger
        const nx = Math.max(-250, Math.min(250 - w, x + px * step));
        const ny = Math.max(-250, Math.min(250 - h, y + py * step));
        if (nx !== x || ny !== y) {
          vbAnim++;
          svg.setAttribute("viewBox", `${nx} ${ny} ${w} ${h}`);
          drag.panned = true;
          place();
        }
      }
      $("mboardwrap").dataset.edge = (px < 0 ? "l" : px > 0 ? "r" : "") + (py < 0 ? "t" : py > 0 ? "b" : "");
    }
    requestAnimationFrame(edgeLoop);
  };
  const end = () => {
    clearTimeout(drag.timer);
    $("mboardwrap").dataset.edge = "";
    if (!drag.zoomed && drag.panned) {               // verschoven zonder vasthouden: nieuwe middenpositie onthouden
      const [x, y, w] = vb(svg);
      zoom.cx = x + w / 2; zoom.cy = y + w / 2;
    }
    if (drag.zoomed) animateVB(svg, drag.saved, 180, redraw);
    svg.classList.remove("holdzoom");
    drag = null;
    ghost.setAttribute("visibility", "hidden");
    $("mloupe").classList.add("hidden");
    if (loupeSvg) { loupeSvg.remove(); loupeSvg = null; }
    lastLbl = "";
    setTimeout(() => { $("mzlvl").textContent = zoom.lvl ? ZOOMS[zoom.lvl] + "×" : ""; $("mzlvl").classList.toggle("hidden", !zoom.lvl); }, 200);
  };
  svg.addEventListener("pointerdown", (ev) => {
    if (!active() || botTurn()) return;
    if (sel === null) { $("mhint").textContent = t("mob_pick_first"); buzz(40); return; }
    ev.preventDefault();
    svg.setPointerCapture(ev.pointerId);
    drag = { id: ev.pointerId, x: ev.clientX, y: ev.clientY, x0: ev.clientX, y0: ev.clientY, zoomed: false };
    drag.timer = setTimeout(holdZoom, HOLD_MS);
    svg.classList.add("placing");
    place();
    requestAnimationFrame(edgeLoop);
  });
  svg.addEventListener("pointermove", (ev) => {
    if (!drag || ev.pointerId !== drag.id) return;
    if (Math.hypot(ev.clientX - drag.x0, ev.clientY - drag.y0) > 24) drag.moved = true;
    drag.x = ev.clientX; drag.y = ev.clientY;          // ingezoomd is dezelfde beweging vanzelf fijner
    place();
  });
  svg.addEventListener("pointerup", (ev) => {
    if (!drag || ev.pointerId !== drag.id) return;
    drag.x = ev.clientX; drag.y = ev.clientY;
    const hit = place();
    svg.classList.remove("placing");
    end();
    commit(hit);
  });
  svg.addEventListener("pointercancel", () => { if (drag) { svg.classList.remove("placing"); end(); } });
}
function hitTest(x, y) {
  const r = Math.hypot(x, y), pos = { x: x / R.dblOut, y: y / R.dblOut };
  if (r <= R.bullIn) return { number: 25, multiplier: 2, ...pos };
  if (r <= R.bullOut) return { number: 25, multiplier: 1, ...pos };
  if (r > R.dblOut) return { number: 0, multiplier: 0, ...pos };
  const ang = Math.atan2(y, x) * 180 / Math.PI;
  const idx = ((Math.round((90 - ang) / 18) % 20) + 20) % 20;
  return { number: SEG[idx], multiplier: r >= R.dblIn ? 2 : (r >= R.triIn && r <= R.triOut) ? 3 : 1, ...pos };
}
// pijl corrigeren (bestaande pijl) of invoeren (lege plek)
function commit(d) {
  const i = sel;
  sel = null;
  if (autoZoom()) zoomTo(0);
  buzz(25);
  if (i < S.darts.length) send({ type: "correct", index: i, ...d });
  else send({ type: "dart", ...d });
}

// --------------------------------------------------------------- weergave
const isAfg = () => !S.mode || S.mode === "afgooien";
const active = () => S && ["select", "play", "bulloff"].includes(S.phase);
const botTurn = () => active() && S.current !== null && S.players[S.current] && S.players[S.current].bot;
const slotsCount = () => (S.phase === "select" || S.phase === "bulloff" ? Math.max(1, S.darts.length + (S.waiting || (S.phase === "select" && S.sel_step === "done") ? 0 : 1))
  : isAfg() ? S.settings.darts_per_turn : 3);
const full = () => isAfg() ? (S.phase === "select" ? S.sel_step === "done" : S.darts.length >= S.settings.darts_per_turn) : !!S.waiting;

function render(state) {
  S = state;
  if (S.lang && S.lang !== LANG) { LANG = S.lang; applyI18n(); fillKeys(); }
  $("mgame").textContent = S.mode === "x01" ? String(S.settings.start) : t("gm_" + (S.mode || "afgooien"));
  const fin = S.phase === "finished", setup = S.phase === "setup";
  $("mplay").classList.toggle("hidden", !active());
  $("midle").classList.toggle("hidden", !setup);
  $("mfinish").classList.toggle("hidden", !fin);
  const cur = S.current !== null && S.players[S.current] ? S.players[S.current] : null;
  $("mbanner").textContent = S.instruction || "";
  $("mbanner").style.borderLeftColor = cur ? COLORS[cur.color % COLORS.length] : "var(--accent)";
  $("mbanner").classList.toggle("hidden", setup);
  $("mround").textContent = roundText();
  if (fin) $("mwin").textContent = S.instruction || "";
  if (sel !== null && (!active() || botTurn() || sel > S.darts.length)) sel = null;

  if (active()) {
    const n = slotsCount();
    let h = "";
    for (let i = 0; i < n; i++) {
      const d = S.darts[i];
      const can = !botTurn() && (d || (i === S.darts.length && !full()));
      h += `<button class="mslot ${d ? "" : "empty"} ${sel === i ? "sel" : ""}" data-i="${i}" ${can ? "" : "disabled"}>` +
        (d ? `<b>${esc(d.label)}</b><small>${t("mob_tap_fix")}</small>` : `<span class="plus">＋</span><small>${t("mob_tap_add")}</small>`) + "</button>";
    }
    $("mslots").innerHTML = h;
    $("mturnlbl").textContent = S.phase === "play" ? t("turn_lbl") : t("darts_lbl");
    $("mturn").textContent = S.bust ? t("bust") : S.phase === "play" ? S.turn_score : S.darts.length;
    $("mhint").textContent = botTurn() ? t("bot_turn")
      : sel === null ? (S.darts.length ? t("mob_pick") : "")
      : t(sel < S.darts.length ? (keysMode ? "mob_fix_keys" : "mob_fix") : (keysMode ? "mob_add_keys" : "mob_add"), { n: sel + 1 });
    $("mboardwrap").classList.toggle("hidden", keysMode);
    $("mkeys").classList.toggle("hidden", !keysMode);
    $("mtoggle").textContent = keysMode ? "◎ " + t("mob_board") : "⌨ " + t("mob_keys");
    $("mundo").disabled = !S.can_undo;
    $("mmiss").querySelector("span").textContent = t(isAfg() && S.phase === "play" && S.settings.miss_penalty ? "miss_pen" : "miss");
    $("mmiss").disabled = botTurn() || (sel === null && full());
    $("mnext").disabled = botTurn() || !!S.pending || (S.phase === "select" && S.sel_step !== "done");
    $("mnotice").textContent = S.notice || "";
    updateBoard(cur);
    updateKeys();
    $("mboard").classList.toggle("aiming", sel !== null);   // alleen dan het scrollen op het bord blokkeren
  }
  renderAlloc();
  renderPlayers();
}
function roundText() {
  if (S.round_label) return S.round_label;
  if (S.phase === "finished") return t("rp_over");
  if (S.mode === "x01") return S.phase === "bulloff" ? t("rp_bulloff") : t("rp_leg", { n: (S.leg_no || 0) + 1 });
  if (S.mode === "countup") return t("rp_cu", { n: S.turn_no, r: S.settings.rounds });
  if (S.phase === "select") return t(S.tiebreak ? "rp_tie" : "rp_select");
  return S.phase === "play" ? t("rp_round", { n: S.turn_no }) : "";
}
function updateBoard(cur) {
  const owners = {};
  if (isAfg()) S.players.forEach((p) => { if (p.number) owners[p.number] = p; });
  else if (S.mode === "killer") S.players.forEach((p) => { if (p.number) owners[p.number] = p; });
  const co = S.checkout && S.checkout[0];
  const coNum = co && /^[SDT]\d+$/.test(co) ? +co.slice(1) : null;
  for (const num of SEG) {
    const o = owners[num];
    B.own[num].setAttribute("fill", o ? (o.out ? "#2a2f36" : COLORS[o.color % COLORS.length]) : "#1a1f26");
    let on = false;
    if (isAfg() && S.phase === "play" && cur && o && !o.out) on = cur.killer ? o.index !== cur.index : o.index === cur.index;
    if (S.highlight) on = S.highlight.nums.includes(num);
    if (coNum === num) on = true;
    B.hl[num].classList.toggle("on", on);
  }
  B.bullhl.classList.toggle("on", !!(S.highlight && S.highlight.bull) || co === "Bull" || co === "Bullseye");
  B.darts.innerHTML = "";
  const col = cur ? COLORS[cur.color % COLORS.length] : "#fff";
  S.darts.forEach((d, i) => {
    if (d.x === undefined) return;
    const g = el("g", { class: "mdart" + (sel === i ? " sel" : "") }, B.darts);
    const k = $("mboard").viewBox.baseVal.width / 480;  // stippen even groot op het scherm, ook ingezoomd
    el("circle", { cx: d.x * R.dblOut, cy: -d.y * R.dblOut, r: (sel === i ? 11 : 8) * k, fill: col, class: "dart" }, g);
    el("text", { x: d.x * R.dblOut, y: -d.y * R.dblOut, class: "dnum", "font-size": 10 * k }, g).textContent = i + 1;
  });
}

// --------------------------------------------------------------- toetsen
function fillKeys() {
  const nums = [];
  for (let n = 1; n <= 20; n++) nums.push(n);
  $("mgrid").innerHTML = nums.map((n) => `<button data-n="${n}">${n}</button>`).join("") +
    `<button data-n="25" class="wide2">Bull</button><button data-n="0" class="wide2 miss">${esc(t("mob_miss_board"))}</button>`;
}
function updateKeys() {
  $("mmult").querySelectorAll("button").forEach((b) => b.classList.toggle("on", +b.dataset.m === mult));
  const b25 = $("mgrid").querySelector('[data-n="25"]');
  if (b25) { b25.textContent = mult === 2 ? "Bullseye" : "Bull"; b25.disabled = mult === 3; }
  $("mgrid").querySelectorAll("button").forEach((b) => { if (b.dataset.n !== "25") b.disabled = sel === null; });
  if (b25 && sel === null) b25.disabled = true;
}

// ---------------------------------------------------------- punten verdelen
function renderAlloc() {
  const pd = S && S.pending && S.phase === "play" && !(S.players[S.pending.player] || {}).bot ? S.pending : null;
  $("malloc").classList.toggle("hidden", !pd);
  if (!pd) { allocKey = null; return; }
  if (String(pd.id) !== allocKey) { allocKey = String(pd.id); alloc = {}; if (pd.targets.length === 1) alloc[pd.targets[0]] = pd.points; }
  const used = Object.values(alloc).reduce((a, b) => a + b, 0), left = pd.points - used;
  $("malloctitle").textContent = `${t("al_title", { name: S.players[pd.player].name, reason: pd.reason })} ${t("al_left", { n: left })}`;
  $("malloclist").innerHTML = pd.targets.map((i) => {
    const q = S.players[i], v = alloc[i] || 0;
    return `<div class="arow"><div class="anum" style="background:${COLORS[q.color % COLORS.length]}">${q.number}</div>
      <div><div class="aname">${esc(q.name)}</div><div class="apts">${t("al_pts", { n: q.points })}${v ? ` → ${Math.max(0, q.points - v)}` : ""}</div></div>
      <div class="stepper"><button data-i="${i}" data-d="-1" ${v === 0 ? "disabled" : ""}>−</button><span class="val">${v}</span>
      <button data-i="${i}" data-d="1" ${left === 0 ? "disabled" : ""}>+</button></div></div>`;
  }).join("");
  $("mallocok").disabled = left !== 0;
}

// ----------------------------------------------------------------- stand
function renderPlayers() {
  if (!S || !S.players || !S.players.length) { $("mplayers").innerHTML = ""; return; }
  const order = S.order && S.order.length ? S.order : S.players.map((p) => p.index);
  $("mplayers").innerHTML = order.map((i) => {
    const p = S.players[i], c = COLORS[p.color % COLORS.length];
    let big = "", meta = "";
    if (isAfg()) {
      big = `${p.points}<small>/${S.settings.target}</small>`;
      meta = p.out ? t("badge_out") : p.killer ? t("badge_killer") : p.number ? "#" + p.number : t("pm_nonum");
    } else if (S.mode === "x01") {
      big = S.phase === "bulloff" ? "–" : p.score;
      meta = S.settings.match !== "off" ? `${t("pm_legs")} ${p.legs}${S.settings.match === "sets" ? ` · ${t("pm_sets")} ${p.sets}` : ""}` : "";
    } else if (S.views) {
      big = esc(S.views[i].big);
      meta = esc(S.views[i].meta[0] || "");
    } else big = p.score;
    const cls = ["mp", i === S.current && S.phase !== "finished" ? "cur" : "", p.out ? "out" : ""].join(" ");
    return `<div class="${cls}" style="--pc:${c}"><span class="mpdot"></span><span class="mpn">${p.bot ? "🤖 " : ""}${esc(p.name)}</span>` +
      `<span class="mpm">${meta}</span><b class="mpb">${big}</b></div>`;
  }).join("");
}

// ------------------------------------------------------------------ events
function bind() {
  $("mslots").addEventListener("click", (e) => {
    const b = e.target.closest(".mslot");
    if (!b || b.disabled) return;
    const i = +b.dataset.i;
    sel = sel === i ? null : i;
    buzz(15);
    if (sel !== null) focusDart(sel);
    else if (autoZoom()) zoomTo(0);
    render(S);
  });
  $("mzin").onclick = () => {
    const d = sel !== null && S.darts[sel];
    if (d && d.x !== undefined && zoom.lvl === 0) zoomTo(1, d.x * R.dblOut, -d.y * R.dblOut);
    else zoomTo(zoom.lvl + 1);
  };
  $("mzout").onclick = () => zoomTo(zoom.lvl - 1);
  $("mtoggle").onclick = () => { keysMode = !keysMode; store.set("afgooien.m.keys", keysMode); render(S); };
  $("mmult").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) { mult = +b.dataset.m; updateKeys(); } });
  $("mgrid").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b || b.disabled || sel === null) return;
    const n = +b.dataset.n;
    // "mis (op het bord)": in de cijferring, dus geen strafpunt bij Afgooien
    commit(n === 0 ? { number: 0, multiplier: 0, x: 0, y: 1.08 } : { number: n, multiplier: n === 25 ? Math.min(mult, 2) : mult });
    mult = 1;
  });
  $("mundo").onclick = () => { sel = null; send({ type: "undo" }); };
  $("mundowin").onclick = () => send({ type: "undo" });
  $("mmiss").onclick = () => {
    if (sel !== null) commit({ number: 0, multiplier: 0 });
    else send({ type: "dart", number: 0, multiplier: 0 });
  };
  $("mnext").onclick = () => { sel = null; send({ type: "next" }); };
  $("magain").onclick = () => {
    const st = { ...S.settings };
    delete st.seed;
    send({ type: "new_game", mode: S.mode || "afgooien", players: S.players.map((p) => p.name), bots: S.players.map((p) => p.bot || 0), settings: st });
  };
  $("malloclist").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-i]");
    if (!b || b.disabled) return;
    const i = +b.dataset.i;
    alloc[i] = Math.max(0, (alloc[i] || 0) + +b.dataset.d);
    renderAlloc();
  });
  $("mallocok").onclick = () => send({ type: "allocate", alloc: Object.entries(alloc).map(([i, n]) => [+i, n]) });
}

applyI18n();
fillKeys();
buildBoard();
setViewBox();
bind();
connect();
