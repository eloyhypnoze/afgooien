"use strict";
// Afgooien - speelscherm. Geen frameworks, geen build-stap.

const COLORS = ["#4f9cff", "#ff7043", "#3ecf8e", "#ba68c8", "#ffca28", "#26c6da",
                "#ec407a", "#9ccc65", "#8d6e63", "#78909c", "#ff8a80", "#b388ff"];
const SEG = [20, 1, 18, 4, 13, 6, 10, 15, 2, 17, 3, 19, 7, 16, 8, 11, 14, 9, 12, 5];
// Officiële maten in mm (straal)
const R = { bullIn: 6.35, bullOut: 15.9, triIn: 99, triOut: 107, dblIn: 162, dblOut: 170 };
const NS = "http://www.w3.org/2000/svg";

const $ = (id) => document.getElementById(id);
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* geen opslag */ } },
};

// ------------------------------------------------------------------- taal
// Schermteksten staan in i18n.js; spelteksten maakt de spelregelcode al in de juiste taal.
const UI = window.AFGOOIEN_UI;
let LANG = store.get("afgooien.lang", "nl");
function t(key, p) {
  let v = (UI[LANG] || UI.nl)[key];
  if (v === undefined) v = UI.nl[key] !== undefined ? UI.nl[key] : key;
  if (Array.isArray(v)) v = v[p && p.n === 1 ? 0 : 1];
  return String(v).replace(/\{(\w+)\}/g, (m, k) => (p && k in p ? p[k] : m));
}
function applyI18n() {
  document.documentElement.lang = LANG;
  document.querySelectorAll("[data-i18n]").forEach((e) => { e.textContent = t(e.dataset.i18n); });
  document.querySelectorAll("[data-i18n-title]").forEach((e) => { e.title = t(e.dataset.i18nTitle); });
  document.querySelectorAll("[data-i18n-ph]").forEach((e) => { e.placeholder = t(e.dataset.i18nPh); });
  document.querySelectorAll("[data-i18n-aria]").forEach((e) => e.setAttribute("aria-label", t(e.dataset.i18nAria)));
  document.querySelectorAll(".langbtn").forEach((b) => b.classList.toggle("active", b.dataset.lang === LANG));
  relabelLobby();
  renderLobbyMode();
  renderModes();
}
// De taal komt van de server (geldt voor alle schermen); wisselen = opnieuw opbouwen.
function setLang(lang) {
  if (!UI[lang] || lang === LANG) return false;
  LANG = lang;
  store.set("afgooien.lang", lang);
  applyI18n();
  fillVoices();
  if (S) { renderLobbyInfo(); updateHome(); if (view === "settings") renderSettings(); if (!$("stats").classList.contains("hidden")) renderStats(); }
  return true;
}

// In de testversie (één losse pagina) draait de spelregelcode in de browser.
const LOCAL = window.AFGOOIEN_LOCAL || null;
let S = null;           // laatste spelstand
let lastVersion = null;   // laatste spelversie waarvoor stem/animatie is afgespeeld
let fixIndex = null;      // pijl die gecorrigeerd wordt (klik daarna op het bord)
let winnerHoldUntil = 0;  // winnaarsvenster pas tonen na de "af"-animatie

// ------------------------------------------------------------------ server
async function send(cmd) {
  try {
    let j;
    if (LOCAL) j = await LOCAL.send(cmd);
    else {
      const r = await fetch("/api/cmd", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cmd) });
      j = await r.json();
    }
    if (!j.ok) { showError(j.error); return false; }
    render(j.state);
    return true;
  } catch (e) {
    showError(t("no_conn"));
    return false;
  }
}
function showError(msg) {
  if (S && S.phase === "setup") $("setuperr").textContent = msg;
  else $("notice").textContent = msg;
}

function connect() {
  if (LOCAL) {
    $("loading").classList.remove("hidden");
    if (LOCAL.onUpdate) LOCAL.onUpdate((st) => render(st));
    LOCAL.ready.then((st) => { $("loading").classList.add("hidden"); render(st); })
      .catch((e) => { $("loadingtext").textContent = t("load_fail", { e }); });
    return;
  }
  const es = new EventSource("/events");
  es.onmessage = (ev) => { $("offline").classList.add("hidden"); render(JSON.parse(ev.data)); };
  es.onerror = () => $("offline").classList.remove("hidden");
}

// ------------------------------------------------------------------- board
function el(tag, attrs, parent) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs || {})) e.setAttribute(k, v);
  if (parent) parent.appendChild(e);
  return e;
}
const pt = (r, deg) => [r * Math.cos(deg * Math.PI / 180), -r * Math.sin(deg * Math.PI / 180)];
function sector(r1, r2, a1, a2) {   // a1 > a2 (met de klok mee)
  const [x1, y1] = pt(r2, a1), [x2, y2] = pt(r2, a2), [x3, y3] = pt(r1, a2), [x4, y4] = pt(r1, a1);
  return `M${x1} ${y1}A${r2} ${r2} 0 0 1 ${x2} ${y2}L${x3} ${y3}A${r1} ${r1} 0 0 0 ${x4} ${y4}Z`;
}

const boardEls = { own: {}, lbl: {}, hl: {} };
function buildBoard() {
  const svg = $("board");
  el("circle", { r: 225.5, class: "boardedge" }, svg);   // echte buitenrand van het bord (451 mm)
  SEG.forEach((num, i) => {
    const mid = 90 - i * 18, a1 = mid + 9, a2 = mid - 9;
    const dark = i % 2 === 0;
    el("path", { d: sector(R.bullOut, R.triIn, a1, a2), class: dark ? "s-dark" : "s-light" }, svg);
    el("path", { d: sector(R.triIn, R.triOut, a1, a2), class: dark ? "r-red" : "r-green" }, svg);
    el("path", { d: sector(R.triOut, R.dblIn, a1, a2), class: dark ? "s-dark" : "s-light" }, svg);
    el("path", { d: sector(R.dblIn, R.dblOut, a1, a2), class: dark ? "r-red" : "r-green" }, svg);
    boardEls.own[num] = el("path", { d: sector(173, 202, a1, a2), class: "ownring", fill: "#1a1f26" }, svg);
    boardEls.hl[num] = el("path", { d: sector(R.bullOut, R.dblOut, a1, a2), class: "hl" }, svg);
    const [lx, ly] = pt(187.5, mid);
    const t = el("text", { x: lx, y: ly, class: "lbl" }, svg);
    t.textContent = num;
    boardEls.lbl[num] = t;
  });
  el("circle", { r: R.bullOut, class: "r-green" }, svg);
  el("circle", { r: R.bullIn, class: "r-red" }, svg);
  for (const r of [R.bullIn, R.bullOut, R.triIn, R.triOut, R.dblIn, R.dblOut]) el("circle", { r, class: "wire" }, svg);
  boardEls.bullhl = el("circle", { r: R.bullOut, class: "hl" }, svg);
  boardEls.darts = el("g", {}, svg);
  boardEls.ring = el("circle", { r: 232, class: "statusring" }, svg);

  svg.addEventListener("click", (ev) => {
    if (!S || !["select", "play", "bulloff", "shootout"].includes(S.phase)) return;
    if (botTurn()) { $("notice").textContent = t("bot_turn"); return; }
    const p = svg.createSVGPoint();
    p.x = ev.clientX; p.y = ev.clientY;
    const q = p.matrixTransform(svg.getScreenCTM().inverse());
    if (fixIndex !== null) {
      const i = fixIndex;
      setFix(null);
      send({ type: "correct", index: i, ...hitTest(q.x, -q.y) });
      return;
    }
    send({ type: "dart", ...hitTest(q.x, -q.y) });
  });
}

function hitTest(x, y) {        // x, y in mm, y omhoog
  const r = Math.hypot(x, y);
  const pos = { x: x / R.dblOut, y: y / R.dblOut };
  if (r <= R.bullIn) return { number: 25, multiplier: 2, ...pos };
  if (r <= R.bullOut) return { number: 25, multiplier: 1, ...pos };
  if (r > R.dblOut) return { number: 0, multiplier: 0, ...pos };
  const ang = Math.atan2(y, x) * 180 / Math.PI;
  const idx = ((Math.round((90 - ang) / 18) % 20) + 20) % 20;
  const mult = r >= R.dblIn ? 2 : (r >= R.triIn && r <= R.triOut) ? 3 : 1;
  return { number: SEG[idx], multiplier: mult, ...pos };
}

function updateBoard() {
  const owners = {};
  S.players.forEach((p) => { if (p.number) owners[p.number] = p; });
  const cur = S.current !== null ? S.players[S.current] : null;
  const playing = S.phase === "play";
  // X01: het eerste vak van de uitgooi-route oplichten
  const co = S.checkout && S.checkout[0];
  const coNum = co && /^[SDT]\d+$/.test(co) ? +co.slice(1) : null;
  for (const num of SEG) {
    const o = owners[num];
    boardEls.own[num].setAttribute("fill", o ? (o.out ? "#2a2f36" : COLORS[o.color % COLORS.length]) : "#1a1f26");
    boardEls.lbl[num].classList.toggle("owned", !!o);
    const hl = boardEls.hl[num];
    let on = false, dead = false;
    if (playing && cur && o) {
      if (o.out) dead = true;
      else if (cur.killer) on = o.index !== cur.index;
      else on = o.index === cur.index;
    }
    if (S.phase === "select" && S.sel_step === "number" && o) dead = true;
    if (coNum === num) on = true;
    if (S.highlight) on = S.highlight.nums.includes(num);
    hl.classList.toggle("on", on);
    hl.classList.toggle("dead", dead);
  }
  boardEls.bullhl.classList.toggle("on", !!(S.highlight && S.highlight.bull) || co === "Bull" || co === "Bullseye");
  const g = boardEls.darts;
  g.innerHTML = "";
  const col = cur ? COLORS[cur.color % COLORS.length] : "#fff";
  for (const d of S.darts) {
    if (d.x === undefined) continue;
    el("circle", { cx: d.x * R.dblOut, cy: -d.y * R.dblOut, r: 5.5, fill: col, class: "dart" }, g);
  }
}

// ------------------------------------------------------------------ render
function pipHtml(p, target) {
  const c = COLORS[p.color % COLORS.length];
  let h = "";
  for (let i = 0; i < target; i++) h += `<div class="pip" style="${i < p.points ? `background:${c};border-color:${c}` : ""}"></div>`;
  return h;
}
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const mm = (b) => (b === null || b === undefined) ? t("miss_mm") : `${Math.round(b * R.dblOut)} mm`;

// Telefoon als afstandsbediening (/?remote=1, geopend vanaf de telefoonpagina): zelfde menu's, maar
// zonder stem (die komt uit het grote scherm). Start je hier een potje, dan ga je naar de bediening.
const REMOTE = /[?&]remote=1/.test(location.search);
let remotePhase = null, loadedVersion = null, lastSayN = null;
function render(state) {
  if (REMOTE && !LOCAL) {
    const wasSetup = remotePhase === "setup";
    remotePhase = state.phase;
    if (wasSetup && state.phase !== "setup") { location.href = "/m"; return; }
  }
  if (!LOCAL && state.app_version) {        // nieuwe versie op de server: pagina opnieuw laden
    if (loadedVersion && state.app_version !== loadedVersion) { location.reload(); return; }
    loadedVersion = state.app_version;
  }
  S = state;
  if (S.lang) setLang(S.lang);
  if (!REMOTE && S.say) {
    if (lastSayN !== null && S.say.n !== lastSayN && S.say.phrases.length) sayPhrases(S.say.phrases, true);
    lastSayN = S.say.n;
  }
  refreshVoiceUi();
  renderMusic();
  applyMusic();
  maybeIntro();
  if (view === "settings") { fillUpdate(); fillMail(); }
  const mk = JSON.stringify(S.mail || {});
  if (mk !== lastMailKey) { lastMailKey = mk; if (view === "players" && S.phase === "setup") renderPlayerMain(); }
  const localScreen = ["localhost", "127.0.0.1", "[::1]"].includes(location.hostname);
  $("powerbtn").classList.toggle("hidden", !(S.power && localScreen && !LOCAL));
  if (S.app_version) $("appversion").textContent = "v" + S.app_version + (LOCAL ? " · " + t("testversion") : "");
  syncWake();
  const setup = S.phase === "setup";
  showView();
  if (setup && !$("names").children.length) fillSetup();

  // bronstatus
  const src = S.source || {};
  const pill = $("src");
  pill.className = "pill";
  pill.title = "";
  if (src.mode === "test") pill.textContent = t("src_test");
  else if (!src.enabled) pill.textContent = t("src_off");
  else if (src.connected) { pill.textContent = t("src_ok") + (boardName(src) ? ` · ${boardName(src)}` : ""); pill.classList.add("ok"); }
  else { pill.textContent = t("src_bad"); pill.classList.add("bad"); pill.title = src.error || ""; }
  if (src.enabled && src.mode !== "test" && !pill.title) pill.title = t("src_tip");
  renderAdPanel();

  renderLobbyInfo();
  if (setup) { $("winner").classList.add("hidden"); updateHome(); feedback(); return; }

  const tgt = S.settings.target;
  const cur = S.current !== null ? S.players[S.current] : null;
  $("banner").textContent = S.instruction || "";
  $("banner").style.borderLeftColor = cur ? COLORS[cur.color % COLORS.length] : "var(--accent)";

  const other = isOther();
  $("gametitle").textContent = modeTitle(S.mode, S.settings);
  if (!isParty()) $("ctable").classList.add("hidden");
  if (isParty()) renderParty();
  else if (other) renderOther();
  else {
  $("roundpill").textContent = S.phase === "select" ? t(S.tiebreak ? "rp_tie" : "rp_select")
    : S.phase === "play" ? t("rp_round", { n: S.turn_no }) : t("rp_over");
  if (S.phase === "select") {
    $("phaseinfo").textContent = t(S.tiebreak ? "ph_tie" : "ph_select");
  } else if (S.phase === "play") {
    const cp = S.current !== null ? S.players[S.current] : null;
    let tg = "";
    if (cp && cp.killer) {
      tg = S.order.filter((i) => i !== S.current && !S.players[i].out).map((i) => {
        const q = S.players[i];
        return `${esc(q.name)} #${q.number} (${q.points} ${t("pt")})`;
      }).join(" · ");
    }
    $("phaseinfo").innerHTML = esc(t("ph_play", { t: tgt })) +
      (tg ? `<span class="tg">${t("ph_targets", { list: tg })}</span>` : "");
  } else $("phaseinfo").textContent = "";

  // spelers
  const order = S.phase === "select" ? S.players.map((p) => p.index) : S.order;
  $("players").innerHTML = order.map((i) => {
    const p = S.players[i];
    const c = COLORS[p.color % COLORS.length];
    let meta = "";
    if (S.phase === "select") {
      if (p.bull.length) meta = t("pm_bull", { mm: mm(p.bull[p.bull.length - 1]) });
      else if (p.number) meta = t("pm_tobull");
      else meta = t("pm_nonum");
    } else if (p.out) meta = t("pm_out", { by: esc(p.out_by), place: p.place });
    else if (p.killer) meta = t("pm_killer");
    else meta = t("pm_pts", { p: p.points, t: tgt });
    if (p.bot) meta += ` <span class="botbadge">${t("bot_badge", { l: p.bot })}</span>`;
    const badge = p.out ? `<span class="badge o">${t("badge_out")}</span>` : p.killer ? `<span class="badge k">${t("badge_killer")}</span>` : "";
    const cls = ["player", i === S.current && S.phase !== "finished" ? "current" : "", p.killer ? "killer" : "", p.out ? "out" : "", cardFx(i)].join(" ");
    return `<div class="${cls}" data-i="${i}" style="--pc:${c}">
      <div class="name">${p.bot ? "🤖 " : ""}${esc(p.name)}${badge}</div>
      <div class="num" style="background:${p.number ? c : "var(--panel2)"};color:${p.number ? "#0b0d10" : "var(--muted)"}">${p.number || "?"}</div>
      <div class="pips">${pipHtml(p, tgt)}</div>
      <div class="meta">${meta}</div></div>`;
  }).join("");
  }

  // worpen deze beurt
  const slots = S.phase === "select" || S.phase === "bulloff" ? Math.max(1, S.darts.length)
    : S.phase === "shootout" ? (S.shootout && S.shootout.choice === "bull" ? 1 : 3) : other ? 3 : S.settings.darts_per_turn;
  let sh = "";
  for (let i = 0; i < slots; i++) {
    const d = S.darts[i];
    const canFix = d && !botTurn();
    sh += d ? `<div class="slot ${canFix ? "fixable" : ""} ${fixIndex === i ? "fixing" : ""}" data-fix="${i}" title="${t("fix_tip")}">${fixIndex === i ? "→ ?" : d.label}</div>`
            : `<div class="slot empty">${DART_ICON}</div>`;
  }
  $("turn").innerHTML = S.phase === "finished" ? "" : sh;
  document.querySelector(".dartbar").classList.toggle("hidden", S.phase === "finished");

  const th = tonHint();
  $("turnscore").innerHTML = (S.bust ? `<span>${t("turn_lbl")}</span><b class="bustv">${t("bust")}</b>`
    : S.phase === "play" ? `<span>${t("turn_lbl")}</span><b>${S.turn_score}</b>`
    : S.phase === "shootout" && S.shootout && S.shootout.choice === "score" ? `<span>${t("turn_lbl")}</span><b>${(S.shootout.vals.find((v) => v.i === S.current) || { v: 0 }).v}</b>` : `<span>${t("darts_lbl")}</span><b>${S.darts.length}</b>`) +
    (th && th.text ? `<span class="tm ${th.cls}">${th.text}</span>` : "") +
    (S.queued ? `<span class="tm mid">${t("waiting", { n: S.queued })}</span>` : "");
  const bs = boardStatus();
  boardEls.ring.setAttribute("class", "statusring " + (bs ? bs[0] : ""));
  $("boardstatus").className = "bstatus " + (bs ? bs[0] : "");
  $("boardstatus").textContent = bs ? "● " + bs[1] : "";
  $("boardreset").classList.toggle("hidden", !(S.source && S.source.enabled) || S.phase === "setup");

  // knoppen
  const active = S.phase === "select" || S.phase === "play" || S.phase === "bulloff" || S.phase === "shootout";
  $("misslbl").textContent = t(!other && S.phase === "play" && S.settings.miss_penalty ? "miss_pen" : "miss");
  $("miss").disabled = !active || botTurn();
  $("undo").disabled = !S.can_undo;
  $("finishbtn").classList.toggle("hidden", !(S.mode === "free" && S.phase === "play"));
  $("next").disabled = !active || (S.phase === "select" && S.sel_step !== "done") || !!S.pending || botTurn();
  if (fixIndex !== null && (!S.darts[fixIndex] || botTurn())) setFix(null, true);
  if (fixIndex !== null) $("notice").innerHTML = `<span class="fixhint">${t("fix_hint", { n: fixIndex + 1 })}</span>`;
  else $("notice").textContent = S.notice || "";

  $("log").innerHTML = S.log.slice().reverse().map((l) => `<li class="${l.kind}">${esc(l.text)}</li>`).join("");
  updateBoard();

  renderAlloc();
  renderSoChoice();
  if (S.history_version !== undefined && S.history_version !== H.version) loadHistory();

  // winnaar
  const fin = S.phase === "finished";
  const hold = winnerHoldUntil - Date.now();
  $("winner").classList.toggle("hidden", !fin || hold > 0);
  if (fin && hold > 0) setTimeout(() => render(S), hold + 20);
  if (fin) {
    const w = S.players[S.winner];
    const tops = S.players.filter((p) => p.place === 1);
    $("winname").textContent = tops.length > 1 ? t("win_tie", { names: tops.map((p) => p.name).join(" & ") }) : t("win", { name: w.name });
    const ranked = [...S.players].sort((a, b) => a.place - b.place || a.index - b.index);
    $("ranking").innerHTML = ranked.map((p) => {
      let who = `<b>${esc(p.name)}</b>`, row;
      if (S.mode === "x01") row = t("win_x01", { avg: fmt2(xavg(p)), legs: p.legs_total, co: p.hi_checkout || "–" });
      else if (S.mode === "free") row = t("win_fr", { avg: fmt2(avg3(p.score, p.darts)), score: p.score, darts: p.darts, best: p.best_round });
      else if (S.mode === "countup") row = t("win_cu", { score: p.score, avg: fmt2(avg3(p.points, p.darts)), best: p.best_round });
      else if (isParty()) { const v = S.views[p.index]; row = esc([String(v.big)].concat(v.meta).join(" · ")); }
      else { who += ` (${p.number})`; row = t("win_row", { kills: p.kills, ppt: fmt2(p.turns ? (p.gained + p.knocked) / p.turns : 0), tr: p.triples }); }
      return `<tr><td>${p.place}.</td><td>${who}</td><td class="r">${row}</td></tr>`;
    }).join("");
    updateTodayLine();
  }
  feedback();
}

// --------------------------------------------------------- X01 / Count Up
const isOther = () => !!(S && S.mode && S.mode !== "afgooien");
const avg3 = (pts, darts) => (darts ? pts / darts * 3 : 0);
// X01-gemiddelde telt alleen beurten waarin je nog niet op een finish stond (oude potjes: alles)
const xavg = (p) => avg3(p.avg_points != null ? p.avg_points : p.points, p.avg_darts != null ? p.avg_darts : p.darts);
function renderOther() {
  const st = S.settings;
  const so = S.mode === "x01" ? S.shootout : null;
  const soVal = {};
  if (so) so.vals.forEach((v) => { soVal[v.i] = v.v; });
  if (S.mode === "x01" && S.phase === "shootout" && so) {
    $("roundpill").textContent = t("rp_so");
    const ch = S.players[so.chooser];
    $("phaseinfo").textContent = so.choice === null ? t("ph_so_choose", { name: ch.name }) : t(so.choice === "bull" ? "ph_so_bull" : "ph_so_score");
  } else if (S.mode === "x01") {
    $("roundpill").textContent = S.phase === "bulloff" ? t("rp_bulloff")
      : S.phase === "finished" ? t("rp_over")
      : st.match === "sets" ? t("rp_set_leg", { s: S.set_no, n: S.players.reduce((a, p) => a + p.legs, 0) + 1 }) : t("rp_leg", { n: S.leg_no + 1 });
    if (S.phase === "bulloff") $("phaseinfo").textContent = t("ph_bulloff");
    else {
      const match = st.match === "sets" ? `${t("chip_first_sets", { n: st.sets })} · ${t("chip_first_legs", { n: st.legs })}`
        : st.match === "legs" ? t("chip_first_legs", { n: st.legs }) : t("ph_m_single");
      $("phaseinfo").innerHTML = esc(t("ph_x01", { start: st.start, out: cap(st.out_mode), in: st.in_mode !== "straight" ? t("ph_in", { m: cap(st.in_mode) }) : "", match })) +
        (S.checkout ? `<span class="tg co">${esc(t("ph_checkout", { route: S.checkout.join(" · ") }))}</span>` : "");
    }
  } else if (S.mode === "free") {
    $("roundpill").textContent = S.phase === "finished" ? t("rp_over") : t("rp_round", { n: S.turn_no });
    $("phaseinfo").textContent = t("ph_free");
  } else if (S.rounds === null) {
    $("roundpill").textContent = S.phase === "finished" ? t("rp_over") : t("rp_cu_elim", { n: S.turn_no, l: S.elim_left });
    $("phaseinfo").textContent = t("ph_cu_elim", { n: st.elim });
  } else {
    $("roundpill").textContent = S.phase === "finished" ? t("rp_over") : t("rp_cu", { n: S.turn_no, r: st.rounds });
    $("phaseinfo").textContent = t("ph_cu", { r: st.rounds });
  }
  let order = S.order.length ? S.order.slice() : S.players.map((p) => p.index);
  if (order.length < S.players.length) order = order.concat(S.players.map((p) => p.index).filter((i) => !order.includes(i))
    .sort((a, b) => (S.players[a].place || 99) - (S.players[b].place || 99)));
  const solo = S.players.length === 1;
  $("players").classList.toggle("solo", solo);
  $("players").innerHTML = order.map((i) => {
    const p = S.players[i];
    const c = COLORS[p.color % COLORS.length];
    const curr = i === S.current && S.phase !== "finished";
    let big, meta = [], side = "", dim = false;
    if (S.mode === "x01") {
      big = S.phase === "bulloff" ? "–" : p.score;
      if (S.phase === "shootout" && so) {
        const inSo = so.rest.includes(i);
        dim = !inSo && i !== S.winner;
        if (i in soVal) big = so.choice === "bull" ? (soVal[i] === null ? t("miss_mm") : soVal[i]) : soVal[i];
        else big = inSo ? "–" : `#${p.place}`;
        if (inSo) meta.push(so.choice === "bull" && i in soVal && soVal[i] !== null ? t("pm_mm", { n: soVal[i] }) : t("pm_so_in"));
      }
      meta.push(t("pm_avg", { avg: fmt2(xavg(p)) }), t("pm_darts", { n: p.darts_leg }));
      if (!p.opened && S.phase === "play") meta.push(t("pm_notopen"));
      if (st.match !== "off") {
        side = (st.match === "sets" ? `<span class="ls"><small>${t("pm_sets")}</small><b>${p.sets}</b></span>` : "") +
          `<span class="ls"><small>${t("pm_legs")}</small><b>${p.legs}</b></span>`;
      }
    } else if (S.mode === "free") {
      big = fmt2(avg3(p.score, p.darts));
      meta.push(t("pm_fr_pts", { n: p.score }), t("pm_darts", { n: p.darts }));
      if (p.rounds.length) meta.push(t("pm_last", { n: p.rounds[p.rounds.length - 1] }));
    } else {
      big = p.score;
      meta.push(t("pm_avg", { avg: fmt2(avg3(p.score, p.darts)) }));
      if (p.rounds.length) meta.push(t("pm_last", { n: p.rounds[p.rounds.length - 1] }));
      if (p.out && S.phase !== "finished") { dim = true; meta.unshift(`#${p.place}`); }
    }
    if (p.place && S.phase === "finished") meta.unshift(`#${p.place}`);
    const bot = p.bot ? ` <span class="botbadge">${t("bot_badge", { l: p.bot })}</span>` : "";
    const badge = p.out && S.phase !== "finished" ? `<span class="badge o">${t("badge_out")}</span>` : "";
    const cls = ["player", "xp", curr ? "current" : "", dim ? "soout" : "", cardFx(i)].join(" ");
    return `<div class="${cls}" data-i="${i}" style="--pc:${c}">
      <div class="name">${p.bot ? "🤖 " : ""}${esc(p.name)}${badge}</div>
      <div class="side">${side}</div>
      <div class="bigscore">${big}</div>
      <div class="meta">${meta.map(esc).join(" · ")}${bot}</div></div>`;
  }).join("");
}

// ------------------------------------------------------- party/training
function renderParty() {
  $("roundpill").textContent = S.round_label || "";
  $("phaseinfo").innerHTML = esc(S.info || "") +
    (S.checkout ? `<span class="tg co">${esc(t("ph_checkout", { route: S.checkout.join(" · ") }))}</span>` : "");
  const order = S.order.length ? S.order : S.players.map((p) => p.index);
  $("players").classList.toggle("solo", S.players.length === 1);
  $("players").innerHTML = order.map((i) => {
    const p = S.players[i], v = S.views[i];
    const c = COLORS[p.color % COLORS.length];
    const curr = i === S.current && S.phase !== "finished";
    const meta = v.meta.slice();
    if (p.place && S.phase === "finished") meta.unshift(`#${p.place}`);
    const bot = p.bot ? ` <span class="botbadge">${t("bot_badge", { l: p.bot })}</span>` : "";
    const badge = v.badge ? `<span class="badge ${p.out ? "o" : "k"}">${esc(v.badge)}</span>` : "";
    const cls = ["player", "xp", curr ? "current" : "", v.dim ? "out" : "", cardFx(i)].join(" ");
    const big = String(v.big);
    return `<div class="${cls}" data-i="${i}" style="--pc:${c}">
      <div class="name">${p.bot ? "🤖 " : ""}${esc(p.name)}${badge}</div>
      <div class="side">${p.number && S.mode === "killer" ? `<span class="ls"><small>#</small><b>${p.number}</b></span>` : ""}</div>
      <div class="bigscore ${/♥|✕/.test(big) ? "hearts" : big.length > 4 ? "small" : ""}">${esc(big)}</div>
      <div class="meta">${meta.map(esc).join(" · ")}${bot}</div></div>`;
  }).join("");
  const tb = S.table;
  $("ctable").classList.toggle("hidden", !tb);
  if (tb) {
    const sym = ["", "╱", "✕", "⊗"];
    $("ctable").innerHTML = `<table class="ctab"><thead><tr><th class="l"></th>${tb.cols.map((c, k) => `<th class="${tb.closed[k] ? "closed" : ""}">${c}</th>`).join("")}<th>${t("pt")}</th></tr></thead><tbody>` +
      order.map((i) => {
        const p = S.players[i];
        return `<tr class="${i === S.current && S.phase !== "finished" ? "cur" : ""}"><td class="l" style="--pc:${COLORS[p.color % COLORS.length]}"><span class="dotc"></span>${esc(p.name)}</td>` +
          tb.rows[i].map((m, k) => `<td class="mk m${m} ${tb.closed[k] ? "closed" : ""}">${sym[m]}</td>`).join("") + `<td class="pts">${p.score}</td></tr>`;
      }).join("") + "</tbody></table>";
  }
}

// ------------------------------------------------------- shoot-out keuze
function renderSoChoice() {
  const so = S && S.phase === "shootout" ? S.shootout : null;
  const show = !!(so && so.choice === null && !(S.players[so.chooser] || {}).bot);
  $("sochoice").classList.toggle("hidden", !show);
  if (show) $("sosub").textContent = t("so_sub", { name: S.players[so.chooser].name });
}

// ------------------------------------------------------- punten verdelen
let alloc = {}, allocKey = null;
function renderAlloc() {
  const pd = S.pending && !(S.players[S.pending.player] || {}).bot ? S.pending : null;   // een bot kiest zelf
  $("alloc").classList.toggle("hidden", !pd);
  if (!pd) { allocKey = null; return; }
  const key = `${pd.id}`;
  if (key !== allocKey) {   // nieuwe keuze: standaard alles bij de eerste
    allocKey = key;
    alloc = {};
    if (pd.targets.length === 1) alloc[pd.targets[0]] = pd.points;
  }
  const p = S.players[pd.player];
  $("alloctitle").textContent = t("al_title", { name: p.name, reason: pd.reason });
  const used = Object.values(alloc).reduce((a, b) => a + b, 0);
  const left = pd.points - used;
  $("allocsub").innerHTML = esc(t("al_sub", { pts: t("points", { n: pd.points }) })) +
    `<span class="remain ${left === 0 ? "ok" : ""}">${t("al_left", { n: left })}</span>` +
    (pd.more ? esc(t("al_more", { n: pd.more })) : "");
  $("alloclist").innerHTML = pd.targets.map((i) => {
    const q = S.players[i];
    const v = alloc[i] || 0;
    const after = Math.max(0, q.points - v);
    const dead = v > 0 && after === 0 && canEliminate(q);   // een ander zet je op 0: af
    const c = COLORS[q.color % COLORS.length];
    return `<div class="arow"><div class="anum" style="background:${c}">${q.number}</div>
      <div><div class="aname">${esc(q.name)}</div>
      <div class="apts ${dead ? "dead" : ""}">${t("al_pts", { n: q.points })}${v ? ` → ${after}${dead ? " · " + t("badge_out") : ""}` : ""}</div></div>
      <div class="stepper"><button data-i="${i}" data-d="-1" ${v === 0 ? "disabled" : ""}>−</button>
      <span class="val">${v}</span><button data-i="${i}" data-d="1" ${left === 0 ? "disabled" : ""}>+</button></div></div>`;
  }).join("");
  $("allocok").disabled = left !== 0;
}
function canEliminate(q) {
  const r = S.settings.elimination;
  return r === "scored" ? q.scored : r === "reached_target" ? q.reached_target : true;
}

// eigen bevestigingsvenster (werkt ook waar confirm() geblokkeerd is)
let confirmYes = null;
function confirmDialog(text, onYes) {
  $("confirmtext").textContent = text;
  confirmYes = onYes;
  $("confirm").classList.remove("hidden");
}

// --------------------------------------------------------------------- stem
// De stem komt uit de browser (Web Speech). Beste resultaat: Microsoft Edge, die
// natuurlijke stemmen heeft zoals "Microsoft Maarten Online (Natural)".
// De gekozen stem wordt per taal bewaard; bij Engels kiest hij automatisch een Engelse stem.
const voiceCfg = Object.assign({ on: true, engine: "browser", commentary: "some", volume: 1, name: "", names: {}, pitch: 0.8, rate: 0.95 }, store.get("afgooien.voice", {}));
if (voiceCfg.name && !voiceCfg.names.nl) voiceCfg.names.nl = voiceCfg.name;   // oude instelling
delete voiceCfg.name;
const VOICE_PREF = {
  nl: { lang: "nl", exact: "nl-nl", male: /maarten|arnaud|frank|xander|willem|daan|guus|bram|male/ },
  en: { lang: "en", exact: "en-gb", male: /ryan|thomas|george|oliver|daniel|arthur|guy|eric|male/ },
};
const hasSpeech = "speechSynthesis" in window;
// De stemmenlijst één keer ophalen (op Linux/Pi gaat dat via speech-dispatcher en is het traag)
let voiceCache = null, bestVoice, voicesHooked = false;
function allVoices() {
  if (!hasSpeech) return [];
  if (!voicesHooked) {           // pas aanraken als de browserstem echt nodig is (op de Pi traag)
    voicesHooked = true;
    try { speechSynthesis.onvoiceschanged = voicesChanged; } catch (e) { /* */ }
  }
  if (voiceCache && voiceCache.length) return voiceCache;
  try { voiceCache = speechSynthesis.getVoices().filter((v) => v.name && !/undefined/i.test(v.name)); } catch (e) { voiceCache = []; }
  return voiceCache;
}
function voicesChanged() { voiceCache = null; bestVoice = undefined; if (view === "settings") fillVoices(); }
function voiceScore(v) {
  const n = v.name.toLowerCase(), l = (v.lang || "").toLowerCase().replace("_", "-");
  const pref = VOICE_PREF[LANG] || VOICE_PREF.nl;
  if (!l.startsWith(pref.lang)) return 0;
  let s = 100;
  if (l === pref.exact) s += 5;
  if (/natural|online|neural|premium|enhanced/.test(n)) s += 30;
  if (pref.male.test(n)) s += 15;
  if (/google/.test(n)) s += 5;
  return s;
}
function pickVoice() {
  const key = LANG + "|" + (voiceCfg.names[LANG] || "");
  if (bestVoice && bestVoice.key === key) return bestVoice.v;
  const v = pickVoiceSlow();
  if (voiceCache && voiceCache.length) bestVoice = { key, v };
  return v;
}
function pickVoiceSlow() {
  const vs = allVoices();
  const want = voiceCfg.names[LANG];
  if (want) { const f = vs.find((v) => v.name === want); if (f) return f; }
  let best = null;
  for (const v of vs) if (!best || voiceScore(v) > voiceScore(best)) best = v;
  return best && voiceScore(best) > 0 ? best : null;
}
// ---- stem van de server (Piper op de Pi, of ElevenLabs/Azure met je eigen sleutel)
// De stem-instellingen staan op de server (gelden voor elk scherm, ook in te stellen vanaf de telefoon).
// Alleen in de losse testversie (zonder server) gelden de instellingen in deze browser.
function vset() { return !LOCAL && S && S.tts && "on" in S.tts ? S.tts : voiceCfg; }
function serverVoice() {
  if (LOCAL || !S || !S.tts) return null;
  return S.tts.provider !== "browser" && S.tts.voices ? S.tts.voices[LANG] || null : null;
}
function voiceSave(changes) {
  if (LOCAL || !S || !S.tts) { Object.assign(voiceCfg, changes); store.set("afgooien.voice", voiceCfg); fillVoices(); return; }
  return send({ type: "voice_config", ...changes });
}
const ttsAudio = typeof Audio !== "undefined" ? new Audio() : null;
let ttsRun = 0;
function stopSpeech() {
  ttsRun++;
  if (ttsAudio) { try { ttsAudio.pause(); } catch (e) { /* */ } }
  if (hasSpeech && voicesHooked) { try { speechSynthesis.cancel(); } catch (e) { /* */ } }
}
const BIG_RE = /tachtig|eighty|is af|is out|Game shot|mag afgooien|is a killer/i;
async function serverSay(list) {
  const run = ++ttsRun;
  if (ttsAudio) ttsAudio.pause();
  const rate = +vset().rate || 1;
  const items = [];
  for (const phrase of list) {
    const parts = phrase.split("...").map((x) => x.trim()).filter(Boolean);
    const big = BIG_RE.test(phrase);
    parts.forEach((part, i) => {
      const last = i === parts.length - 1;
      const r = Math.round(rate * (big ? (last ? 0.88 : 0.95) : 1) * 20) / 20;
      const vk = encodeURIComponent((S && S.tts && S.tts.voices && S.tts.voices[LANG]) || "");
      items.push({ url: `/api/tts?l=${LANG}&r=${r}&v=${vk}&t=${encodeURIComponent(part)}`, gap: last ? 150 : 280 });
    });
  }
  // alles meteen opvragen (de server maakt ze), dan na elkaar afspelen
  for (const it of items) it.p = fetch(it.url, { cache: "no-store" }).then((r) => (r.ok ? r.blob() : null)).catch(() => null);
  for (const it of items) {
    const blob = await it.p;
    if (run !== ttsRun) return;
    if (!blob) continue;
    const src = URL.createObjectURL(blob);
    try {
      ttsAudio.src = src;
      ttsAudio.volume = Math.min(1, Math.max(0, vset().volume ?? 1));
      await new Promise((res) => { ttsAudio.onended = res; ttsAudio.onerror = res; ttsAudio.play().catch(res); });
    } finally { URL.revokeObjectURL(src); }
    if (run !== ttsRun) return;
    await new Promise((res) => setTimeout(res, it.gap));
  }
}
function sayPhrases(list, force) {
  const vs = vset();
  if (REMOTE || (!vs.on && !force) || !list.length) return;
  if (serverVoice() && ttsAudio) { const end = musDuck(); serverSay(list).finally(end); return; }
  if (!hasSpeech) return;
  try {
    speechSynthesis.cancel();
    const end = musDuck();
    let pending = 0;
    const done = () => { if (--pending <= 0) end(); };
    const v = pickVoice();
    const rate = +vs.rate || 1;
    for (const phrase of list) {
      // "..." = korte stilte en nadruk op het laatste deel, zoals een caller
      const parts = phrase.split("...").map((x) => x.trim()).filter(Boolean);
      const big = BIG_RE.test(phrase);
      parts.forEach((part, i) => {
        const u = new SpeechSynthesisUtterance(part);
        if (v) { u.voice = v; u.lang = v.lang; } else u.lang = LANG === "en" ? "en-GB" : "nl-NL";
        const last = i === parts.length - 1;
        u.pitch = Math.max(0.1, voiceCfg.pitch * (big && last ? 0.9 : 1));
        u.rate = rate * (big ? (last ? 0.78 : 0.9) : 1);
        u.volume = Math.min(1, Math.max(0, vs.volume ?? 1));
        pending++;
        u.onend = done; u.onerror = done;
        speechSynthesis.speak(u);
      });
    }
  } catch (e) { /* geen stem beschikbaar */ }
}

// ------------------------------------------------------- muziek (YouTube / YouTube Music)
// De server bewaart wát er moet spelen; alleen het grote scherm speelt het af met de officiële
// YouTube-speler (klein maar zichtbaar in beeld). Telefoon en menu bedienen via de server.
const MUS = { yt: null, ready: false, apiP: null, seq: null, duckN: 0, vol: null, ramp: null, rep: "", err: null,
  errRun: 0, needShuffle: false };
const musicHere = () => !REMOTE && !LOCAL;
function ytApi() {
  if (MUS.apiP) return MUS.apiP;
  MUS.apiP = new Promise((res, rej) => {
    const prev = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => { if (prev) try { prev(); } catch (e) { /* */ } res(window.YT); };
    const s = document.createElement("script");
    s.src = "https://www.youtube.com/iframe_api";
    s.async = true;
    s.onerror = () => { MUS.apiP = null; s.remove(); rej(new Error("yt")); };
    document.head.appendChild(s);
    setTimeout(() => rej(new Error("yt")), 20000);
  });
  return MUS.apiP;
}
async function ytPlayer() {
  if (MUS.yt && MUS.ready) return MUS.yt;
  const YT = await ytApi();
  if (!MUS.yt) {
    await new Promise((res) => {
      MUS.yt = new YT.Player("ytplayer", {
        width: 224, height: 200,
        playerVars: { autoplay: 1, playsinline: 1, rel: 0, iv_load_policy: 3, origin: location.origin },
        events: { onReady: () => { MUS.ready = true; res(); }, onStateChange: musState, onError: musError },
      });
    });
  }
  return MUS.yt;
}
function musTarget() {
  const m = S && S.music;
  if (!m) return 0;
  const base = INTRO.on ? Math.max(m.volume, 70) : m.volume;          // walk-ons iets harder
  return Math.round(base * (MUS.duckN > 0 && m.duck ? 0.3 : 1));
}
function musVolume(smooth) {
  const p = MUS.yt;
  if (!p || !MUS.ready) return;
  const to = musTarget();
  if (MUS.vol === to) return;
  clearInterval(MUS.ramp);
  const from = MUS.vol === null ? to : MUS.vol;
  if (!smooth || from === to) { MUS.vol = to; try { p.setVolume(to); } catch (e) { /* */ } return; }
  let i = 0;
  MUS.ramp = setInterval(() => {
    i++;
    const v = Math.round(from + (to - from) * i / 6);
    try { p.setVolume(v); } catch (e) { /* */ }
    MUS.vol = v;
    if (i >= 6) clearInterval(MUS.ramp);
  }, 45);
}
// stem: muziek even zachter (tijdens het praten)
function musDuck() {
  if (!musicHere() || !MUS.yt) return () => {};
  MUS.duckN++;
  musVolume(true);
  let done = false;
  const end = () => { if (done) return; done = true; MUS.duckN = Math.max(0, MUS.duckN - 1); setTimeout(() => musVolume(true), 250); };
  setTimeout(end, 20000);              // vangnet als het einde nooit gemeld wordt
  return end;
}
function musReport() {
  if (INTRO.on) return;
  const p = MUS.yt;
  if (!p || !MUS.ready || !S || !S.music || !(S.music.video || S.music.list || S.music.videos)) return;
  let st = -1, title = "";
  try { st = p.getPlayerState(); title = (p.getVideoData() || {}).title || ""; } catch (e) { /* */ }
  let vid = "";
  try { vid = (p.getVideoData() || {}).video_id || ""; } catch (e) { /* */ }
  const o = { playing: st === 1 || st === 3, title, err: MUS.err, vid };
  const k = JSON.stringify(o);
  if (k === MUS.rep) return;
  MUS.rep = k;
  fetch("/api/cmd", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ type: "music_status", ...o }) }).catch(() => {});
}
function musState(e) {
  const p = MUS.yt;
  if (INTRO.on) { if (e.data === 0) showIntro(INTRO.i + 1); else if (e.data === 1) musVolume(false); return; }
  if (e.data === 1) {
    MUS.errRun = 0;
    if (MUS.err && MUS.err !== "101") MUS.err = null;
    if (MUS.needShuffle) {
      MUS.needShuffle = false;
      try { p.setLoop(true); p.setShuffle(true); p.playVideoAt(0); } catch (err) { /* */ }
    }
    musVolume(false);
  }
  musReport();
}
function musError(e) {
  if (INTRO.on) { clearTimeout(INTRO.timer); INTRO.timer = setTimeout(() => showIntro(INTRO.i + 1), 4000); return; }
  const code = String(e.data);
  MUS.err = code === "150" ? "101" : code;
  const m = S && S.music;
  if (m && (m.list || m.videos) && ++MUS.errRun < 8) { try { MUS.yt.nextVideo(); } catch (err) { /* */ } }
  musReport();
}
async function applyMusic() {
  if (!musicHere() || !S || !S.music || INTRO.on) return;
  const m = S.music;
  const has = !!(m.video || m.list || m.videos);
  $("musicdock").classList.toggle("hidden", !has);
  if (has) placeDock();
  if (MUS.seq === m.seq) { musVolume(true); return; }
  const first = MUS.seq === null;
  MUS.seq = m.seq;
  if (!has) { if (MUS.yt && MUS.ready) try { MUS.yt.stopVideo(); } catch (e) { /* */ } MUS.rep = ""; return; }
  const op = first ? "load" : m.op;
  let p;
  try { p = await ytPlayer(); } catch (e) { MUS.err = "yt"; renderMusic(); return; }
  if (MUS.seq !== m.seq) return;                     // inmiddels alweer iets anders gekozen
  try {
    if (op === "load") {
      MUS.err = null; MUS.errRun = 0; MUS.rep = "";
      const radio = m.list && /^RD/.test(m.list) && m.video;   // mixen: gewoon het nummer
      if (m.videos) {
        if (m.playing) p.loadPlaylist(m.videos, m.start || 0); else p.cuePlaylist(m.videos, m.start || 0);
        MUS.needShuffle = !!m.shuffle && m.playing && !m.start;
        try { p.setLoop(true); } catch (e) { /* */ }
      } else if (m.list && !radio) {
        const o = { list: m.list, listType: "playlist", index: 0 };
        if (m.playing) p.loadPlaylist(o); else p.cuePlaylist(o);
        MUS.needShuffle = !!m.shuffle && m.playing;
        try { p.setLoop(true); } catch (e) { /* */ }
      } else {
        const o = { videoId: m.video };
        if (m.vend) { o.startSeconds = m.vstart || 0; o.endSeconds = m.vend; }      // stukje (walk-on proberen)
        if (m.playing) p.loadVideoById(o); else p.cueVideoById(o);
      }
    } else if (op === "play") p.playVideo();
    else if (op === "pause") p.pauseVideo();
    else if (op === "next") { if (m.list || m.videos) p.nextVideo(); else p.seekTo(0, true); }
    else if (op === "prev") { if (m.list || m.videos) p.previousVideo(); else p.seekTo(0, true); }
    else if (op === "shuffle") { p.setShuffle(!!m.shuffle); }
  } catch (e) { /* speler nog niet klaar */ }
  MUS.vol = null;
  musVolume(false);
}
function placeDock() {
  const d = $("musicdock");
  if (d.classList.contains("hidden")) return;
  if (INTRO.on) {                                                  // walk-on: groot naast de spelerskaart
    d.classList.remove("compact");
    const W = d.offsetWidth || 448, H = d.offsetHeight || 252;
    d.style.left = Math.round(Math.max(innerWidth * 0.6, innerWidth - W - innerWidth * 0.06)) + "px";
    d.style.top = Math.round((innerHeight - H) / 2) + "px";
    return;
  }
  const inGame = !$("game").classList.contains("hidden");
  const a = inGame && document.querySelector("#game .dartbar"), b = inGame && document.querySelector("#game .statusrow");
  const ra = a && a.getBoundingClientRect(), rb = b && b.getBoundingClientRect();
  const gap = ra && rb ? rb.top - ra.bottom : 0;
  // weinig ruimte: alleen de speler (200 hoog), bediening zit in het muziekmenu
  d.classList.toggle("compact", inGame && gap < 236 + 12);
  const W = d.offsetWidth || 224, H = d.offsetHeight || 236;
  let x = innerWidth - W - 16, y = innerHeight - H - 16;           // buiten het spel: rechtsonder
  if (ra && rb) {                                                  // in het spel: rechts naast het bord
    x = Math.min(innerWidth - W - 8, Math.max(8, ra.right - W));
    y = gap >= H + 12 ? ra.bottom + (gap - H) / 2 : Math.max(ra.top, rb.top - H - 6);
  }
  d.style.left = Math.round(x) + "px";
  d.style.top = Math.round(y) + "px";
}
const MU_ERR = { "101": "mu_e101", "100": "mu_e100", "2": "mu_e2", "5": "mu_e5", "yt": "mu_eyt" };
const MUI = { tab: store.get("afgooien.muTab", "search"), sk: "video", pls: null, plsAt: 0, tracks: null, trTitle: "",
  trFrom: "mine", results: null, busy: false };
function ytErr(code) {
  const m = (UI[LANG] || UI.nl).yt_e || {};
  return m[code] || t("yt_e_other", { code });
}
// fout van de server ("YouTube: code") of van een /api/yt-aanroep
function muErrText(e) {
  const s = String(e || "");
  const m = /^YouTube: (\S+)$/.exec(s);
  return m ? ytErr(m[1]) : s;
}
function setMuTab(tab) {
  MUI.tab = tab;
  if (tab !== "tracks") store.set("afgooien.muTab", tab);
  document.querySelectorAll("#musicpanel [data-tab]").forEach((b) => b.classList.toggle("on", b.dataset.tab === tab || (tab === "tracks" && b.dataset.tab === MUI.trFrom)));
  document.querySelectorAll("#musicpanel [data-pane]").forEach((p) => p.classList.toggle("hidden", p.dataset.pane !== tab));
  $("mu_err").textContent = "";
  if (tab === "mine") loadPlaylists(false);
  if (tab === "search") setTimeout(() => { if (!$("musicpanel").classList.contains("hidden")) $("mu_q").focus(); }, 30);
  renderMusic();
}
async function ytGet(path) {
  const r = await fetch(path, { cache: "no-store" });
  const j = await r.json().catch(() => ({ ok: false, error: "net" }));
  if (!j.ok) throw new Error(j.error || "net");
  return j.items;
}
const ytUser = () => (S && S.youtube) || {};
function muRow(it, i, kind) {
  const th = it.thumb ? `<img src="${esc(it.thumb)}" alt="" loading="lazy">` : `<span class="mu_noart">${kind === "pl" ? "≡" : "♪"}</span>`;
  const sub = kind === "pl" ? (it.count != null ? t("mu_tracks_n", { n: it.count }) : "") : esc(it.artist || "");
  return `<li><button class="mu_row" data-${kind}="${i}">${th}<span class="mu_rt"><b>${esc(it.title)}</b><small>${sub}</small></span></button></li>`;
}
function renderMuLists() {
  const u = ytUser();
  // zoeken
  const gate = !u.logged_in ? `<p>${esc(t(u.configured ? "mu_needlogin" : "mu_needcfg"))}</p>` +
    (u.configured ? `<button class="primary" data-golog>${esc(t("mu_loginbtn"))}</button>` : `<button class="ghost" data-gocfg>${esc(t("mu_tocfg"))}</button>`) : "";
  $("mu_sgate").innerHTML = gate;
  $("mu_sgate").classList.toggle("hidden", !gate);
  $("mu_sform").classList.toggle("hidden", !!gate);
  document.querySelectorAll("#musicpanel [data-sk]").forEach((b) => b.classList.toggle("on", b.dataset.sk === MUI.sk));
  $("mu_results").innerHTML = MUI.results === "busy" ? `<li class="mu_info">${esc(t("mu_searching"))}</li>`
    : Array.isArray(MUI.results) ? (MUI.results.length ? MUI.results.map((it, i) => muRow(it, i, MUI.sk === "playlist" ? "spl" : "sv")).join("")
      : `<li class="mu_info">${esc(t("mu_noresults"))}</li>`) : "";
  // mijn muziek
  let lg = "";
  if (!u.configured) lg = `<p>${esc(t("mu_needcfg"))}</p><button class="ghost" data-gocfg>${esc(t("mu_tocfg"))}</button>`;
  else if (u.login) {
    const url = u.login.url.replace(/^https?:\/\/(www\.)?/, "");
    lg = `<p>${esc(t("mu_code_t", { url }))}</p><div class="mu_code">${esc(u.login.user_code)}</div>
      <div class="mu_qr"><span>${esc(t("mu_code_scan"))}</span><img src="/api/yt/qr.svg?c=${encodeURIComponent(u.login.user_code)}" alt=""></div>
      <p class="hint">${esc(t("mu_waiting"))}</p><button class="ghost small" data-logcancel>${esc(t("mu_cancel"))}</button>`;
  } else if (!u.logged_in) lg = (u.error ? `<p class="mu_errl">${esc(ytErr(u.error))}</p>` : "") +
    `<p>${esc(t("mu_needlogin"))}</p><button class="primary" data-golog>${esc(t("mu_loginbtn"))}</button>`;
  $("mu_login").innerHTML = lg;
  $("mu_login").classList.toggle("hidden", !lg);
  $("mu_plhead").classList.toggle("hidden", !u.logged_in);
  $("mu_pls").innerHTML = !u.logged_in ? "" : MUI.pls === "busy" || MUI.pls === null ? `<li class="mu_info">${esc(t("mu_loadingl"))}</li>`
    : MUI.pls.map((p, i) => muRow(p.special === "likes" ? { ...p, title: t("mu_likes") } : p, i, "pl")).join("");
  // nummers van een afspeellijst
  $("mu_trtitle").textContent = MUI.trTitle;
  $("mu_tracks").innerHTML = MUI.tracks === "busy" ? `<li class="mu_info">${esc(t("mu_loadingl"))}</li>`
    : Array.isArray(MUI.tracks) ? (MUI.tracks.length ? MUI.tracks.map((it, i) => muRow(it, i, "tr")).join("") : `<li class="mu_info">${esc(t("mu_noresults"))}</li>`) : "";
  $("mu_playall").disabled = $("mu_shufall").disabled = !(Array.isArray(MUI.tracks) && MUI.tracks.length);
}
async function loadPlaylists(force) {
  const u = ytUser();
  if (!u.logged_in) { MUI.pls = null; renderMuLists(); return; }
  if (!force && Array.isArray(MUI.pls) && Date.now() - MUI.plsAt < 5 * 60000) return;
  MUI.pls = "busy"; renderMuLists();
  try { MUI.pls = await ytGet("/api/yt/playlists"); MUI.plsAt = Date.now(); }
  catch (e) { MUI.pls = []; $("mu_err").textContent = ytErr(e.message); }
  renderMuLists();
}
async function openTracks(id, title, from) {
  MUI.tracks = "busy"; MUI.trTitle = title; MUI.trFrom = from; MUI.trId = id;
  setMuTab("tracks");
  try { MUI.tracks = await ytGet("/api/yt/items?list=" + encodeURIComponent(id)); }
  catch (e) { MUI.tracks = []; $("mu_err").textContent = ytErr(e.message); }
  renderMuLists();
}
async function playTracks(start, shuffle) {
  if (!Array.isArray(MUI.tracks) || !MUI.tracks.length) return;
  if (shuffle !== undefined && !!S.music.shuffle !== shuffle) await musicSend({ type: "music_set", shuffle });
  musicSend({ type: "music_load", videos: MUI.tracks.map((x) => x.id), start, name: MUI.trTitle });
}
function renderMusic() {
  if (LOCAL) { $("musicbtn").classList.add("hidden"); return; }
  const m = (S && S.music) || null;
  if (!m) return;
  const has = !!(m.video || m.list || m.videos);
  $("musicbtn").classList.toggle("on", has && m.playing);
  const title = m.title || (has ? t("mu_loading") : "");
  $("mu_now").innerHTML = !has ? esc(t("mu_none")) : `<b>${esc(title)}</b>`;
  $("mu_sub").textContent = !has ? "" : (m.playing ? "▶ " : "⏸ ") + (m.name ? t("mu_from", { name: m.name }) : m.list || m.videos ? t("mu_list") : "");
  const vid = m.vid || m.video;
  $("mu_art").src = vid ? `https://i.ytimg.com/vi/${vid}/mqdefault.jpg` : "";
  $("mu_art").classList.toggle("hidden", !vid);
  $("md_title").textContent = title;
  const u = ytUser();
  $("mu_acct").textContent = u.logged_in && u.account ? t("mu_acct", { name: u.account }) : "";
  const err = (musicHere() ? MUS.err : null) || m.err;
  if (err && MU_ERR[err]) $("mu_err").textContent = t(MU_ERR[err]);
  $("mu_pp").textContent = m.playing ? "⏸" : "▶";
  $("md_pp").textContent = m.playing ? "⏸" : "▶";
  document.querySelectorAll("#musicpanel [data-mu]").forEach((b) => { b.disabled = !has; });
  $("mu_shuf").classList.toggle("on", !!m.shuffle);
  $("mu_shuf").disabled = !(m.list || m.videos);
  if (document.activeElement !== $("mu_vol")) $("mu_vol").value = m.volume;
  $("mu_vol_val").textContent = m.volume + "%";
  const cv = vset().volume ?? 1;
  if (document.activeElement !== $("mu_cvol")) $("mu_cvol").value = cv;
  $("mu_cvol_val").textContent = Math.round(cv * 100) + "%";
  $("mu_duck").checked = !!m.duck;
  $("mu_favs").dataset.empty = t("mu_nofavs");
  const fk = JSON.stringify(m.favs) + LANG;
  if ($("mu_favs").dataset.k !== fk) {
    $("mu_favs").dataset.k = fk;
    $("mu_favs").innerHTML = m.favs.map((f, i) => `<li><button class="ghost mu_fp" data-fav="${i}">${f.list ? "≡ " : "♪ "}${esc(f.title)}</button>
      <button class="ghost mu_fd" data-favdel="${i}" title="${esc(t("set_delete"))}">✕</button></li>`).join("");
  }
  $("mu_favadd").disabled = !(m.video || m.list);
  // inlogstatus veranderd: lijsten bijwerken
  const lk = JSON.stringify([u.configured, u.logged_in, u.login && u.login.user_code, u.error]);
  if (MUI.lk !== lk) {
    const wasIn = MUI.lk && JSON.parse(MUI.lk)[1];
    MUI.lk = lk;
    if (!u.logged_in) { MUI.pls = null; }
    if (u.logged_in && !wasIn) { MUI.pls = null; if (MUI.tab === "mine") loadPlaylists(true); }
    renderMuLists();
  }
  fillYtCard();
}
function fillYtCard() {
  const u = S && S.youtube;
  $("ytcard").classList.toggle("hidden", !u || LOCAL);
  if (!u) return;
  $("yt_state").textContent = u.logged_in ? t("yt_in", { name: u.account || "✓" }) : u.configured ? t("yt_cfg") : t("yt_notcfg");
  $("yt_state").classList.toggle("ok", !!u.logged_in);
  if (!$("yt_steps").children.length || $("yt_steps").dataset.l !== LANG) {
    $("yt_steps").dataset.l = LANG;
    $("yt_steps").innerHTML = ((UI[LANG] || UI.nl).yt_steps || []).map((x) => `<li>${esc(x)}</li>`).join("") + `<li class="hint">${esc(t("yt_tip_phone"))}</li>`;
  }
  if (document.activeElement !== $("yt_cid") && !$("yt_cid").dataset.dirty) $("yt_cid").value = u.client_id || "";
  $("yt_secret").placeholder = u.has_secret ? t("yt_secret_saved") : "";
  $("yt_loginbtn").classList.toggle("hidden", !u.configured || u.logged_in);
  $("yt_logout").classList.toggle("hidden", !u.logged_in);
  if (u.login) $("yt_msg").textContent = t("mu_code_t", { url: u.login.url.replace(/^https?:\/\/(www\.)?/, "") }) + " " + u.login.user_code;
  else if (u.error) $("yt_msg").textContent = ytErr(u.error);
  else if (/[A-Z]{4}-[A-Z]{4}|\.com\/device/.test($("yt_msg").textContent)) $("yt_msg").textContent = "";
}
async function musicSend(cmd) {
  $("mu_err").textContent = "";
  try {
    const r = await fetch("/api/cmd", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cmd) });
    const j = await r.json();
    if (!j.ok) { $("mu_err").textContent = muErrText(j.error); return false; }
    render(j.state);
    return true;
  } catch (e) { $("mu_err").textContent = t("no_conn"); return false; }
}
function openMusic() {
  $("voicepanel").classList.add("hidden");
  $("adpanel").classList.add("hidden");
  $("musicpanel").classList.remove("hidden");
  setMuTab(MUI.tab === "tracks" ? MUI.trFrom : MUI.tab);
}
function bindMusic() {
  $("musicbtn").onclick = (e) => {
    e.stopPropagation();
    if ($("musicpanel").classList.contains("hidden")) openMusic();
    else $("musicpanel").classList.add("hidden");
  };
  $("mu_close").onclick = () => $("musicpanel").classList.add("hidden");
  $("musicpanel").addEventListener("click", (e) => {
    e.stopPropagation();
    const tb = e.target.closest("[data-tab]");
    if (tb) { setMuTab(tb.dataset.tab); return; }
    const b = e.target.closest("[data-mu]");
    if (b && !b.disabled) {
      const a = b.dataset.mu, m = S.music;
      if (a === "toggle") musicSend({ type: "music_ctl", action: m.playing ? "pause" : "play" });
      else if (a === "shuffle") musicSend({ type: "music_set", shuffle: !m.shuffle });
      else musicSend({ type: "music_ctl", action: a });
      return;
    }
    const sk = e.target.closest("[data-sk]");
    if (sk) { MUI.sk = sk.dataset.sk; MUI.results = null; renderMuLists(); if ($("mu_q").value.trim()) $("mu_sform").requestSubmit(); return; }
    const row = e.target.closest(".mu_row");
    if (row) {
      const d = row.dataset;
      if (d.sv !== undefined) { const it = MUI.results[+d.sv]; musicSend({ type: "music_load", video: it.id, title: it.title }); }
      else if (d.spl !== undefined) { const it = MUI.results[+d.spl]; openTracks(it.id, it.title, "search"); }
      else if (d.pl !== undefined) { const p = MUI.pls[+d.pl]; openTracks(p.id, p.special === "likes" ? t("mu_likes") : p.title, "mine"); }
      else if (d.tr !== undefined) playTracks(+d.tr);
      return;
    }
    if (e.target.closest("[data-golog]")) { musicSend({ type: "yt_login" }).then(() => setMuTab("mine")); return; }
    if (e.target.closest("[data-logcancel]")) { musicSend({ type: "yt_login_cancel" }); return; }
    if (e.target.closest("[data-gocfg]")) { $("musicpanel").classList.add("hidden"); setView("settings"); setTimeout(() => $("ytcard").scrollIntoView({ behavior: "smooth" }), 80); return; }
    const f = e.target.closest("[data-fav]");
    if (f) { musicSend({ type: "music_fav", action: "play", index: +f.dataset.fav }); return; }
    const fd = e.target.closest("[data-favdel]");
    if (fd) musicSend({ type: "music_fav", action: "del", index: +fd.dataset.favdel });
  });
  $("mu_back").onclick = () => setMuTab(MUI.trFrom);
  $("mu_playall").onclick = () => playTracks(0, false);
  $("mu_shufall").onclick = () => playTracks(0, true);
  $("mu_plrefresh").onclick = () => loadPlaylists(true);
  $("mu_sform").addEventListener("submit", async (e) => {
    e.preventDefault();
    const q = $("mu_q").value.trim();
    if (!q) return;
    $("mu_err").textContent = "";
    MUI.results = "busy"; renderMuLists();
    try { MUI.results = await ytGet(`/api/yt/search?type=${MUI.sk}&q=${encodeURIComponent(q)}`); }
    catch (err) { MUI.results = []; $("mu_err").textContent = ytErr(err.message); }
    renderMuLists();
  });
  $("mu_form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const url = $("mu_url").value.trim();
    if (!url) return;
    if (await musicSend({ type: "music_load", url })) $("mu_url").value = "";
  });
  $("mu_vol").addEventListener("input", () => { $("mu_vol_val").textContent = $("mu_vol").value + "%"; });
  $("mu_vol").addEventListener("change", () => musicSend({ type: "music_set", volume: +$("mu_vol").value }));
  $("mu_cvol").addEventListener("input", () => { $("mu_cvol_val").textContent = Math.round($("mu_cvol").value * 100) + "%"; });
  $("mu_cvol").addEventListener("change", () => { voiceSave({ volume: +$("mu_cvol").value }); });
  $("mu_duck").addEventListener("change", () => musicSend({ type: "music_set", duck: $("mu_duck").checked }));
  $("mu_favadd").onclick = () => musicSend({ type: "music_fav", action: "add" });
  $("md_pp").onclick = () => musicSend({ type: "music_ctl", action: S.music.playing ? "pause" : "play" });
  $("md_next").onclick = () => musicSend({ type: "music_ctl", action: "next" });
  // instellingen: YouTube-account
  $("yt_cid").addEventListener("input", () => { $("yt_cid").dataset.dirty = "1"; });
  $("yt_save").onclick = async () => {
    $("yt_msg").textContent = "";
    const ok = await musicSend({ type: "yt_client", client_id: $("yt_cid").value.trim(), client_secret: $("yt_secret").value.trim() });
    if (ok) { $("yt_secret").value = ""; delete $("yt_cid").dataset.dirty; $("yt_msg").textContent = t("yt_saved"); }
    else $("yt_msg").textContent = $("mu_err").textContent;
  };
  $("yt_loginbtn").onclick = async () => { if (!(await musicSend({ type: "yt_login" }))) $("yt_msg").textContent = $("mu_err").textContent; };
  $("yt_logout").onclick = () => confirmDialog(t("yt_logout") + "?", () => musicSend({ type: "yt_logout" }));
  document.addEventListener("click", (e) => { if (!e.target.closest("#confirm")) $("musicpanel").classList.add("hidden"); });
  addEventListener("resize", placeDock);
  if (/[?&]music=1/.test(location.search)) setTimeout(openMusic, 400);
}

// ------------------------------------------------------- walk-ons (X01): eigen nummer + stats bij de start
const INTRO = { on: false, list: [], i: 0, timer: null, prev: null, gid: null };
const fmtT = (s) => Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0");
function introStats(name) {
  const games = (H.games || []).filter((g) => gmode(g) === "x01");
  const rows = aggregate(games, "x01").filter((r) => !r.bot);
  const a = rows.find((r) => nkey(r.name) === nkey(name));
  if (!a || !a.games) return null;
  let bestAvg = 0;
  const form = [];
  const chron = games.slice().sort((x, y) => (x.ended < y.ended ? -1 : 1));
  const since = (H.since || {})[nkey(name)];
  for (const g of chron) {
    if (since && g.ended < since) continue;
    const p = g.players.find((q) => !q.bot && nkey(q.name) === nkey(name));
    if (!p) continue;
    bestAvg = Math.max(bestAvg, xavg(p));
    form.push(p.place === 1);
  }
  const tags = [];
  const peers = rows.filter((r) => r.games >= 3);
  if (a.games >= 3 && peers.length >= 2) {
    const M = [["wo_t_avg", (r) => r.avg], ["wo_t_co", (r) => r.coPct || 0], ["wo_t_180", (r) => r.n180 / r.games],
      ["wo_t_f9", (r) => r.f9], ["wo_t_hico", (r) => r.hico], ["wo_t_win", (r) => r.winPct]];
    for (const [k, f] of M) {
      const top = Math.max(...peers.map(f));
      if (top > 0 && f(a) === top) tags.push(t(k));
    }
  }
  if (a.streak >= 2) tags.push(t("wo_t_streak", { n: a.streak }));
  return { a, bestAvg, form: form.slice(-5), tags: tags.slice(0, 3) };
}
function introCard(it) {
  const p = it.p;
  const n = INTRO.list.length;
  $("intro_count").textContent = n > 1 ? t("wo_count", { i: INTRO.i + 1, n }) : "";
  const col = COLORS[(p.color || 0) % COLORS.length];
  $("intro").style.setProperty("--pc", col);
  $("musicdock").style.setProperty("--pc", col);
  $("intro_name").textContent = p.name;
  $("intro_song").innerHTML = it.wo ? `♪ ${esc(it.wo.title || "")}` : "";
  const st = introStats(p.name);
  if (!st) {
    $("intro_games").textContent = t("wo_debut");
    $("intro_stats").innerHTML = "";
    $("intro_tags").innerHTML = "";
    return;
  }
  const a = st.a;
  $("intro_games").textContent = t("wo_games", { n: a.games, w: a.wins, p: pct(a.winPct) });
  const tiles = [];
  if (a.avg > 0) tiles.push([t("wo_avg"), fmt2(a.avg)]);
  if (st.bestAvg > 0) tiles.push([t("wo_bestavg"), fmt2(st.bestAvg)]);
  if (a.n180) tiles.push([t("wo_180"), a.n180]);
  if (a.hico) tiles.push([t("wo_hico"), a.hico]);
  if (a.bestLeg) tiles.push([t("wo_bestleg"), t("wo_legdarts", { n: a.bestLeg })]);
  if (a.coPct) tiles.push([t("wo_co"), pct(a.coPct)]);
  $("intro_stats").innerHTML = tiles.slice(0, 6).map(([k, v], i) =>
    `<div class="itile" style="--d:${0.35 + i * 0.12}s"><b>${esc(String(v))}</b><span>${esc(k)}</span></div>`).join("");
  const form = st.form.length ? `<span class="iform"><span>${esc(t("wo_form"))}</span>${st.form.map((w) => `<i class="${w ? "w" : "l"}"></i>`).join("")}</span>` : "";
  $("intro_tags").innerHTML = st.tags.map((x) => `<span class="itag">${esc(x)}</span>`).join("") + form;
}
function maybeIntro() {
  if (!musicHere() || !S || S.mode !== "x01" || !S.settings || S.settings.walkon !== "on" || !S.game_id) return;
  if (INTRO.on && S.players.some((p) => p.darts > 0)) { endIntro(); return; }   // er wordt al gegooid
  if (INTRO.gid === S.game_id) return;
  if (!["play", "bulloff"].includes(S.phase)) return;
  INTRO.gid = S.game_id;
  if (S.players.some((p) => p.darts > 0) || store.get("afgooien.introDone", "") === S.game_id) return;
  store.set("afgooien.introDone", S.game_id);
  const reg = H.players || [];
  const order = S.order && S.order.length ? S.order : S.players.map((p) => p.index);
  INTRO.list = order.map((i) => S.players[i]).filter((p) => p && !p.bot)
    .map((p) => ({ p, wo: (reg.find((r) => nkey(r.name) === nkey(p.name)) || {}).walkon || null }));
  if (!INTRO.list.length) return;
  INTRO.prev = null;
  if (MUS.yt && MUS.ready) {
    try { INTRO.prev = { idx: MUS.yt.getPlaylistIndex(), time: Math.floor(MUS.yt.getCurrentTime() || 0) }; } catch (e) { /* */ }
  }
  INTRO.on = true;
  $("intro").classList.remove("hidden");
  showIntro(0);
}
async function showIntro(i) {
  clearTimeout(INTRO.timer);
  if (!INTRO.on) return;
  const it = INTRO.list[i];
  if (!it) { endIntro(); return; }
  INTRO.i = i;
  introCard(it);
  const box = $("introin");
  box.classList.remove("go"); void box.offsetWidth; box.classList.add("go");
  const dur = it.wo ? it.wo.dur : 6;
  $("intro_prog").style.animationDuration = dur + "s";
  INTRO.timer = setTimeout(() => showIntro(i + 1), dur * 1000 + 700);
  sayPhrases([t("wo_call", { name: it.p.name })]);
  const d = $("musicdock");
  if (it.wo) {
    try {
      const p = await ytPlayer();
      if (!INTRO.on || INTRO.i !== i) return;
      d.classList.remove("hidden");
      d.classList.add("wodock");
      placeDock();
      p.loadVideoById({ videoId: it.wo.video, startSeconds: it.wo.start, endSeconds: it.wo.start + it.wo.dur });
      MUS.vol = null;
      musVolume(false);
    } catch (e) { /* geen YouTube: alleen de kaart */ }
  } else {
    if (MUS.yt && MUS.ready) try { MUS.yt.pauseVideo(); } catch (e) { /* */ }
    d.classList.add("hidden");
  }
}
function endIntro() {
  if (!INTRO.on) return;
  INTRO.on = false;
  clearTimeout(INTRO.timer);
  $("intro").classList.add("hidden");
  $("musicdock").classList.remove("wodock");
  musRestore(INTRO.prev || {});
}
function musRestore(prev) {
  const m = S && S.music;
  if (!m) return;
  const has = !!(m.video || m.list || m.videos);
  $("musicdock").classList.toggle("hidden", !has);
  const p = MUS.yt;
  if (!p || !MUS.ready) return;
  if (!has) { try { p.stopVideo(); } catch (e) { /* */ } return; }
  if (MUS.seq !== m.seq) { applyMusic(); return; }          // tijdens de intro iets anders gekozen
  try {
    const go = m.playing;
    if (m.videos) go ? p.loadPlaylist(m.videos, prev.idx || 0, prev.time || 0) : p.cuePlaylist(m.videos, prev.idx || 0, prev.time || 0);
    else if (m.list) {
      const o = { list: m.list, listType: "playlist", index: prev.idx || 0, startSeconds: prev.time || 0 };
      go ? p.loadPlaylist(o) : p.cuePlaylist(o);
    } else {
      const o = { videoId: m.video, startSeconds: prev.time || 0 };
      go ? p.loadVideoById(o) : p.cueVideoById(o);
    }
  } catch (e) { /* */ }
  MUS.vol = null;
  musVolume(false);
  placeDock();
}

// walk-on kiezen (Instellingen → Spelers)
const WO = { name: null, cand: null, results: null };
function parseYt(u) {
  const s = String(u || "").trim();
  const m = /(?:[?&]v=|youtu\.be\/|\/shorts\/|\/embed\/|\/live\/)([A-Za-z0-9_-]{11})/.exec(s) || /^([A-Za-z0-9_-]{11})$/.exec(s);
  if (!m) return null;
  let tt = 0;
  const tm = /[?&](?:t|start)=([0-9hms]+)/.exec(s);
  if (tm) {
    if (/^\d+$/.test(tm[1])) tt = +tm[1];
    else { const g = /^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$/.exec(tm[1]) || []; tt = (+g[1] || 0) * 3600 + (+g[2] || 0) * 60 + (+g[3] || 0); }
  }
  return { video: m[1], t: tt };
}
function openWalkon(name) {
  const reg = (H.players || []).find((p) => nkey(p.name) === nkey(name));
  WO.name = name;
  WO.cand = reg && reg.walkon ? { ...reg.walkon } : null;
  WO.results = null;
  $("wo_title").textContent = t("wo_title", { name });
  $("wo_q").value = ""; $("wo_link").value = ""; $("wo_err").textContent = "";
  $("wodlg").classList.remove("hidden");
  renderWo();
}
function renderWo() {
  const c = WO.cand;
  if (c && !c.title && S && S.music && S.music.vid === c.video && S.music.title) c.title = S.music.title;
  $("wo_cur").innerHTML = c
    ? `<img src="https://i.ytimg.com/vi/${esc(c.video)}/mqdefault.jpg" alt=""><div><b>${esc(c.title || c.video)}</b><small>${esc(t("wo_from", { t: fmtT(c.start), d: c.dur }))}</small></div>`
    : `<p class="hint">${esc(t("wo_none"))}</p>`;
  document.querySelector("#wodlg .wo_time").classList.toggle("hidden", !c);
  if (c) {
    $("wo_start").textContent = fmtT(c.start);
    if (document.activeElement !== $("wo_dur")) $("wo_dur").value = c.dur;
    $("wo_dur_v").textContent = c.dur + " s";
  }
  const u = ytUser();
  $("wo_sform").classList.toggle("hidden", !u.logged_in);
  $("wo_gate").classList.toggle("hidden", !!u.logged_in);
  $("wo_results").innerHTML = WO.results === "busy" ? `<li class="mu_info">${esc(t("mu_searching"))}</li>`
    : Array.isArray(WO.results) ? (WO.results.length ? WO.results.map((it, i) => muRow(it, i, "wo")).join("") : `<li class="mu_info">${esc(t("mu_noresults"))}</li>`) : "";
  const reg = (H.players || []).find((p) => nkey(p.name) === nkey(WO.name || ""));
  $("wo_remove").classList.toggle("hidden", !(reg && reg.walkon));
  $("wo_save").disabled = !c;
}
async function woSend(cmd) {
  $("wo_err").textContent = "";
  try {
    const r = await fetch("/api/cmd", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cmd) });
    const j = await r.json();
    if (!j.ok) { $("wo_err").textContent = muErrText(j.error); return false; }
    render(j.state);
    return true;
  } catch (e) { $("wo_err").textContent = t("no_conn"); return false; }
}
function bindWalkon() {
  $("wo_close").onclick = () => $("wodlg").classList.add("hidden");
  $("wodlg").addEventListener("click", (e) => {
    if (e.target === $("wodlg")) { $("wodlg").classList.add("hidden"); return; }
    const st = e.target.closest("[data-ws]");
    if (st && WO.cand) { WO.cand.start = Math.max(0, WO.cand.start + +st.dataset.ws); renderWo(); return; }
    const row = e.target.closest(".mu_row[data-wo]");
    if (row) {
      const it = WO.results[+row.dataset.wo];
      WO.cand = { video: it.id, title: it.title, start: 45, dur: WO.cand ? WO.cand.dur : 20 };
      renderWo();
    }
  });
  $("wo_dur").addEventListener("input", () => { if (WO.cand) { WO.cand.dur = +$("wo_dur").value; $("wo_dur_v").textContent = WO.cand.dur + " s"; renderWo(); } });
  $("wo_sform").addEventListener("submit", async (e) => {
    e.preventDefault();
    const q = $("wo_q").value.trim();
    if (!q) return;
    WO.results = "busy"; renderWo();
    try { WO.results = await ytGet(`/api/yt/search?type=video&q=${encodeURIComponent(q)}`); }
    catch (err) { WO.results = []; $("wo_err").textContent = ytErr(err.message); }
    renderWo();
  });
  $("wo_lform").addEventListener("submit", (e) => {
    e.preventDefault();
    const r = parseYt($("wo_link").value);
    if (!r) { $("wo_err").textContent = t("wo_badlink"); return; }
    $("wo_err").textContent = "";
    WO.cand = { video: r.video, title: "", start: r.t || 45, dur: WO.cand ? WO.cand.dur : 20 };
    $("wo_link").value = "";
    renderWo();
  });
  $("wo_try").onclick = () => {
    const c = WO.cand;
    if (c) woSend({ type: "music_load", video: c.video, title: c.title, start: c.start, end: c.start + c.dur });
  };
  $("wo_stop").onclick = () => woSend({ type: "music_ctl", action: "stop" });
  $("wo_save").onclick = async () => {
    const c = WO.cand;
    if (!c) return;
    if (!c.title && S.music && S.music.vid === c.video) c.title = S.music.title;
    if (await woSend({ type: "player_walkon", name: WO.name, video: c.video, title: c.title, start: c.start, dur: c.dur })) {
      $("wodlg").classList.add("hidden");
      await loadHistory(true);
      renderSettings();
    }
  };
  $("wo_remove").onclick = async () => {
    if (await woSend({ type: "player_walkon", name: WO.name, clear: true })) {
      $("wodlg").classList.add("hidden");
      await loadHistory(true);
      renderSettings();
    }
  };
  // intro bedienen
  $("intro_next").onclick = () => showIntro(INTRO.i + 1);
  $("intro_skip").onclick = () => endIntro();
  document.addEventListener("keydown", (e) => {
    if (!INTRO.on) return;
    if (e.key === "Enter" || e.key === " " || e.key === "ArrowRight") showIntro(INTRO.i + 1);
    else if (e.key === "Escape") endIntro();
    else return;
    e.preventDefault();
    e.stopImmediatePropagation();
  }, true);
}

// ---- commentaar: korte uitroepen zoals een sportcommentator, bovenop de scheidsrechter
const COMMENT = {
  nl: {
    c180: ["Daar is ie... de maximale score!", "Drie keer in de triple twintig, prachtig!", "Wat een beurt!", "Kijk hem gaan!", "Dat is darten op z'n best!"],
    win: ["Wat een wedstrijd!", "Dik verdiend!", "Wat een prestatie, {name}!", "{name} pakt de winst, schitterend!", "Hij doet het gewoon!"],
    leg: ["Wat een finish!", "Strak uitgegooid!", "Daar gaat de dubbel in!", "Koelbloedig, {name}!", "Die laat zich niet kennen!"],
    ton140: ["Lekker gegooid!", "Dat is een prima beurt.", "Daar kan hij mee leven.", "Sterk, {name}!"],
    ton100: ["Netjes.", "De ton is binnen.", "Mooi zo."],
    out: ["En weg is hij!", "Die is eruit!", "Einde verhaal voor {name}.", "Daar gaat er weer een!", "Genadeloos!"],
    killer: ["Nu wordt het gevaarlijk!", "Pas op, jongens!", "{name} heeft het mes geslepen!", "Daar komt hij aan!"],
    bust: ["Oei, eentje te veel.", "Helaas, kapot gegooid.", "Dat gaat net mis.", "Pech voor {name}."],
    bull: ["Midden in de roos!", "Op de bull, prachtig!", "Daar zit hij, in het hart van het bord!"],
    halve: ["Au, dat doet pijn!", "Gehalveerd, sneu voor {name}."],
  },
  en: {
    c180: ["There it is... the maximum!", "Three in the treble twenty, beautiful!", "What a visit!", "Look at that!", "That's darts at its finest!"],
    win: ["What a match!", "Thoroughly deserved!", "What a performance, {name}!", "{name} takes it, brilliant!", "He's done it!"],
    leg: ["What a finish!", "Clinical checkout!", "And the double goes in!", "Ice cold, {name}!", "Lovely darts!"],
    ton140: ["Good darts!", "That's a strong visit.", "He'll be happy with that.", "Big score, {name}!"],
    ton100: ["Nicely done.", "The ton is in.", "Steady."],
    out: ["And he's gone!", "Out he goes!", "That's the end for {name}.", "Another one bites the dust!", "Ruthless!"],
    killer: ["Now it gets dangerous!", "Watch out, everyone!", "{name} is out for blood!", "Here he comes!"],
    bust: ["Oh, one too many.", "Busted, unlucky.", "Just over.", "Hard luck, {name}."],
    bull: ["Right in the bull!", "Bullseye, beautiful!", "Dead centre!"],
    halve: ["Ouch, that hurts!", "Halved, tough luck {name}."],
  },
};
const COMMENT_P = { some: { big: 0.85, mid: 0.4, small: 0.12 }, lots: { big: 1, mid: 0.85, small: 0.45 } };
let lastComment = "";
function commentary(fxList) {
  const lvl = COMMENT_P[vset().commentary || "off"];
  if (!lvl || !fxList || !fxList.length) return [];
  const pool = COMMENT[LANG] || COMMENT.nl;
  // het belangrijkste moment van deze beurt
  const rank = (f) => ({ win: 9, leg: 8, out: 7, killer: 6, bust: 5, halve: 5, bull: 3 }[f.type] ||
    (f.type === "ton" ? (f.score >= 180 ? 8.5 : f.score >= 140 ? 4 : 2) : 0));
  const f = fxList.slice().sort((x, y) => rank(y) - rank(x))[0];
  let key = f.type;
  if (f.type === "ton") key = f.score >= 180 ? "c180" : f.score >= 140 ? "ton140" : "ton100";
  const lines = pool[key];
  if (!lines) return [];
  const size = ["c180", "win", "leg", "out"].includes(key) ? "big" : ["ton100"].includes(key) ? "small" : "mid";
  if (Math.random() > lvl[size]) return [];
  let line = lines[Math.floor(Math.random() * lines.length)];
  if (line === lastComment && lines.length > 1) line = lines[(lines.indexOf(line) + 1) % lines.length];
  lastComment = line;
  const p = S && S.players && f.player !== undefined ? S.players[f.player] : null;
  return [line.replace("{name}", p ? p.name : "")];
}

// ---- het stem-menu
let elevenList = null;
const errText = (code) => {
  if (!code) return "";
  const c = String(code).split(":").pop();
  return { bad_key: t("v_err_bad_key"), quota: t("v_err_quota"), offline: t("v_err_offline"), no_key: t("v_err_no_key"),
    paid_plan: t("v_err_paid_plan"), blocked: t("v_err_blocked"), voice_not_found: t("v_err_voice_not_found"), busy: t("v_err_busy") }[c] ||
    t("v_err_other", { code: c });
};
function fillAzure(sel, lang, cur) {
  const list = { nl: [["nl-NL-MaartenNeural", "Maarten (NL, man)"], ["nl-BE-ArnaudNeural", "Arnaud (BE, man)"], ["nl-NL-FennaNeural", "Fenna (NL, vrouw)"], ["nl-NL-ColetteNeural", "Colette (NL, vrouw)"], ["nl-BE-DenaNeural", "Dena (BE, vrouw)"]],
    en: [["en-GB-RyanNeural", "Ryan (UK, man)"], ["en-GB-ThomasNeural", "Thomas (UK, man)"], ["en-US-GuyNeural", "Guy (US, man)"], ["en-GB-SoniaNeural", "Sonia (UK, vrouw)"]] }[lang];
  if (sel.dataset.k !== lang) { sel.innerHTML = list.map(([v, n]) => `<option value="${v}">${esc(n)}</option>`).join(""); sel.dataset.k = lang; }
  sel.value = cur;
}
function fillVoices() {
  const vs = vset();
  const server = !LOCAL && S && S.tts && "on" in S.tts;
  $("v_on").checked = !!vs.on;
  setSoundIcon(vs.on);
  $("v_rate").value = vs.rate; $("v_rate_val").textContent = (+vs.rate).toFixed(2);
  const vol = vs.volume ?? 1;
  $("v_volume").value = vol; $("v_volume_val").textContent = Math.round(vol * 100) + "%";
  $("v_comm").value = vs.commentary || "off";
  const prov = server ? vs.provider : (voiceCfg.engine === "browser" ? "browser" : "browser");
  $("v_prov").value = prov;
  [...$("v_prov").options].forEach((o) => { o.disabled = !server && o.value !== "browser"; });
  $("v_eleven").classList.toggle("hidden", !(server && prov === "elevenlabs"));
  $("v_azure").classList.toggle("hidden", !(server && prov === "azure"));
  $("v_clear").classList.toggle("hidden", !(server && (vs.has_eleven_key || vs.has_azure_key)));
  if (server) {
    $("v_ekey").placeholder = vs.has_eleven_key ? t("v_key_saved") : t("v_key_paste");
    $("v_akey").placeholder = vs.has_azure_key ? t("v_key_saved") : t("v_key_paste");
    if (document.activeElement !== $("v_areg")) $("v_areg").value = vs.azure_region || "";
    $("v_emodel").value = vs.eleven_model || "eleven_multilingual_v2";
    const es = $("v_evoice");
    const list = elevenList || (vs.eleven_voice ? [{ id: vs.eleven_voice, name: vs.eleven_voice_name || vs.eleven_voice, info: "" }] : []);
    const k = list.map((v) => v.id).join(",");
    if (es.dataset.k !== k) {
      es.innerHTML = `<option value="">${esc(t("v_pickvoice"))}</option>` +
        list.map((v) => `<option value="${esc(v.id)}">${esc(v.name)}${v.premade === undefined ? "" : " (" + (v.premade ? t("v_free") : t("v_paid")) + ")"}${v.info ? " · " + esc(v.info) : ""}</option>`).join("");
      es.dataset.k = k;
    }
    es.value = vs.eleven_voice || "";
    fillAzure($("v_anl"), "nl", vs.azure_voice_nl);
    fillAzure($("v_aen"), "en", vs.azure_voice_en);
  }
  const sv = serverVoice();
  const browser = !sv;
  $("v_voice_row").classList.toggle("hidden", !browser);
  $("v_pitch_row").classList.toggle("hidden", !browser);    // alleen de browserstem heeft toonhoogte
  let hint = "";
  if (sv) hint = t("v_active", { name: sv });
  else if (browser && (!server || prov === "browser" || !vs.available)) {
    // pas hier de (op de Pi trage) browserstemmen aanraken
    const sel = $("v_voice");
    const all = allVoices();
    const listKey = LANG + "|" + all.length;
    if (sel.dataset.k !== listKey) {
      const mine = all.filter((v) => voiceScore(v) > 0).sort((a, b) => voiceScore(b) - voiceScore(a));
      const opt = (v) => `<option value="${esc(v.name)}">${esc(v.name)} (${esc(v.lang)})</option>`;
      sel.innerHTML = `<option value="">${esc(t("v_auto"))}</option>` +
        (mine.length ? `<optgroup label="${esc(t("v_group"))}">${mine.slice(0, 40).map(opt).join("")}</optgroup>` : "");
      sel.dataset.k = listKey;
    }
    sel.value = voiceCfg.names[LANG] || "";
    if (sel.value !== (voiceCfg.names[LANG] || "")) sel.value = "";
    const v = pickVoice();
    hint = (server && prov !== "browser" ? t("v_nostem") + " " : "") + (v ? t("v_used", { name: v.name }) : t("v_none"));
    if (!hasSpeech) hint = t("v_nospeech");
  }
  if (server && vs.error) hint = errText(vs.error) + (sv && /^Piper/.test(sv) ? "" : "") + (vs.piper_installed && vs.error ? t("v_err_fallback") : "") + " " + hint;
  $("v_hint").textContent = hint.trim();
}
async function loadEleven() {
  $("v_hint").textContent = t("v_loading");
  try {
    const r = await (await fetch("/api/tts/voices?p=elevenlabs", { cache: "no-store" })).json();
    if (!r.ok) { $("v_hint").textContent = errText(r.error); return; }
    elevenList = r.voices;
    $("v_evoice").dataset.k = "";
    fillVoices();
    $("v_hint").textContent = t("v_loaded", { n: r.voices.length });
  } catch (e) { $("v_hint").textContent = errText("offline"); }
}
// ---- updates (Instellingen → Updates)
function upErr(code) {
  const c = String(code || "").replace(/^http_\d+$/, "other");
  const k = "up_e_" + c;
  const tx = t(k);
  return tx && tx !== k ? tx : t("up_e_other", { code });
}
let upLocalMsg = "";
function fillUpdate() {
  const u = S && S.update;
  const card = $("updatecard");
  if (!card) return;
  card.classList.toggle("hidden", !u || LOCAL);
  if (!u) return;
  $("up_cur").textContent = t("up_cur", { v: u.current });
  if (document.activeElement !== $("up_repo")) $("up_repo").value = u.repo || "";
  $("up_token").placeholder = u.has_token ? t("up_token_saved") : "";
  $("up_auto").checked = !!u.auto;
  const st = u.status || {};
  const lv = u.latest && u.latest.version;
  const avail = st.state === "available" && lv;
  $("up_install").classList.toggle("hidden", !avail);
  if (avail) $("up_install").textContent = t("up_install_v", { v: lv });
  $("up_rollback").classList.toggle("hidden", !u.backup || u.backup === u.current);
  if (u.backup) $("up_rollback").textContent = t("up_rollback_v", { v: u.backup });
  let msg = { checking: t("up_s_checking"), latest: t("up_s_latest"), installing: t("up_s_installing"),
    available: t("up_s_available", { v: lv }), done: t("up_s_done", { v: st.version }), error: upErr(st.error) }[st.state] || "";
  if (upLocalMsg) { msg = upLocalMsg; upLocalMsg = ""; }
  if (u.needs_install) msg = (msg ? msg + " " : "") + t("up_run_install");
  $("up_status").textContent = msg;
  const notes = avail && u.latest.notes ? u.latest.notes : "";
  $("up_notes").classList.toggle("hidden", !notes);
  $("up_notes").textContent = notes;
}
async function updatePost(action) {
  try {
    const r = await (await fetch("/api/update", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action }) })).json();
    if (!r.ok) { upLocalMsg = upErr(r.error); fillUpdate(); }
  } catch (e) { upLocalMsg = upErr("offline"); fillUpdate(); }
}
async function uploadUpdate() {
  const f = $("up_file").files[0];
  if (!f) { $("up_status").textContent = t("up_pick"); return; }
  $("up_status").textContent = t("up_s_uploading");
  $("up_upload").disabled = true;
  try {
    const r = await (await fetch("/api/update/upload", { method: "POST", headers: { "Content-Type": "application/zip" }, body: f })).json();
    if (!r.ok) $("up_status").textContent = upErr(r.error);
    else $("up_status").textContent = t("up_s_installing");
  } catch (e) { $("up_status").textContent = upErr("offline"); }
  $("up_upload").disabled = false;
}

function setSoundIcon(on) { $("sound").classList.toggle("muted", !on); }
let lastTtsKey = "";
function refreshVoiceUi() {
  const k = JSON.stringify((S && S.tts) || {});
  if (k === lastTtsKey) return;
  lastTtsKey = k;
  if (!$("voicepanel").classList.contains("hidden") || view === "settings") fillVoices();
  else setSoundIcon(vset().on);
}

// ---------------------------------------------------------------- animaties
const cardFxMap = {};   // spelerindex -> {cls, until}
function cardFx(i) { const f = cardFxMap[i]; return f && f.until > Date.now() ? f.cls : ""; }
function markCard(i, cls, ms) {
  cardFxMap[i] = { cls, until: Date.now() + ms };
  const el = document.querySelector(`.player[data-i="${i}"]`);
  if (el) { el.classList.remove(cls); void el.offsetWidth; el.classList.add(cls); }
}
const DART_SVG = `<svg class="dart" width="120" height="40" viewBox="0 0 120 40"><path d="M2 20 L22 17 L22 23 Z" fill="#cfd6de"/><rect x="22" y="16" width="44" height="8" rx="3" fill="#8a94a3"/><rect x="66" y="18" width="22" height="4" fill="#5b6470"/><path d="M88 20 L118 4 L106 20 L118 36 Z" fill="#ef5350"/></svg>`;
const fxQueue = [];
let fxBusy = false;
function runFx(list) { fxQueue.push(...list); if (!fxBusy) nextFx(); }
let confettiRun = 0;
function clearFx() {
  fxQueue.length = 0; $("fxlayer").innerHTML = "";
  confettiRun++;
  const cv = $("confetti"); cv.getContext("2d").clearRect(0, 0, cv.width, cv.height);
}
function nextFx() {
  const f = fxQueue.shift();
  if (!f) { fxBusy = false; return; }
  fxBusy = true;
  setTimeout(nextFx, showFx(f));
}
function addFx(html, ms) {
  const d = document.createElement("div");
  d.innerHTML = html;
  const nodes = [...d.children];
  nodes.forEach((n) => $("fxlayer").appendChild(n));
  setTimeout(() => nodes.forEach((n) => n.remove()), ms);
}
function showFx(f) {
  const p = S && S.players ? S.players[f.player] : null;
  const name = p ? esc(p.name) : "";
  if (f.type === "out") {
    addFx(`<div class="fx-flash"></div><div class="fx fx-out">${DART_SVG}<div class="who">${name}</div><div class="stamp">${t("fx_out")}</div></div>`, 2400);
    document.body.classList.remove("shake"); void document.body.offsetWidth; document.body.classList.add("shake");
    markCard(f.player, "ko", 1000);
    return 2300;
  }
  if (f.type === "win") { if (display.fx) confetti(p ? COLORS[p.color % COLORS.length] : null); return 300; }
  if (f.type === "killer") {
    addFx(`<div class="fx fx-toast">${t("fx_killer", { name })}</div>`, 2000);
    markCard(f.player, "glow", 2900);
    return 1400;
  }
  if (f.type === "ton") {
    addFx(`<div class="fx fx-pop ${f.score === 180 ? "big" : ""}">${f.score}!${f.pts === 0 ? "" : `<small>${t("fx_pts", { n: 3 })}</small>`}</div>`, 1700);
    if (f.score === 180) { document.body.classList.remove("shake"); void document.body.offsetWidth; document.body.classList.add("shake"); }
    return 1500;
  }
  if (f.type === "leg") {
    addFx(`<div class="fx fx-toast">${t("fx_leg")} ${name}${f.score ? ` · ${f.score}` : ""}</div>`, 2200);
    markCard(f.player, "glow", 2400);
    return 1600;
  }
  if (f.type === "bust") {
    addFx(`<div class="fx fx-pop bust">${t("fx_bust")}</div>`, 1200);
    return 900;
  }
  if (f.type === "bull") {
    addFx(`<div class="fx fx-pop">${esc(f.label)}!<small>${t("fx_pts", { n: f.label === "Bullseye" ? 3 : 1 })}</small></div>`, 1500);
    return 1300;
  }
  return 0;
}
function confetti(main) {
  const run = ++confettiRun;
  const cv = $("confetti");
  const ctx = cv.getContext("2d");
  const dpr = window.devicePixelRatio || 1;
  cv.width = innerWidth * dpr; cv.height = innerHeight * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const cols = [main || "#ffca28", "#ffca28", "#ffffff", ...COLORS.slice(0, 6)];
  const parts = Array.from({ length: display.perf ? 70 : 260 }, (_, i) => ({
    x: innerWidth / 2 + (Math.random() - .5) * 120, y: innerHeight * .55,
    vx: (Math.random() - .5) * 18, vy: -8 - Math.random() * 14,
    w: 6 + Math.random() * 8, h: 8 + Math.random() * 12, r: Math.random() * 6, vr: (Math.random() - .5) * .4,
    c: cols[i % cols.length], delay: Math.random() * 25,
  }));
  const t0 = performance.now();
  function frame(t) {
    if (run !== confettiRun) return;            // gestopt (ander scherm / nieuw potje)
    const age = t - t0;
    ctx.clearRect(0, 0, innerWidth, innerHeight);
    const end = display.perf ? 3800 : 6200;     // Pi: korter, zodat het scherm snel weer vrij is
    ctx.globalAlpha = age > end - 1200 ? Math.max(0, 1 - (age - (end - 1200)) / 1200) : 1;
    for (const q of parts) {
      if (q.delay > 0) { q.delay--; continue; }
      q.vy += 0.32; q.vx *= 0.99; q.vy *= 0.99; q.x += q.vx; q.y += q.vy; q.r += q.vr;
      ctx.save(); ctx.translate(q.x, q.y); ctx.rotate(q.r);
      ctx.fillStyle = q.c; ctx.fillRect(-q.w / 2, -q.h / 2, q.w, q.h * Math.abs(Math.cos(q.r * 2)));
      ctx.restore();
    }
    if (age < end) requestAnimationFrame(frame); else ctx.clearRect(0, 0, innerWidth, innerHeight);
  }
  requestAnimationFrame(frame);
}

// stem + animaties één keer per nieuwe spelversie (niet bij herladen of dubbele updates)
function feedback() {
  if (lastVersion === null) { lastVersion = S.version; return; }
  if (S.version === lastVersion) return;
  lastVersion = S.version;
  if (S.phase === "select" || S.phase === "setup" || S.phase === "bulloff" || (S.phase === "play" && S.turn_no === 1 && !S.darts.length && isOther() && S.leg_no === 0)) clearFx();   // nieuw potje: oude animaties weg
  const said = [...(S.announce || []), ...commentary(S.fx)];
  if (said.length) sayPhrases(said);
  if (S.fx && S.fx.length) {
    if (S.fx.some((f) => f.type === "win")) {
      const wait = display.fx ? S.fx.reduce((a, f) => a + ({ out: 2300, killer: 1400, ton: 1500, bull: 1300, leg: 1600, bust: 900 }[f.type] || 0), 0) : 0;
      winnerHoldUntil = Date.now() + wait;
      $("winner").classList.add("hidden");
      setTimeout(() => render(S), wait + 20);
    }
    if (display.fx) runFx(S.fx);
  }
}

// ------------------------------------------------------ pijl corrigeren
function setFix(i, quiet) {
  fixIndex = i;
  $("board").classList.toggle("fixmode", i !== null);
  if (!quiet && S) render(S);
}

// --------------------------------------------------------------- weergave
// Per scherm bewaard (een monitor naast het bord wil vaak een andere zoom dan een tablet).
// Raspberry Pi / ARM-Linux herkennen: daar staat de prestatiemodus standaard aan
const IS_PI = /Linux (aarch64|armv\d)/i.test(navigator.userAgent) || /[?&]pi=1/.test(location.search);
const DISPLAY_DEFAULT = { zoom: 1, ui: 1.35, board: 0.7, split: 0.65, fx: true, awake: true, perf: IS_PI };
const display = Object.assign({}, DISPLAY_DEFAULT, store.get("afgooien.display", {}));
if (store.get("afgooien.uiScale", null) !== null && !store.get("afgooien.display", null)) display.ui = store.get("afgooien.uiScale", 1.35);
let uiScale = display.ui;
const pctTxt = (x) => Math.round(x * 100) + "%";
function applyScale() {
  display.ui = uiScale;
  const root = document.documentElement;
  root.style.setProperty("--ui", uiScale);
  root.classList.toggle("perf", !!display.perf);
  root.style.setProperty("--boardh", Math.round(display.board * 100) + "vh");
  root.style.setProperty("--lcol", Math.round((1 - display.split) * 100) + "fr");   // scores : dartbord
  root.style.setProperty("--rcol", Math.round(display.split * 100) + "fr");
  root.style.zoom = display.zoom === 1 ? "" : display.zoom;
  $("confetti").style.zoom = display.zoom === 1 ? "" : 1 / display.zoom;   // confetti altijd schermvullend
  store.set("afgooien.display", display);
  if ($("d_zoom")) {
    $("d_zoom").value = display.zoom; $("d_zoom_val").textContent = pctTxt(display.zoom);
    $("d_ui").value = uiScale; $("d_ui_val").textContent = pctTxt(uiScale / DISPLAY_DEFAULT.ui);
    $("d_board").value = display.board; $("d_board_val").textContent = pctTxt(display.board);
    $("d_split").value = display.split; $("d_split_val").textContent = pctTxt(display.split);
    $("d_fx").checked = display.fx; $("d_awake").checked = display.awake; $("d_perf").checked = !!display.perf;
  }
}
// Scherm wakker houden tijdens een potje (Wake Lock; vraagt niets aan de gebruiker).
let wakeLock = null;
const canWake = "wakeLock" in navigator;
async function syncWake() {
  const want = canWake && display.awake && S && (S.phase === "select" || S.phase === "play") && document.visibilityState === "visible";
  try {
    if (want && !wakeLock) { wakeLock = await navigator.wakeLock.request("screen"); wakeLock.addEventListener("release", () => { wakeLock = null; }); }
    else if (!want && wakeLock) { const w = wakeLock; wakeLock = null; await w.release(); }
  } catch (e) { wakeLock = null; }
}
function isFull() { return !!(document.fullscreenElement || document.webkitFullscreenElement); }
function toggleFull() {
  try {
    if (isFull()) (document.exitFullscreen || document.webkitExitFullscreen).call(document);
    else { const r = document.documentElement; (r.requestFullscreen || r.webkitRequestFullscreen).call(r); }
  } catch (e) { /* niet toegestaan */ }
}
function updateFullBtn() { if ($("d_full")) $("d_full").textContent = t(isFull() ? "set_full_exit" : "set_full"); }

// ------------------------------------------------- statusring en 100+-meter
function botTurn() {
  return !!(S && ["select", "play", "bulloff", "shootout"].includes(S.phase) && S.current !== null && S.players[S.current] && S.players[S.current].bot);
}
// [kleur, tekst]: groen = gooien, geel = (nog) niet gooien, rood = probleem
function boardStatus() {
  if (!S || !["select", "play", "bulloff", "shootout"].includes(S.phase)) return null;
  const src = S.source || {};
  const cur = S.players[S.current];
  if (src.enabled && !src.connected) return ["red", t("bs_noconn")];
  if (src.enabled && (src.board_offline || (src.board && /stop|error|fout|calibrat|kalibr/i.test(String(src.board))))) return ["red", t("bs_board", { b: boardName(src) })];
  if (cur && cur.bot) return ["yellow", t("bs_bot", { name: cur.name })];
  if (S.phase === "shootout" && S.shootout && S.shootout.choice === null) return ["yellow", t("bs_so_choose", { name: cur ? cur.name : "" })];
  if (S.pending) return ["yellow", t("bs_choose")];
  if (isOther() ? S.waiting : ((S.phase === "select" && S.sel_step === "done") || (S.phase === "play" && S.darts.length >= S.settings.darts_per_turn))) {
    return ["yellow", t("bs_takeout")];
  }
  if (src.enabled && src.board && /takeout/i.test(String(src.board))) return ["yellow", t("bs_takeout")];
  return ["green", cur ? t("bs_go", { name: cur.name }) : t("bs_go2")];
}
// Status van de Autodarts-detectie zoals Autodarts hem geeft, plus "niet verbonden" in de eigen taal.
// Autodarts-bediening (klik op de statuspil): aan/uit, reset, kalibreren, herstarten
function renderAdPanel() {
  const src = (S && S.source) || {};
  const live = !!(src.enabled && src.mode !== "test");
  if (!live) { $("adpanel").classList.add("hidden"); return; }
  const busy = src.busy;
  const stopped = /stop/i.test(String(src.board || ""));
  $("ad_state").innerHTML = !src.connected ? esc(t("bm_unreach"))
    : t("bm_state", { s: `<b>${esc(boardName(src) || "–")}</b>` }) + (busy ? ` · ${esc(t("bm_busy"))}` : "");
  $("ad_msg").textContent = src.msg || "";
  $("adpanel").querySelectorAll("[data-bm]").forEach((b) => {
    const a = b.dataset.bm;
    b.disabled = !!busy || !src.connected;
    b.classList.toggle("on", (a === "start" && src.connected && !stopped) || (a === "stop" && stopped) || busy === a);
  });
}
function boardName(src) {
  const b = src.board ? String(src.board) : "";
  if (!src.board_offline) return b;
  return b ? `${b} (${t("not_connected")})` : t("not_connected");
}
// laagste losse pijl met minstens `need` punten (voorkeur single, dan dubbel, triple, bull)
function minDart(need) {
  const opts = [];
  for (let n = 1; n <= 20; n++) { opts.push([n, `${n}`, 0], [2 * n, `D${n}`, 1], [3 * n, `T${n}`, 2]); }
  opts.push([25, "Bull", 3], [50, "Bullseye", 3]);
  const ok = opts.filter((o) => o[0] >= need).sort((a, b) => a[0] - b[0] || a[2] - b[2]);
  return ok.length ? ok[0][1] : null;
}
function tonHint() {
  if (!S || S.phase !== "play") return null;
  const ts = S.turn_score, left = S.settings.darts_per_turn - S.darts.length;
  if (!S.settings.ton_bonus) return S.darts.length ? { text: "" } : null;
  if (ts >= 100) return { cls: "ok", text: t("ton_ok") };
  if (!S.darts.length) return null;
  const need = 100 - ts;
  if (left <= 0 || need > 60 * left) return { cls: "no", text: t("ton_no") };
  if (left === 1) {
    return { cls: need <= 20 ? "easy" : need <= 40 ? "mid" : "hard", text: t("ton_last", { need, d: minDart(need) }) };
  }
  const per = Math.ceil(need / left);
  return { cls: per <= 20 ? "easy" : per <= 40 ? "mid" : "hard", text: t("ton_more", { need, left }) };
}

// ---------------------------------------------------------------- scorebord
let H = { version: -1, games: [] };
let statsTab = store.get("afgooien.statsTab", "rank");
let statsRange = store.get("afgooien.statsRange", "all");
let statsMode = store.get("afgooien.statsMode", "afgooien");
let rankSort = { key: "wins", dir: -1 };
const fmt1 = (x) => (Math.round(x * 10) / 10).toFixed(1).replace(".", t("dec"));
const fmt2 = (x) => (Math.round(x * 100) / 100).toFixed(2).replace(".", t("dec"));
const pct = (x) => Math.round(x * 100) + "%";
const nkey = (n) => String(n).trim().toLowerCase();

async function loadHistory(force) {
  try {
    if (!force && S && S.history_version === H.version) return;
    H = LOCAL ? await LOCAL.history() : await (await fetch("/api/history", { cache: "no-store" })).json();
    if (!$("stats").classList.contains("hidden")) renderStats();
    updateTodayLine();
    if (S && S.phase === "setup" && view === "home") updateHome();
    if (S && S.phase === "setup" && view === "settings") renderSettings();
    if (S && S.phase === "setup" && view === "lobby") renderChips();
    if (S && S.phase === "setup" && view === "players") renderPlayers();
  } catch (e) { /* geen geschiedenis beschikbaar */ }
}
function inRange(g, range, from, to) {
  if (range === "all") return true;
  const t = new Date(g.ended), now = new Date();
  if (range === "today") return t.toDateString() === now.toDateString();
  if (range === "custom") {
    const d = g.ended.slice(0, 10);
    return (!from || d >= from) && (!to || d <= to);
  }
  const days = { week: 7, month: 30, year: 365 }[range] || 7;
  return now - t <= days * 864e5;
}
const gmode = (g) => g.mode || "afgooien";
const SUMS = {
  afgooien: ["kills", "knocked", "gained", "darts", "useful", "outside", "triples", "doubles", "bulls", "tons", "turns"],
  x01: ["darts", "points", "f9_points", "f9_darts", "n180", "n140", "n100", "legs_total", "co_att", "co_hit", "busts"],
  countup: ["darts", "points", "score", "n180", "n140", "n100"],
  free: ["darts", "points", "score", "n180", "n140", "n100"],
};
for (const m of ["atc", "shanghai", "bobs27", "halveit", "cricket", "bulls", "doubles", "checkout", "killer", "golf", "gotcha"]) {
  SUMS[m] = ["darts", "hits", "score", "mtotal", "kills"];
}
const LOWER_BETTER = { golf: true };
function aggregate(games, mode) {
  const by = new Map();
  const chron = games.slice().sort((a, b) => (a.ended < b.ended ? -1 : a.ended > b.ended ? 1 : 0));
  const SUM = SUMS[mode || "afgooien"];
  const party = PARTY.includes(mode);
  const since = H.since || {};
  for (const g of chron) {
    for (const p of g.players) {
      const k = nkey(p.name);
      if (since[k] && g.ended < since[k]) continue;      // stats gereset of speler verwijderd
      let a = by.get(k);
      if (!a) {
        a = { name: p.name, games: 0, wins: 0, placeSum: 0, seconds: 0, best: null, streak: 0, bestStreak: 0,
              hico: 0, bestLeg: null, hiscore: 0, bestRound: 0, hiTurn: 0, bestScore: null, bestFinish: null };
        SUM.forEach((f) => (a[f] = 0));
        by.set(k, a);
      }
      a.name = p.name;
      a.bot = p.bot || 0;
      a.games++;
      a.placeSum += p.place || g.players.length;
      if (p.place === 1) { a.wins++; a.streak++; a.bestStreak = Math.max(a.bestStreak, a.streak); } else a.streak = 0;
      if (p.place === 2) a.seconds++;
      SUM.forEach((f) => (a[f] += p[f] || 0));
      a.avgP = (a.avgP || 0) + ((p.avg_points != null ? p.avg_points : p.points) || 0);
      a.avgD = (a.avgD || 0) + ((p.avg_darts != null ? p.avg_darts : p.darts) || 0);
      if (p.darts_to_target != null && (a.best === null || p.darts_to_target < a.best)) a.best = p.darts_to_target;
      if (p.hi_checkout) a.hico = Math.max(a.hico, p.hi_checkout);
      if (p.best_leg != null && (a.bestLeg === null || p.best_leg < a.bestLeg)) a.bestLeg = p.best_leg;
      if (p.score != null && mode === "countup") a.hiscore = Math.max(a.hiscore, p.score);
      if (p.best_round) a.bestRound = Math.max(a.bestRound, p.best_round);
      if (p.hi_turn) a.hiTurn = Math.max(a.hiTurn, p.hi_turn);
      if (party && p.score != null) {
        a.bestScore = a.bestScore === null ? p.score : LOWER_BETTER[mode] ? Math.min(a.bestScore, p.score) : Math.max(a.bestScore, p.score);
      }
      if (p.finish != null && (a.bestFinish === null || p.finish < a.bestFinish)) a.bestFinish = p.finish;
    }
  }
  return [...by.values()].map((a) => Object.assign(a, {
    winPct: a.games ? a.wins / a.games : 0,
    avgPlace: a.games ? a.placeSum / a.games : 0,
    ppt: a.turns ? (a.gained + a.knocked) / a.turns : 0,
    tpg: a.games ? a.triples / a.games : 0,
    dpg: a.games ? a.doubles / a.games : 0,
    hit: a.darts ? a.useful / a.darts : 0,
    avg: avg3(a.avgP || 0, a.avgD || 0),
    f9: avg3(a.f9_points || 0, a.f9_darts || 0),
    coPct: a.co_att ? a.co_hit / a.co_att : null,
    avgScore: a.games ? (a.score || 0) / a.games : 0,
    ppr: avg3(a.points || 0, a.darts),
    hitPct: a.darts ? (a.hits || 0) / a.darts : 0,
    mpr: avg3(a.mtotal || 0, a.darts),
  }));
}

// label/title zijn sleutels in i18n.js
const BASE_COLS = [
  { key: "name", label: "c_player", l: true, fmt: (a) => (a.bot ? "🤖 " : "") + esc(a.name), cls: "name l" },
  { key: "games", label: "c_games" },
  { key: "wins", label: "c_wins", cls: "big" },
  { key: "winPct", label: "c_winpct", fmt: (a) => pct(a.winPct) },
];
const MODE_COLS = {
  x01: [
    { key: "avg", label: "c_avg", title: "c_avg_t", fmt: (a) => fmt2(a.avg), cls: "big" },
    { key: "f9", label: "c_f9", title: "c_f9_t", fmt: (a) => fmt2(a.f9) },
    { key: "legs_total", label: "c_legs" },
    { key: "coPct", label: "c_co", title: "c_co_t", fmt: (a) => (a.coPct == null ? "–" : pct(a.coPct)) },
    { key: "hico", label: "c_hico", fmt: (a) => a.hico || "–" },
    { key: "bestLeg", label: "c_bestleg", title: "c_bestleg_t", asc: true, fmt: (a) => (a.bestLeg == null ? "–" : a.bestLeg) },
    { key: "n180", label: "c_180" }, { key: "n140", label: "c_140" }, { key: "n100", label: "c_100" },
    { key: "busts", label: "c_busts", asc: true },
  ],
  countup: [
    { key: "avgScore", label: "c_score", fmt: (a) => fmt1(a.avgScore), cls: "big" },
    { key: "hiscore", label: "c_hiscore" },
    { key: "ppr", label: "c_ppr", fmt: (a) => fmt2(a.ppr) },
    { key: "bestRound", label: "c_bestround" },
    { key: "n180", label: "c_180" }, { key: "n140", label: "c_140" }, { key: "n100", label: "c_100" },
  ],
  free: [
    { key: "ppr", label: "c_avg", fmt: (a) => fmt2(a.ppr), cls: "big" },
    { key: "bestRound", label: "c_bestround" },
    { key: "n180", label: "c_180" }, { key: "n140", label: "c_140" }, { key: "n100", label: "c_100" },
    { key: "darts", label: "g_darts" },
  ],
};
function partyCols(m) {
  const low = !!LOWER_BETTER[m];
  const cols = [
    { key: "avgScore", label: m === "atc" ? "c_targets" : "c_avgscore", fmt: (a) => fmt1(a.avgScore), cls: "big", asc: low },
    { key: "bestScore", label: "c_bestscore", asc: low, fmt: (a) => (a.bestScore == null ? "–" : a.bestScore) },
  ];
  if (m === "atc") cols.push({ key: "bestFinish", label: "c_bestfinish", asc: true, fmt: (a) => (a.bestFinish == null ? "–" : a.bestFinish) });
  if (m === "cricket") cols.push({ key: "mpr", label: "c_mpr", title: "c_mpr_t", fmt: (a) => fmt2(a.mpr) });
  if (m === "killer") cols.push({ key: "kills", label: "c_kills2" });
  cols.push({ key: "hitPct", label: "c_hit2", title: "c_hit2_t", fmt: (a) => pct(a.hitPct) }, { key: "darts", label: "g_darts" });
  return cols;
}
const rankCols = () => (statsMode === "afgooien" ? RANK_COLS : BASE_COLS.concat(MODE_COLS[statsMode] || partyCols(statsMode)));
const RANK_COLS = [
  { key: "name", label: "c_player", l: true, fmt: (a) => (a.bot ? "🤖 " : "") + esc(a.name), cls: "name l" },
  { key: "games", label: "c_games" },
  { key: "wins", label: "c_wins", cls: "big" },
  { key: "winPct", label: "c_winpct", fmt: (a) => pct(a.winPct) },
  { key: "avgPlace", label: "c_place", asc: true, fmt: (a) => fmt1(a.avgPlace) },
  { key: "kills", label: "c_kills", title: "c_kills_t" },
  { key: "ppt", label: "c_ppt", title: "c_ppt_t", fmt: (a) => fmt2(a.ppt) },
  { key: "tpg", label: "c_tpg", fmt: (a) => fmt1(a.tpg) },
  { key: "dpg", label: "c_dpg", fmt: (a) => fmt1(a.dpg) },
  { key: "hit", label: "c_hit", title: "c_hit_t", fmt: (a) => pct(a.hit) },
  { key: "best", label: "c_best", asc: true, title: "c_best_t", fmt: (a) => (a.best == null ? "–" : t("c_best_v", { n: a.best })) },
  { key: "bulls", label: "c_bulls" },
  { key: "tons", label: "c_tons", title: "c_tons_t" },
  { key: "outside", label: "c_out", asc: true },
];

function sortRows(rows) {
  const { key, dir } = rankSort;
  const val = (a) => (key === "name" ? nkey(a.name) : a[key] == null ? (dir < 0 ? -Infinity : Infinity) : a[key]);
  return rows.slice().sort((a, b) => {
    const x = val(a), y = val(b);
    if (x !== y) return (x < y ? -1 : 1) * dir;
    return b.wins - a.wins || b.winPct - a.winPct || a.avgPlace - b.avgPlace;
  });
}

function renderStats() {
  if (statsTab === "h2h" && statsMode !== "afgooien") statsTab = "rank";
  document.querySelectorAll("#stats .tab").forEach((b) => {
    b.classList.toggle("active", b.dataset.tab === statsTab);
    b.classList.toggle("hidden", b.dataset.tab === "h2h" && statsMode !== "afgooien");
  });
  $("statsrange").value = statsRange;
  $("statsmode").value = statsMode;
  const all = (H.games || []).filter((g) => gmode(g) === statsMode);
  const games = all.filter((g) => inRange(g, statsRange));
  const total = all.length;
  $("statscount").textContent = t("sb_count", { games: t("games_n", { n: games.length }), total });
  $("statsclear").disabled = !total;
  const body = $("statsbody");
  if (!games.length) {
    body.innerHTML = `<div class="statsempty">${t(statsRange === "today" ? "sb_empty_today" : "sb_empty")}</div>`;
    return;
  }
  const rows = aggregate(games, statsMode);
  if (statsTab === "rank") body.innerHTML = rankTable(rows);
  else if (statsTab === "awards") body.innerHTML = awardsHtml(rows);
  else if (statsTab === "h2h") body.innerHTML = h2hHtml(games);
  else body.innerHTML = gamesHtml(games);
}

function rankTable(rows) {
  const sorted = sortRows(rows);
  const COLS = rankCols();
  const head = COLS.map((c) => `<th class="${c.l ? "l" : ""} ${rankSort.key === c.key ? "sorted" : ""}" data-sort="${c.key}" title="${esc(t(c.title || "sort"))}">${t(c.label)}${rankSort.key === c.key ? (rankSort.dir < 0 ? " ▾" : " ▴") : ""}</th>`).join("");
  const medal = ["🥇", "🥈", "🥉"];
  const body = sorted.map((a, i) => `<tr><td class="l"><span class="medal">${rankSort.key === "wins" && i < 3 && a.wins ? medal[i] : i + 1 + "."}</span></td>` +
    COLS.map((c) => `<td class="${c.cls || ""}">${c.fmt ? c.fmt(a) : a[c.key]}</td>`).join("") + "</tr>").join("");
  return `<table class="stats"><thead><tr><th class="l"></th>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function awardsHtml(rows) {
  const best = (f, ok = () => true, asc = false) => {
    const c = rows.filter((a) => ok(a) && f(a) != null && (asc || f(a) > 0));
    if (!c.length) return null;
    const v = asc ? Math.min(...c.map(f)) : Math.max(...c.map(f));
    return { who: c.filter((a) => f(a) === v).map((a) => esc(a.name)).join(" & "), v };
  };
  // [icoon, sleutel (aw_x, aw_x_v, aw_x_d), winnaar, opmaak waarde, poedelprijs]
  const list = statsMode === "x01" ? [
    ["👑", "champ", best((a) => a.wins), (v) => v],
    ["📈", "xavg", best((a) => a.avg, (a) => a.darts >= 30), fmt2],
    ["💯", "x180", best((a) => a.n180), (v) => v],
    ["🎯", "xco", best((a) => a.hico), (v) => v],
    ["⚡", "xleg", best((a) => a.bestLeg, () => true, true), (v) => v],
    ["🧊", "xcop", best((a) => a.coPct, (a) => a.co_att >= 10), pct],
    ["🔥", "streak", best((a) => a.bestStreak, (a) => a.bestStreak >= 2), (v) => v],
    ["🥈", "second", best((a) => a.seconds, (a) => a.seconds >= 2), (v) => v, true],
  ] : PARTY.includes(statsMode) ? [
    ["👑", "champ", best((a) => a.wins), (v) => v],
    ["🏆", "pbest", best((a) => a.bestScore, () => true, !!LOWER_BETTER[statsMode]), (v) => v],
    ["🎯", "phit", best((a) => a.hitPct, (a) => a.darts >= 30), pct],
    ["🔥", "streak", best((a) => a.bestStreak, (a) => a.bestStreak >= 2), (v) => v],
    ["🥈", "second", best((a) => a.seconds, (a) => a.seconds >= 2), (v) => v, true],
  ] : statsMode === "free" ? [
    ["📈", "fravg", best((a) => a.ppr, (a) => a.darts >= 30), fmt2],
    ["🚀", "curound", best((a) => a.bestRound), (v) => v],
    ["💯", "x180", best((a) => a.n180), (v) => v],
    ["🎯", "frdarts", best((a) => a.darts), (v) => v],
  ] : statsMode === "countup" ? [
    ["👑", "champ", best((a) => a.wins), (v) => v],
    ["🏆", "cubest", best((a) => a.hiscore), (v) => v],
    ["📈", "cuavg", best((a) => a.ppr, (a) => a.games >= 2), fmt2],
    ["🚀", "curound", best((a) => a.bestRound), (v) => v],
    ["💯", "x180", best((a) => a.n180), (v) => v],
    ["🔥", "streak", best((a) => a.bestStreak, (a) => a.bestStreak >= 2), (v) => v],
  ] : [
    ["👑", "champ", best((a) => a.wins), (v) => v],
    ["💀", "beul", best((a) => a.kills), (v) => v],
    ["⚡", "ppt", best((a) => a.ppt, (a) => a.turns >= 3), fmt2],
    ["🎯", "sharp", best((a) => a.hit, (a) => a.darts >= 15), pct],
    ["🚀", "fast", best((a) => a.best, () => true, true), (v) => v],
    ["🔺", "tri", best((a) => a.tpg), fmt1],
    ["✌️", "dbl", best((a) => a.dpg), fmt1],
    ["🐂", "bull", best((a) => a.bulls), (v) => v],
    ["💯", "ton", best((a) => a.tons), (v) => v],
    ["🔥", "streak", best((a) => a.bestStreak, (a) => a.bestStreak >= 2), (v) => v],
    ["🥈", "second", best((a) => a.seconds, (a) => a.seconds >= 2), (v) => v, true],
    ["🧱", "wall", best((a) => a.outside), (v) => v, true],
  ];
  const cards = list.filter((x) => x[2]).map(([ico, k, r, f, booby]) =>
    `<div class="award ${booby ? "booby" : ""}"><div class="ico">${ico}</div><div class="ttl">${t("aw_" + k)}</div>
     <div class="who">${r.who}</div><div class="val">${esc(t("aw_" + k + "_v", { v: f(r.v) }))}</div><div class="desc">${t("aw_" + k + "_d")}</div></div>`).join("");
  return `<div class="awards">${cards}</div>`;
}

function h2hHtml(games) {
  const names = new Map(), cnt = {};
  const since = H.since || {};
  for (const g of games) for (const p of g.players) {
    if (since[nkey(p.name)] && g.ended < since[nkey(p.name)]) continue;
    names.set(nkey(p.name), p.name);
    if (p.out_by) {
      const a = nkey(p.out_by), v = nkey(p.name);
      cnt[a] = cnt[a] || {};
      cnt[a][v] = (cnt[a][v] || 0) + 1;
    }
  }
  const total = (a) => Object.values(cnt[a] || {}).reduce((x, y) => x + y, 0);
  const keys = [...names.keys()].sort((a, b) => total(b) - total(a) || names.get(a).localeCompare(names.get(b)));
  const head = keys.map((k) => `<th>${esc(names.get(k))}</th>`).join("");
  const rows = keys.map((a) => `<tr><td class="l name">${esc(names.get(a))}</td>` + keys.map((v) => {
    if (a === v) return `<td class="self"></td>`;
    const n = (cnt[a] || {})[v] || 0;
    return `<td class="cnt ${n ? "" : "zero"}">${n}</td>`;
  }).join("") + `<td class="cnt">${total(a)}</td></tr>`).join("");
  return `<table class="stats h2h"><thead><tr><th class="l">${t("h2h_head")}</th>${head}<th>${t("h2h_total")}</th></tr></thead><tbody>${rows}</tbody></table>
    <p class="h2hnote">${t("h2h_note")}</p>`;
}

let gamesOrder = store.get("afgooien.gamesOrder", "new");
const whenTxt = (g) => { const d = new Date(g.ended); const p = (x) => String(x).padStart(2, "0"); return `${p(d.getDate())}-${p(d.getMonth() + 1)} ${p(d.getHours())}:${p(d.getMinutes())}`; };
const byDate = (a, b) => (a.ended < b.ended ? -1 : a.ended > b.ended ? 1 : 0);
function gamesHtml(games) {
  const list = games.slice().sort(byDate);
  if (gamesOrder !== "old") list.reverse();
  const tools = `<div class="listtools"><label>${t("g_sort")} <select id="gorder">
    <option value="new" ${gamesOrder !== "old" ? "selected" : ""}>${t("pl_order_new")}</option>
    <option value="old" ${gamesOrder === "old" ? "selected" : ""}>${t("pl_order_old")}</option></select></label></div>`;
  return tools + `<div class="gamelist">` + list.map((g) => gameRowHtml(g)).join("") + `</div>`;
}
function gameRowHtml(g, me) {
  {
    const [w, ...rest] = g.players;
    if (gmode(g) !== "afgooien") return otherGameRow(g, whenTxt(g), me);
    const when = whenTxt;
    const detail = g.players.map((p) => `<tr class="${me && nkey(p.name) === me ? "me" : ""}"><td class="l">${p.place}.</td><td class="l name">${esc(p.name)}</td><td>${p.number}</td><td>${p.kills}</td>
      <td>${fmt2(p.turns ? (p.gained + p.knocked) / p.turns : 0)}</td><td>${p.triples}</td><td>${p.doubles}</td>
      <td>${pct(p.darts ? p.useful / p.darts : 0)}</td><td>${p.darts}</td><td>${p.darts_to_target == null ? "–" : p.darts_to_target}</td>
      <td class="l">${p.out_by ? t("g_outby", { by: esc(p.out_by) }) : t("g_winner")}</td></tr>`).join("");
    return `<details class="gamerow"><summary><span class="when">${when(g)}</span>
      <span class="gwin">🏆 ${esc(w.name)} (${w.number})</span>
      <span class="rest">${rest.map((p) => `${p.place}. ${esc(p.name)}`).join(" · ")}</span>
      <span class="rest">· ${t("g_rounds", { n: g.rounds })}</span></summary>
      <table class="stats"><thead><tr><th class="l"></th><th class="l">${t("c_player")}</th><th>${t("g_num")}</th><th>${t("c_kills")}</th><th>${t("c_ppt")}</th>
      <th>${t("c_triples")}</th><th>${t("c_doubles")}</th><th>${t("c_hit")}</th><th>${t("g_darts")}</th><th>${t("g_to5")}</th><th class="l"></th></tr></thead><tbody>${detail}</tbody></table></details>`;
  }
}

function partyGameRow(g, when, me) {
  const [w, ...rest] = g.players;
  const detail = g.players.map((p) => `<tr class="${me && nkey(p.name) === me ? "me" : ""}"><td class="l">${p.place}.</td><td class="l name">${p.bot ? "🤖 " : ""}${esc(p.name)}</td>` +
    [p.score, p.hits, pct(p.darts ? p.hits / p.darts : 0), p.darts].map((c) => `<td>${c}</td>`).join("") + "</tr>").join("");
  return `<details class="gamerow"><summary><span class="when">${when}</span>
    <span class="gwin">🏆 ${esc(g.winner)} (${w.score})</span>
    <span class="rest">${rest.map((p) => `${p.place}. ${esc(p.name)}`).join(" · ")}</span></summary>
    <table class="stats"><thead><tr><th class="l"></th><th class="l">${t("c_player")}</th>${["c_score2", "c_hits", "c_hit2", "g_darts"].map((h) => `<th>${t(h)}</th>`).join("")}</tr></thead>
    <tbody>${detail}</tbody></table></details>`;
}

function otherGameRow(g, when, me) {
  if (PARTY.includes(gmode(g))) return partyGameRow(g, when, me);
  const x = gmode(g) === "x01";
  const [w, ...rest] = g.players;
  const head = x ? ["c_avg", "c_f9", "c_legs", "c_hico", "c_bestleg", "c_180", "c_140", "c_100", "g_darts"]
    : ["c_score", "c_ppr", "c_bestround", "c_180", "c_140", "c_100", "g_darts"];
  const cells = (p) => (x ? [fmt2(xavg(p)), fmt2(avg3(p.f9_points, p.f9_darts)), p.legs_total, p.hi_checkout || "–",
    p.best_leg == null ? "–" : p.best_leg, p.n180, p.n140, p.n100, p.darts]
    : [p.score, fmt2(avg3(p.points, p.darts)), p.best_round, p.n180, p.n140, p.n100, p.darts]);
  const detail = g.players.map((p) => `<tr class="${me && nkey(p.name) === me ? "me" : ""}"><td class="l">${p.place}.</td><td class="l name">${p.bot ? "🤖 " : ""}${esc(p.name)}</td>` +
    cells(p).map((c) => `<td>${c}</td>`).join("") + "</tr>").join("");
  const what = x ? `${g.settings.start} · ${cap(g.settings.out_mode)} out${g.settings.shootout === "on" ? " · " + t("chip_so") : ""}`
    : gmode(g) === "free" ? t("chip_free", { n: g.rounds })
    : g.settings && g.settings.elim ? t("chip_elim", { n: g.settings.elim }) : t("chip_rounds", { n: g.rounds });
  const wtxt = x ? `${esc(w.name)} (${fmt2(xavg(w))})` : gmode(g) === "free" ? `${esc(g.winner)} (${fmt2(avg3(w.score, w.darts))})` : `${esc(g.winner)} (${w.score})`;
  return `<details class="gamerow"><summary><span class="when">${when}</span>
    <span class="gwin">🏆 ${wtxt}</span>
    <span class="rest">${rest.map((p) => `${p.place}. ${esc(p.name)}`).join(" · ")}</span>
    <span class="rest">· ${esc(what)}</span></summary>
    <table class="stats"><thead><tr><th class="l"></th><th class="l">${t("c_player")}</th>${head.map((h) => `<th>${t(h)}</th>`).join("")}</tr></thead>
    <tbody>${detail}</tbody></table></details>`;
}

// ============================================================ spelerspagina
let plSel = store.get("afgooien.plSel", "");
let lastMailKey = "";
let plRange = store.get("afgooien.plRange", "month");
let plFrom = "", plTo = "";
let plMode = "all";
let plOrder = "new";
let plSort = store.get("afgooien.plSort", "recent");
const isoDay = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const dayTxt = (iso) => { const [y, m, d] = iso.slice(0, 10).split("-"); return `${d}-${m}-${y}`; };
function playerGames(name) {        // alle potjes van deze speler (na een eventuele stats-reset)
  const k = nkey(name), since = (H.since || {})[k];
  return (H.games || []).filter((g) => g.players.some((p) => nkey(p.name) === k) && !(since && g.ended < since));
}
function periodName() {
  if (plRange === "custom") return `${plFrom ? dayTxt(plFrom) : "…"} ${t("pl_to")} ${plTo ? dayTxt(plTo) : "…"}`;
  if (plRange === "today") return t("pr_today").toLowerCase() + " (" + dayTxt(isoDay(new Date())) + ")";
  return t("pr_" + plRange).toLowerCase();
}
// hoofdcijfer van één speler in één potje: [label, waarde-tekst, getal]
function keyStat(g, p) {
  const m = gmode(g);
  if (m === "afgooien") return [t("c_kills"), String(p.kills || 0), p.kills || 0];
  if (m === "x01") { const a = xavg(p); return [t("c_avg"), fmt2(a), a]; }
  if (m === "countup") return [t("c_score"), String(p.score), p.score];
  if (m === "free") { const a = avg3(p.score, p.darts); return [t("c_avg"), fmt2(a), a]; }
  return [t("c_score2"), String(p.score), p.score];
}
// per spel samenvatten voor deze speler (zelfde berekening als het scorebord)
function playerModes(name, games) {
  const k = nkey(name), out = [];
  const modes = [...new Set(games.map(gmode))];
  for (const m of modes) {
    const gs = games.filter((g) => gmode(g) === m);
    const a = aggregate(gs, m).find((r) => nkey(r.name) === k);
    if (!a) continue;
    let key, best;
    if (m === "afgooien") { key = [t("c_kills"), String(a.kills)]; best = [t("c_ppt"), fmt2(a.ppt)]; }
    else if (m === "x01") { key = [t("c_avg"), fmt2(a.avg)]; best = [t("c_hico"), a.hico || "–"]; }
    else if (m === "countup") { key = [t("c_score"), fmt1(a.avgScore)]; best = [t("c_hiscore"), a.hiscore]; }
    else if (m === "free") { key = [t("c_avg"), fmt2(a.ppr)]; best = [t("c_bestround"), a.bestRound]; }
    else { key = [m === "atc" ? t("c_targets") : t("c_avgscore"), fmt1(a.avgScore)]; best = [t("c_bestscore"), a.bestScore == null ? "–" : a.bestScore]; }
    out.push({ mode: m, a, key, best });
  }
  return out.sort((x, y) => y.a.games - x.a.games);
}
function playerSummary(name, games) {
  const k = nkey(name);
  let wins = 0, placeSum = 0, streak = 0, bestStreak = 0;
  for (const g of games.slice().sort(byDate)) {
    const p = g.players.find((q) => nkey(q.name) === k);
    placeSum += p.place || g.players.length;
    if (p.place === 1 && g.players.length > 1) { wins++; streak++; bestStreak = Math.max(bestStreak, streak); }
    else if (p.place === 1) { wins++; streak++; bestStreak = Math.max(bestStreak, streak); }
    else streak = 0;
  }
  const n = games.length;
  return { games: n, wins, winPct: n ? wins / n : 0, avgPlace: n ? placeSum / n : 0, bestStreak };
}
function renderPlayers() {
  const all = H.games || [];
  const reg = H.players || [];
  // iedereen die geregistreerd is of ooit gespeeld heeft (geen bots)
  const names = new Map();
  reg.forEach((p) => names.set(nkey(p.name), p.name));
  for (const g of all) for (const p of g.players) if (!p.bot && !names.has(nkey(p.name))) names.set(nkey(p.name), p.name);
  const q = nkey($("plsearch").value || "");
  let list = [...names.values()].map((n) => {
    const gs = playerGames(n);
    const sm = playerSummary(n, gs);
    const last = gs.length ? gs.reduce((a, g) => (g.ended > a ? g.ended : a), "") : "";
    return { name: n, ...sm, last };
  }).filter((r) => !q || nkey(r.name).includes(q));
  const srt = { recent: (a, b) => (b.last > a.last ? 1 : b.last < a.last ? -1 : 0), wins: (a, b) => b.wins - a.wins || b.games - a.games,
    games: (a, b) => b.games - a.games, name: (a, b) => a.name.localeCompare(b.name) }[plSort];
  list.sort(srt);
  if (!plSel || !names.has(nkey(plSel))) plSel = list.length ? list[0].name : "";
  $("plsort").value = plSort;
  $("plitems").innerHTML = list.length ? list.map((r, i) => {
    const c = COLORS[i % COLORS.length];
    return `<button class="plitem ${nkey(r.name) === nkey(plSel) ? "on" : ""}" data-name="${esc(r.name)}">
      <span class="av" style="background:${c}">${esc(r.name.slice(0, 1).toUpperCase())}</span>
      <span class="plin"><b>${esc(r.name)}</b><small>${r.games ? `${t("games_n", { n: r.games })} · ${r.wins} 🏆 · ${pct(r.winPct)}` : t("pl_never")}</small></span></button>`;
  }).join("") : `<div class="statsempty">${t("pl_none")}</div>`;
  renderPlayerMain();
}
function rangeButtons() {
  const rs = ["today", "week", "month", "year", "all", "custom"];
  return `<div class="seg plrange">${rs.map((r) => `<button data-r="${r}" class="${plRange === r ? "on" : ""}">${t("pr_" + r)}</button>`).join("")}</div>` +
    (plRange === "custom" ? `<div class="pldates">${t("pl_from")} <input type="date" id="plfrom" value="${plFrom}"> ${t("pl_to")} <input type="date" id="plto" value="${plTo}"></div>` : "");
}
function chartSvg(games) {
  // potjes en overwinningen per dag (of per week/maand bij een lange periode)
  if (!games.length) return "";
  const k = nkey(plSel);
  const days = games.map((g) => g.ended.slice(0, 10)).sort();
  const span = (new Date(days[days.length - 1]) - new Date(days[0])) / 864e5;
  const bucket = (iso) => (span > 400 ? iso.slice(0, 7) : span > 60 ? isoDay(new Date(new Date(iso).getTime() - ((new Date(iso).getDay() + 6) % 7) * 864e5)) : iso);
  const map = new Map();
  for (const g of games) {
    const b = bucket(g.ended.slice(0, 10));
    const v = map.get(b) || { g: 0, w: 0 };
    v.g++;
    if ((g.players.find((p) => nkey(p.name) === k) || {}).place === 1) v.w++;
    map.set(b, v);
  }
  const keys = [...map.keys()].sort().slice(-40);
  const max = Math.max(...keys.map((x) => map.get(x).g));
  const W = 640, Hh = 150, bw = Math.max(6, Math.min(34, (W - 20) / keys.length - 4));
  const step = (W - 20) / keys.length;
  const bars = keys.map((x, i) => {
    const v = map.get(x), hx = 10 + i * step + (step - bw) / 2;
    const hg = (v.g / max) * (Hh - 30), hw = (v.w / max) * (Hh - 30);
    const lab = x.length === 7 ? x.slice(5) + "-" + x.slice(2, 4) : x.slice(8, 10) + "-" + x.slice(5, 7);
    return `<g><title>${lab}: ${v.g} ${t("pl_chart_games")}, ${v.w} ${t("pl_chart_wins")}</title>
      <rect x="${hx}" y="${Hh - 18 - hg}" width="${bw}" height="${hg}" rx="3" class="cg"/>
      <rect x="${hx}" y="${Hh - 18 - hw}" width="${bw}" height="${hw}" rx="3" class="cw"/>
      ${keys.length <= 16 || i % Math.ceil(keys.length / 12) === 0 ? `<text x="${hx + bw / 2}" y="${Hh - 4}" class="cl">${lab}</text>` : ""}</g>`;
  }).join("");
  return `<svg class="plchart" viewBox="0 0 ${W} ${Hh}" preserveAspectRatio="none">${bars}</svg>
    <div class="plleg"><span class="lg"></span>${t("pl_chart_games")} <span class="lw"></span>${t("pl_chart_wins")}</div>`;
}
function renderPlayerMain() {
  const box = $("plmain");
  if (!plSel) { box.innerHTML = `<div class="card"><div class="statsempty">${t("pl_none")}</div></div>`; return; }
  const k = nkey(plSel);
  const allG = playerGames(plSel);
  const games = allG.filter((g) => inRange(g, plRange, plFrom, plTo));
  const sm = playerSummary(plSel, games);
  const modes = playerModes(plSel, games);
  const reg = (H.players || []).find((p) => nkey(p.name) === k);
  const last = allG.length ? allG.reduce((a, g) => (g.ended > a ? g.ended : a), "") : "";
  const idx = [...(H.players || [])].findIndex((p) => nkey(p.name) === k);
  const color = COLORS[(idx < 0 ? 0 : idx) % COLORS.length];
  const mail = S && S.mail;
  const canMail = !!(reg && reg.email && mail && mail.ready && !LOCAL);
  const mailHint = LOCAL ? "" : !reg || !reg.email ? t("pl_mail_noaddr") : !mail || !mail.ready ? t("pl_mail_nosetup") : "";
  const kpi = (v, l) => `<div class="kpi"><b>${v}</b><span>${l}</span></div>`;
  const fav = modes.length ? t("gm_" + modes[0].mode) : "–";
  let shown = games.filter((g) => plMode === "all" || gmode(g) === plMode).sort(byDate);
  if (plOrder === "new") shown.reverse();
  if (plOrder === "place") shown.sort((a, b) => (a.players.find((p) => nkey(p.name) === k).place || 9) - (b.players.find((p) => nkey(p.name) === k).place || 9) || byDate(b, a));
  const medal = (pl) => ({ 1: "🥇", 2: "🥈", 3: "🥉" }[pl] || pl + ".");
  const rows = shown.slice(0, 300).map((g) => {
    const p = g.players.find((q) => nkey(q.name) === k);
    const [kl, kv] = keyStat(g, p);
    const others = g.players.filter((q) => nkey(q.name) !== k).map((q) => esc(q.name));
    return `<details class="plgame"><summary>
      <span class="pgplace">${medal(p.place)}</span>
      <span class="pgwhen">${whenTxt(g)}</span>
      <span class="pgmode">${t("gm_" + gmode(g))}</span>
      <span class="pgkey"><small>${kl}</small> ${kv}</span>
      <span class="pgvs">${others.length ? t("pl_vs", { names: others.join(", ") }) : t("pl_solo")}</span></summary>
      ${gameRowHtml(g, k).replace(/^<details class="gamerow"><summary>[\s\S]*?<\/summary>/, "").replace(/<\/details>$/, "")}</details>`;
  }).join("");
  const modeOpts = [`<option value="all">${t("pl_allmodes")}</option>`].concat([...new Set(allG.map(gmode))].map((m) => `<option value="${m}" ${plMode === m ? "selected" : ""}>${t("gm_" + m)}</option>`)).join("");
  box.innerHTML = `
    <div class="card plhead">
      <div class="plwho"><span class="av big" style="background:${color}">${esc(plSel.slice(0, 1).toUpperCase())}</span>
        <div><h2>${esc(plSel)}</h2><span class="sub">${last ? t("pl_last", { when: whenTxt({ ended: last }) }) : t("pl_never")}${reg && reg.email ? " · ✉ " + esc(reg.email) : ""}</span></div>
        ${LOCAL ? "" : `<button id="plmail" class="ghost" ${canMail ? "" : "disabled"}>✉ ${t("pl_mail")}</button>`}</div>
      ${mailHint ? `<p class="hint">${mailHint}</p>` : ""}<p id="plmailmsg" class="hint"></p>
      ${rangeButtons()}
    </div>
    ${games.length ? `
    <div class="kpis">${kpi(sm.games, t("k_games"))}${kpi(sm.wins, t("k_wins"))}${kpi(pct(sm.winPct), t("k_winpct"))}${kpi(fmt1(sm.avgPlace), t("k_place"))}${kpi(sm.bestStreak, t("k_streak"))}${kpi(fav, t("k_fav"))}</div>
    <div class="plcols">
      <div class="card"><h3>${t("pl_permode")}</h3>
        <table class="stats plmodes"><thead><tr><th class="l">${t("pl_mode")}</th><th>${t("k_games")}</th><th>${t("k_wins")}</th><th>${t("k_winpct")}</th><th>${t("pl_key")}</th><th>${t("pl_best")}</th></tr></thead>
        <tbody>${modes.map((r) => `<tr><td class="l name">${t("gm_" + r.mode)}</td><td>${r.a.games}</td><td class="big">${r.a.wins}</td><td>${pct(r.a.winPct)}</td>
          <td><small>${r.key[0]}</small> ${r.key[1]}</td><td><small>${r.best[0]}</small> ${r.best[1]}</td></tr>`).join("")}</tbody></table></div>
      <div class="card"><h3>${t("pl_chart")}</h3>${chartSvg(games)}</div>
    </div>
    <div class="card"><div class="cardhead"><h3>${t("pl_games")}</h3>
      <div class="listtools"><select id="plmode">${modeOpts}</select>
      <select id="plorder"><option value="new" ${plOrder === "new" ? "selected" : ""}>${t("pl_order_new")}</option>
        <option value="old" ${plOrder === "old" ? "selected" : ""}>${t("pl_order_old")}</option>
        <option value="place" ${plOrder === "place" ? "selected" : ""}>${t("pl_order_place")}</option></select></div></div>
      <div class="plgames">${rows || `<div class="statsempty">${t("pl_empty_range")}</div>`}</div></div>`
    : `<div class="card"><div class="statsempty">${t("pl_empty_range")}</div></div>`}`;
}

// ---- e-mail met stats (opgemaakt met inline-stijlen, zodat het in elke mailapp goed oogt)
function mailHtml(name, games, period) {
  const k = nkey(name);
  const sm = playerSummary(name, games);
  const modes = playerModes(name, games);
  const td = "padding:8px 10px;border-bottom:1px solid #e6e9f0;text-align:center;font-size:14px;";
  const th = "padding:8px 10px;background:#f2f5fb;color:#56607a;font-size:12px;text-transform:uppercase;text-align:center;";
  const kpi = (v, l) => `<td style="padding:10px;text-align:center;background:#f6f8fc;border-radius:10px;">
      <div style="font:800 24px/1.1 Arial,sans-serif;color:#1d4ed8;">${v}</div><div style="font-size:12px;color:#6b7280;">${l}</div></td>`;
  const list = games.slice().sort(byDate).reverse().slice(0, 50).map((g) => {
    const p = g.players.find((q) => nkey(q.name) === k);
    const [kl, kv] = keyStat(g, p);
    const others = g.players.filter((q) => nkey(q.name) !== k).map((q) => esc(q.name)).join(", ");
    return `<tr><td style="${td}">${whenTxt(g)}</td><td style="${td}">${t("gm_" + gmode(g))}</td><td style="${td}font-weight:700;">${p.place === 1 ? "🏆 1" : p.place}</td>
      <td style="${td}">${kl}: <b>${kv}</b></td><td style="${td}color:#6b7280;">${others || "–"}</td></tr>`;
  }).join("");
  return `<div style="font-family:Arial,Helvetica,sans-serif;color:#111827;max-width:640px;margin:0 auto;">
  <div style="background:linear-gradient(90deg,#1d4ed8,#e8336f);color:#fff;padding:18px 20px;border-radius:14px 14px 0 0;">
    <div style="font:900 italic 22px Arial,sans-serif;letter-spacing:.5px;">AFGOOIEN</div><div style="font-size:13px;opacity:.9;">Darts · Party</div></div>
  <div style="border:1px solid #e6e9f0;border-top:0;padding:18px 20px;border-radius:0 0 14px 14px;">
  <p style="font-size:15px;">${esc(t("mail_hi", { name }))}</p><p style="font-size:15px;">${esc(t("mail_intro", { period }))}</p>
  <table style="width:100%;border-spacing:8px;"><tr>${kpi(sm.games, t("k_games"))}${kpi(sm.wins, t("k_wins"))}${kpi(pct(sm.winPct), t("k_winpct"))}${kpi(fmt1(sm.avgPlace), t("k_place"))}</tr></table>
  <h3 style="margin:18px 0 6px;font-size:16px;">${t("pl_permode")}</h3>
  <table style="width:100%;border-collapse:collapse;"><tr><th style="${th}text-align:left;">${t("pl_mode")}</th><th style="${th}">${t("k_games")}</th><th style="${th}">${t("k_wins")}</th><th style="${th}">${t("pl_key")}</th><th style="${th}">${t("pl_best")}</th></tr>
  ${modes.map((r) => `<tr><td style="${td}text-align:left;font-weight:700;">${t("gm_" + r.mode)}</td><td style="${td}">${r.a.games}</td><td style="${td}">${r.a.wins}</td>
    <td style="${td}">${r.key[0]}: <b>${r.key[1]}</b></td><td style="${td}">${r.best[0]}: <b>${r.best[1]}</b></td></tr>`).join("")}</table>
  <h3 style="margin:18px 0 6px;font-size:16px;">${t("pl_games")}</h3>
  <table style="width:100%;border-collapse:collapse;">${list}</table>
  <p style="margin-top:18px;font-size:13px;color:#6b7280;">${esc(t("mail_foot"))}</p></div></div>`;
}
function mailText(name, games, period) {
  const sm = playerSummary(name, games);
  const lines = [t("mail_hi", { name }), "", t("mail_intro", { period }), "",
    `${t("k_games")}: ${sm.games}   ${t("k_wins")}: ${sm.wins}   ${t("k_winpct")}: ${pct(sm.winPct)}   ${t("k_place")}: ${fmt1(sm.avgPlace)}`, ""];
  for (const r of playerModes(name, games)) lines.push(`${t("gm_" + r.mode)}: ${r.a.games} ${t("k_games").toLowerCase()}, ${r.a.wins} ${t("k_wins").toLowerCase()}, ${r.key[0]} ${r.key[1]}`);
  lines.push("", t("mail_foot"));
  return lines.join("\n");
}
async function mailPlayer(name, games, period) {
  const r = await (await fetch("/api/mail", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, subject: t("mail_subject", { name, period }), html: mailHtml(name, games, period), text: mailText(name, games, period) }) })).json();
  return r;
}
const mlErr = (code, detail) => { const k = "ml_e_" + code, tx = t(k); return (tx && tx !== k ? tx : t("ml_e_other", { code })) + (detail ? ` (${detail})` : ""); };

// ---- e-mailinstellingen
function fillMail() {
  const m = S && S.mail;
  const card = $("mailcard");
  card.classList.toggle("hidden", !m || LOCAL);
  if (!m) return;
  $("ml_state").textContent = m.ready ? t("ml_ready") : t("ml_notready");
  $("ml_state").classList.toggle("ok", !!m.ready);
  if (document.activeElement !== $("ml_preset")) $("ml_preset").value = m.preset;
  $("ml_custom").classList.toggle("hidden", m.preset !== "other");
  if (document.activeElement !== $("ml_host")) $("ml_host").value = m.host || "";
  if (document.activeElement !== $("ml_port")) $("ml_port").value = m.port || 587;
  if (document.activeElement !== $("ml_user")) $("ml_user").value = m.user || "";
  $("ml_pass").placeholder = m.has_password ? t("ml_pass_saved") : "";
  $("ml_help").textContent = t("ml_help_" + m.preset) !== "ml_help_" + m.preset && t("ml_help_" + m.preset) ? t("ml_help_" + m.preset) : t("ml_help_other");
}

function updateTodayLine() {
  const el = $("todayline");
  if (!S || S.phase !== "finished") { el.textContent = ""; return; }
  const today = (H.games || []).filter((g) => inRange(g, "today") && gmode(g) === (S.mode || "afgooien"));
  if (!today.length) { el.textContent = ""; return; }
  const rows = aggregate(today, S.mode || "afgooien");
  const parts = S.players.map((p) => rows.find((a) => nkey(a.name) === nkey(p.name)) || { name: p.name, wins: 0 })
    .sort((a, b) => b.wins - a.wins)
    .map((a, i) => (i === 0 && a.wins ? `<b>${esc(a.name)} ${a.wins}</b>` : `${esc(a.name)} ${a.wins}`));
  el.innerHTML = t("today_wins", { list: parts.join(" · ") });
}

function openStats() {
  clearFx();
  if (S && S.mode && S.phase !== "setup") { statsMode = S.mode; store.set("afgooien.statsMode", statsMode); }
  $("stats").classList.remove("hidden");
  renderStats();
  loadHistory(true);
}

// ------------------------------------------------------------ schermen
const DART_ICON = `<svg viewBox="0 0 64 20" aria-hidden="true"><path d="M2 10 L13 8.6 L13 11.4 Z" fill="#cfd6e2"/><rect x="13" y="7.6" width="22" height="4.8" rx="2" fill="#e9edf5"/><rect x="35" y="9" width="10" height="2" fill="#9aa4b5"/><path d="M45 10 L51 3 L63 3 L57 10 L63 17 L51 17 Z" fill="#e9edf5"/></svg>`;
let view = store.get("afgooien.view", "home");     // home | modes | lobby
function setView(v) { view = v; store.set("afgooien.view", v); showView(); requestAnimationFrame(placeDock); }
function showView() {
  const inGame = !!S && S.phase !== "setup";
  $("view-home").classList.toggle("hidden", inGame || view !== "home");
  $("view-modes").classList.toggle("hidden", inGame || view !== "modes");
  $("setup").classList.toggle("hidden", inGame || view !== "lobby");
  $("view-settings").classList.toggle("hidden", inGame || view !== "settings");
  $("view-players").classList.toggle("hidden", inGame || view !== "players");
  $("nav-players").classList.toggle("active", !inGame && view === "players");
  $("game").classList.toggle("hidden", !inGame);
  $("nav-home").classList.toggle("active", !inGame && view === "home");
  $("nav-settings").classList.toggle("active", !inGame && view === "settings");
  if (!inGame && view === "settings") {
    $("voicepanel").classList.add("hidden");
    $("voiceslot").appendChild($("voicebox"));
    fillVoices();
    renderSettings();
    fillUpdate();
    fillMail();
  }
  if (!inGame && view === "lobby") { renderChips(); renderLobbyMode(); }
  $("nav-play").classList.toggle("active", inGame || view === "modes" || view === "lobby");
  if (!inGame && view === "lobby" && !$("names").children.length) fillSetup();
  if (!inGame && view === "home") updateHome();
  if (!inGame && view === "players") renderPlayers();
}
function leaveGame(then) {
  const go = () => { $("names").innerHTML = ""; then(); send({ type: "reset" }); };
  if (S && S.phase !== "setup" && S.phase !== "finished") confirmDialog(t("q_stop"), go);
  else if (S && S.phase !== "setup") go();
  else then();
}
function updateHome() {
  const games = H.games || [];
  const el = $("homestats");
  if (!games.length) {
    el.innerHTML = `<div class="st"><b>${t("home_welcome")}</b><span>${t("home_first")}</span></div>`;
    return;
  }
  const rows = aggregate(games);
  const champ = rows.slice().sort((a, b) => b.wins - a.wins || b.winPct - a.winPct)[0];
  const today = games.filter((g) => inRange(g, "today")).length;
  const last = games[games.length - 1];
  el.innerHTML = `<div class="st"><b>${games.length}</b><span>${t("home_played")}</span></div>
    <div class="st"><b>${today}</b><span>${t("home_today")}</span></div>
    <div class="st"><b>${champ ? esc(champ.name) : "–"}</b><span>${t("home_champ", { n: champ ? champ.wins : 0 })}</span></div>
    <div class="st"><b>${esc(last.winner)}</b><span>${t("home_last")}</span></div>`;
}
function renderLobbyInfo() {
  $("pcount").textContent = `${$("names").children.length}/8`;
  const src = S.source || {};
  const pill = $("autopill");
  pill.className = "pill";
  if (src.mode === "test") { pill.textContent = t("a_test"); $("autotext").textContent = t("a_click"); }
  else if (!src.enabled) { pill.textContent = t("a_off"); $("autotext").textContent = t("a_click"); }
  else if (src.connected) { pill.textContent = t("a_on"); pill.classList.add("ok"); $("autotext").textContent = t("a_auto"); }
  else { pill.textContent = t("a_none"); pill.classList.add("bad"); $("autotext").textContent = t("a_start"); }
}

// --------------------------------------------------- opgeslagen spelers
function renderSettings() {
  const reg = H.players || [];
  $("regcount").textContent = reg.length;
  const rows = aggregate(H.games || []);
  $("playerlist").innerHTML = reg.length ? reg.map((p, i) => {
    const a = rows.find((r) => nkey(r.name) === nkey(p.name));
    const st = a ? t("set_pstats2", { games: t("games_n", { n: a.games }), wins: a.wins, pct: pct(a.winPct) }) : t("set_pnone");
    const c = COLORS[i % COLORS.length];
    return `<div class="preg"><div class="av" style="background:${c}">${esc(p.name.slice(0, 1).toUpperCase())}</div>
      <div><div class="pn">${esc(p.name)}</div><div class="ps">${st}</div>${p.walkon ? `<div class="pwo">${esc(t("wo_row", { title: p.walkon.title || p.walkon.video }))}</div>` : ""}</div>
      <input class="pmail" type="email" data-name="${esc(p.name)}" value="${esc(p.email || "")}" placeholder="${esc(t("pl_email_ph"))}" spellcheck="false">
      <div class="pa">${LOCAL ? "" : `<button class="ghost" data-act="player_walkon" data-name="${esc(p.name)}">🎵 ${t("wo_btn")}</button>`}
      <button class="ghost" data-act="player_rename" data-name="${esc(p.name)}">✎ ${t("set_rename")}</button>
      <button class="ghost" data-act="player_reset" data-name="${esc(p.name)}">${t("set_reset")}</button>
      <button class="ghost danger" data-act="player_delete" data-name="${esc(p.name)}">${t("set_delete")}</button></div></div>`;
  }).join("") : `<div class="statsempty">${t("set_noplayers")}</div>`;
  $("datainfo").textContent = LOCAL ? t("set_data_local") : t("set_data_dir", { dir: (S && S.data_dir) || t("set_data_dirx") });
  applyScale();
  updateFullBtn();
  $("d_awake_no").classList.toggle("hidden", canWake);
}
function renderChips() {
  const reg = H.players || [];
  const box = $("savedchips");
  if (!reg.length) { box.innerHTML = ""; return; }
  const inList = new Set([...$("names").querySelectorAll("input")].map((i) => nkey(i.value)));
  box.innerHTML = `<span class="lbl">${t("saved_players")}</span>` + reg.map((p) =>
    `<button class="chip ${inList.has(nkey(p.name)) ? "used" : ""}" data-name="${esc(p.name)}">${esc(p.name)}</button>`).join("");
}
function addSaved(name) {
  const rows = [...$("names").children];
  const empty = rows.find((li) => !li.querySelector("input").value.trim());
  if (empty) { empty.querySelector("input").value = name; empty.querySelector("select").value = "0"; empty.classList.remove("isbot"); }
  else if (rows.length < 8) addName(name, 0);
  renderChips();
}
// naam wijzigen: het naamveld van de speler wordt even een invulveld
function startRename(row, name) {
  const pn = row && row.querySelector(".pn");
  if (!pn || pn.querySelector("form")) return;
  pn.innerHTML = `<form class="rnform"><input maxlength="24" spellcheck="false" autocomplete="off" value="${esc(name)}">
    <button type="submit" class="primary">${t("set_rename_ok")}</button><button type="button" class="ghost" data-rncancel>✕</button></form>`;
  const inp = pn.querySelector("input");
  inp.focus(); inp.select();
  inp.addEventListener("keydown", (e) => { if (e.key === "Escape") renderSettings(); });
  pn.querySelector("form").addEventListener("submit", (e) => {
    e.preventDefault();
    const nn = inp.value.trim();
    if (!nn || nn === name) { renderSettings(); return; }
    renamePlayer(name, nn);
  });
}
async function renamePlayer(old, nn) {
  $("regerr").textContent = "";
  const ok = await send({ type: "player_rename", name: old, new_name: nn });
  if (!ok) { $("regerr").textContent = $("setuperr").textContent || t("err_failed"); $("setuperr").textContent = ""; }
  else {
    // ook in de lobby en op de spelerspagina meteen de nieuwe naam
    const same = (x) => nkey(x || "") === nkey(old);
    store.set("afgooien.players", (store.get("afgooien.players", []) || []).map((r) => (r && !r.bot && same(r.name) ? { ...r, name: nn } : r)));
    [...$("names").children].forEach((li) => {
      const i = li.querySelector("input"), sel = li.querySelector("select");
      if (i && same(i.value.trim()) && !(sel && +sel.value)) i.value = nn;
    });
    if (same(plSel)) { plSel = nn; store.set("afgooien.plSel", plSel); }
  }
  await loadHistory(true);
  renderSettings();
  renderChips();
}
async function playerAction(act, name) {
  $("regerr").textContent = "";
  const ok = await send({ type: act, name });
  if (!ok) { $("regerr").textContent = $("setuperr").textContent || t("err_failed"); $("setuperr").textContent = ""; }
  await loadHistory(true);
  renderSettings();
}

// ------------------------------------------------------------- spelkeuze
const GAME_LIST = [
  { sec: "classic", modes: ["x01", "cricket"] },
  { sec: "party", modes: ["afgooien", "killer", "shanghai", "halveit", "golf", "gotcha"] },
  { sec: "training", modes: ["free", "countup", "atc", "bobs27", "doubles", "bulls", "checkout"] },
];
const TAGCLS = { classic: "tag-classic", party: "tag-party", training: "tag-practice" };
const ALL_MODES = GAME_LIST.flatMap((g) => g.modes);
const PARTY = ["atc", "shanghai", "bobs27", "halveit", "cricket", "bulls", "doubles", "checkout", "killer", "golf", "gotcha"];
const tagKey = (sec) => (sec === "training" ? "tag_practice" : "tag_" + sec);
const modeSec = (m) => (GAME_LIST.find((g) => g.modes.includes(m)) || GAME_LIST[1]).sec;
const isParty = () => !!(S && PARTY.includes(S.mode));
function renderModes() {
  $("modelist").innerHTML = GAME_LIST.map((g) => `<h2 class="section">${t("sec_" + g.sec)}</h2><div class="modes">` +
    g.modes.map((m) => `<button class="mode" data-mode="${m}"><span class="mode-top"><b>${esc(t("gm_" + m))}</b>` +
      `<span class="tag ${TAGCLS[g.sec]}">${t(tagKey(g.sec))}</span></span><span class="mode-desc">${esc(t("gd_" + m))}</span></button>`).join("") +
    "</div>").join("");
  const sel = $("statsmode");
  sel.innerHTML = ALL_MODES.map((m) => `<option value="${m}">${esc(t("gm_" + m))}</option>`).join("");
  sel.value = typeof statsMode === "undefined" ? "afgooien" : statsMode;
}
// Instellingen per spel: [sleutel, soort, standaard, opties of min/max, label]. seg-opties: [waarde, label]
const ONOFF = [[true, "o_on"], [false, "o_off"]];
const SCHEMA = {
  atc: [{ k: "zone", def: "any", opts: [["any", "o_any"], ["double", "o_double"], ["triple", "o_triple"]], label: "s_zone" },
    { k: "bull", def: true, opts: ONOFF, label: "s_bull_end" }, { k: "jump", def: false, opts: ONOFF, label: "s_jump" }],
  shanghai: [{ k: "rounds", def: 7, opts: [[7, "7"], [10, "10"], [20, "20"]], label: "s_rounds" },
    { k: "instant", def: true, opts: ONOFF, label: "s_instant" }],
  bobs27: [{ k: "bull", def: true, opts: ONOFF, label: "s_bull_round" }, { k: "negative", def: false, opts: ONOFF, label: "s_negative" }],
  halveit: [{ k: "start", def: 0, opts: [[0, "0"], [40, "40"]], label: "s_start_pts" }],
  cricket: [{ k: "scoring", def: "standard", opts: [["standard", "o_standard"], ["cutthroat", "o_cutthroat"], ["noscore", "o_noscore"]], label: "s_scoring" },
    { k: "rounds", def: 20, opts: [[0, "o_nolimit"], [10, "10"], [15, "15"], [20, "20"], [25, "25"]], label: "s_cr_rounds" }],
  bulls: [{ k: "rounds", def: 10, min: 1, max: 30, label: "s_rounds" }],
  doubles: [{ k: "order", def: "ordered", opts: [["ordered", "o_ordered"], ["random", "o_random"]], label: "s_order" },
    { k: "count", def: 21, min: 1, max: 21, label: "s_count" }],
  checkout: [{ k: "range", def: "all", opts: [["easy", "o_easy"], ["mid", "o_mid"], ["hard", "o_hard"], ["all", "o_all"]], label: "s_range" },
    { k: "rounds", def: 10, min: 1, max: 30, label: "s_rounds" }],
  killer: [{ k: "lives", def: 3, min: 1, max: 9, label: "s_lives" }, { k: "self", def: true, opts: ONOFF, label: "s_self" }],
  golf: [{ k: "holes", def: 9, opts: [[9, "9"], [18, "18"]], label: "s_holes" }],
  gotcha: [{ k: "target", def: 301, opts: [[201, "201"], [301, "301"], [501, "501"]], label: "s_target_pts" }],
};
const partySet = {};
for (const m of PARTY) {
  const def = {};
  for (const f of SCHEMA[m]) def[f.k] = f.def;
  partySet[m] = Object.assign(def, store.get("afgooien.set." + m, {}));
}
const optLabel = (o) => (String(o[1]).startsWith("o_") ? t(o[1]) : o[1]);
function renderGenCard() {
  const m = lobbyMode;
  if (!PARTY.includes(m)) return;
  const st = partySet[m], sec = modeSec(m);
  $("gentitle").textContent = t("gm_" + m);
  $("gentag").className = "tag " + TAGCLS[sec];
  $("gentag").textContent = t(tagKey(sec));
  $("gendesc").textContent = t("gr_" + m);
  const chips = [];
  $("genset").innerHTML = SCHEMA[m].map((f) => {
    if (f.opts) {
      const cur = f.opts.find((o) => o[0] === st[f.k]) || f.opts[0];
      chips.push(f.opts === ONOFF ? (st[f.k] ? t(f.label) : null) : `${t(f.label)}: ${optLabel(cur)}`);
      return `<div class="xrow"><span class="xl">${t(f.label)}</span><div class="seg" data-gseg="${f.k}">` +
        f.opts.map((o, i) => `<button data-i="${i}" class="${o[0] === st[f.k] ? "on" : ""}">${esc(optLabel(o))}</button>`).join("") + "</div></div>";
    }
    chips.push(`${t(f.label)}: ${st[f.k]}`);
    return `<div class="xrow"><span class="xl">${t(f.label)}</span><div class="stepper big"><button data-gstep="${f.k}" data-d="-1">−</button>` +
      `<span class="val">${st[f.k]}</span><button data-gstep="${f.k}" data-d="1">+</button></div></div>`;
  }).join("");
  $("genchips").innerHTML = chips.filter(Boolean).map((c) => `<span class="chipx">${esc(c)}</span>`).join("");
  store.set("afgooien.set." + m, st);
}
function genClick(e) {
  if (!PARTY.includes(lobbyMode)) return false;
  const f = (k) => SCHEMA[lobbyMode].find((x) => x.k === k);
  const sg = e.target.closest("[data-gseg] button");
  if (sg) { const fd = f(sg.parentElement.dataset.gseg); partySet[lobbyMode][fd.k] = fd.opts[+sg.dataset.i][0]; renderGenCard(); return true; }
  const sp = e.target.closest("[data-gstep]");
  if (sp) {
    const fd = f(sp.dataset.gstep), st = partySet[lobbyMode];
    st[fd.k] = Math.max(fd.min, Math.min(fd.max, st[fd.k] + +sp.dataset.d));
    renderGenCard();
    return true;
  }
  return false;
}
// Welk spel in de lobby staat (afgooien | x01 | countup) en de instellingen per spel.
const X01_SCORES = [101, 170, 201, 301, 401, 501, 601, 701, 801, 901, 1001];
const X01_DEF = { start: 501, match: "legs", legs: 1, sets: 1, in_mode: "straight", out_mode: "double", bulloff: "off", shootout: "off", walkon: "off" };
const X01_AVG = { 1: 25, 2: 35, 3: 45, 4: 55, 5: 65, 6: 80 };
let lobbyMode = store.get("afgooien.mode", "afgooien");
if (!["afgooien", "x01", "countup", "free", "atc", "shanghai", "bobs27", "halveit", "cricket", "bulls", "doubles", "checkout", "killer", "golf", "gotcha"].includes(lobbyMode)) lobbyMode = "afgooien";
const x01Set = Object.assign({}, X01_DEF, store.get("afgooien.x01", {}));
// elim = rondes per blok bij het toernooi (0 = uit); block onthoudt de laatst gekozen blokgrootte
const cuSet = Object.assign({ rounds: 8, elim: 0, block: 3 }, store.get("afgooien.countup", {}));
if (!(cuSet.block >= 1 && cuSet.block <= 30)) cuSet.block = 3;
if (!(cuSet.elim >= 0 && cuSet.elim <= 30)) cuSet.elim = 0;
if (cuSet.elim) cuSet.block = cuSet.elim;
const cap = (m) => m.charAt(0).toUpperCase() + m.slice(1);
const modeTitle = (m, st) => (m === "x01" ? String((st || x01Set).start) : t("gm_" + (m || "afgooien")));
function setLobbyMode(m) {
  lobbyMode = m;
  store.set("afgooien.mode", m);
  renderLobbyMode();
  relabelLobby();
}
function x01Chips(st) {
  const c = [String(st.start)];
  if (st.match === "sets") c.push(t("chip_first_sets", { n: st.sets }), t("chip_first_legs", { n: st.legs }));
  else c.push(t("chip_first_legs", { n: st.match === "off" ? 1 : st.legs }));
  c.push(t("chip_in", { m: cap(st.in_mode) }), t("chip_out", { m: cap(st.out_mode) }));
  c.push(st.bulloff === "off" ? t("chip_nobull") : t("chip_bull", { m: st.bulloff.toUpperCase() }));
  if (st.shootout === "on") c.push(t("chip_so"));
  if (st.walkon === "on") c.push(t("chip_wo"));
  return c;
}
function renderLobbyMode() {
  updateOrderHint();
  $("afgcard").classList.toggle("hidden", lobbyMode !== "afgooien");
  $("x01card").classList.toggle("hidden", lobbyMode !== "x01");
  $("cucard").classList.toggle("hidden", lobbyMode !== "countup");
  $("freecard").classList.toggle("hidden", lobbyMode !== "free");
  $("gencard").classList.toggle("hidden", !PARTY.includes(lobbyMode));
  renderGenCard();
  $("lobbytitle").textContent = modeTitle(lobbyMode);
  const s = x01Set;
  $("x01title").textContent = s.start;
  $("x_start").textContent = s.start;
  $("x_legs").textContent = s.legs;
  $("x_sets").textContent = s.sets;
  $("x_legs_lbl").textContent = t(s.match === "sets" ? "x_legs_set" : "x_legs_first");
  $("x_legsrow").classList.toggle("hidden", s.match === "off");
  $("x_setsrow").classList.toggle("hidden", s.match !== "sets");
  document.querySelectorAll("#x01card .seg").forEach((g) =>
    g.querySelectorAll("button").forEach((b) => b.classList.toggle("on", s[g.dataset.seg] === b.dataset.v)));
  $("x01chips").innerHTML = x01Chips(s).map((c) => `<span class="chipx">${esc(c)}</span>`).join("");
  $("x_help").textContent = t("xh_" + s.out_mode) + (s.in_mode !== "straight" ? t("xh_in_" + s.in_mode) : "") +
    (s.bulloff !== "off" ? t("xh_" + s.bulloff) : "") + (s.shootout === "on" ? t("xh_so") : "") + (s.walkon === "on" ? t("xh_wo") : "");
  $("cu_rounds").textContent = cuSet.rounds;
  $("cu_block").textContent = cuSet.block;
  $("cu_roundsrow").classList.toggle("hidden", cuSet.elim > 0);
  $("cu_blockrow").classList.toggle("hidden", !cuSet.elim);
  document.querySelectorAll("#cucard [data-cuseg] button").forEach((b) => b.classList.toggle("on", +b.dataset.v === (cuSet.elim ? 1 : 0)));
  $("cu_help").textContent = cuSet.elim > 0 ? t("cuh_elim", { n: cuSet.elim }) : t("cuh_rounds");
  store.set("afgooien.x01", x01Set);
  store.set("afgooien.countup", cuSet);
}
function lobbyStep(key, d) {
  if (key === "start") {
    const i = X01_SCORES.indexOf(x01Set.start);
    x01Set.start = X01_SCORES[Math.max(0, Math.min(X01_SCORES.length - 1, (i < 0 ? 5 : i) + d))];
  } else if (key === "legs") x01Set.legs = Math.max(1, Math.min(11, x01Set.legs + d));
  else if (key === "sets") x01Set.sets = Math.max(1, Math.min(7, x01Set.sets + d));
  else if (key === "rounds") cuSet.rounds = Math.max(1, Math.min(30, cuSet.rounds + d));
  else if (key === "block") { cuSet.block = Math.max(1, Math.min(30, cuSet.block + d)); cuSet.elim = cuSet.block; }
  renderLobbyMode();
}

// ------------------------------------------------------------------- setup
const LEVEL_PPT = { 1: "0,5", 2: "1,0", 3: "1,5", 4: "2,0", 5: "2,5", 6: "3,0" };
const botName = (lvl, taken) => {
  let base = t("bot_name", { l: lvl }), name = base, k = 2;
  while (taken.has(name.toLowerCase())) name = `${base} (${k++})`;
  return name;
};
function rowNames(except) {
  return new Set([...$("names").children].filter((li) => li !== except).map((li) => li.querySelector("input").value.trim().toLowerCase()));
}
function addName(value = "", bot = 0) {
  const ol = $("names");
  const li = document.createElement("li");
  const idx = ol.children.length;
  li.innerHTML = `<span class="dot" style="background:${COLORS[idx % COLORS.length]}"></span>
    <input maxlength="24"><select class="ptype">${ptypeOptions()}</select>
    <button class="ghost">✕</button>`;
  relabelRow(li, idx);
  const inp = li.querySelector("input"), sel = li.querySelector("select");
  inp.value = value;
  sel.value = String(bot || 0);
  li.classList.toggle("isbot", !!bot);
  sel.onchange = () => {
    const lvl = +sel.value;
    li.classList.toggle("isbot", !!lvl);
    const v = inp.value.trim();
    if (lvl && (!v || BOT_RE.test(v))) inp.value = botName(lvl, rowNames(li));
    if (!lvl && BOT_RE.test(v)) inp.value = "";
  };
  li.querySelector("button").onclick = () => { li.remove(); recolor(); if (S) renderLobbyInfo(); renderChips(); };
  inp.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); if (li === ol.lastElementChild) { addName(); ol.lastElementChild.querySelector("input").focus(); } }
  });
  ol.appendChild(li);
  if (S) renderLobbyInfo();
  return li;
}
function addBot() {
  const lvl = 3;
  addName(botName(lvl, rowNames(null)), lvl);
}
const BOT_RE = /^(Bot niveau|Bot level) \d/;
const levelPpt = (l) => LEVEL_PPT[l].replace(",", t("dec"));
function ptypeOptions() {
  const afg = lobbyMode === "afgooien";
  return `<option value="0">${esc(t("human"))}</option>` + [1, 2, 3, 4, 5, 6].map((l) => afg
    ? `<option value="${l}" title="${esc(t("bot_tip", { ppt: levelPpt(l) }))}">${esc(t("bot_opt", { l, ppt: levelPpt(l) }))}</option>`
    : `<option value="${l}" title="${esc(t("bot_tip_avg", { avg: X01_AVG[l] }))}">${esc(t("bot_opt_avg", { l, avg: X01_AVG[l] }))}</option>`).join("");
}
function relabelRow(li, i) {
  li.querySelector("input").placeholder = t("player_n", { n: i + 1 });
  li.querySelector("select").title = t("ptype_tip");
  li.querySelector("button").title = t("remove");
}
// na een taalwissel: keuzelijsten, voorbeeldtekst en automatische botnamen in de nieuwe taal
function relabelLobby() {
  [...$("names").children].forEach((li, i) => {
    const sel = li.querySelector("select"), v = sel.value, inp = li.querySelector("input");
    sel.innerHTML = ptypeOptions(); sel.value = v;
    relabelRow(li, i);
    if (+v && BOT_RE.test(inp.value.trim())) inp.value = botName(+v, rowNames(li));
  });
}
function recolor() {
  [...$("names").children].forEach((li, i) => {
    li.querySelector(".dot").style.background = COLORS[i % COLORS.length];
    relabelRow(li, i);
  });
}
function fillSetup() {
  let players = store.get("afgooien.players", null);
  if (!Array.isArray(players)) players = store.get("afgooien.names", ["", ""]).map((n) => ({ name: n, bot: 0 }));
  if (players.length < 2) players = [{ name: "", bot: 0 }, { name: "", bot: 0 }];
  $("names").innerHTML = "";
  players.forEach((p) => addName(p.name || "", p.bot || 0));
  const st = store.get("afgooien.settings", null);
  if (st) {
    $("target").value = st.target; $("dpt").value = st.darts_per_turn; $("elim").value = st.elimination;
    $("r_miss").checked = st.miss_penalty !== false; $("r_bull").checked = st.bull_bonus !== false; $("r_ton").checked = st.ton_bonus !== false;
  }
}
// Gooivolgorde: bij Afgooien en bij X01 met bull-off beslist de bull; anders mag hij geloot worden.
const bullDecides = (mode, st) => mode === "afgooien" || (mode === "x01" && st && st.bulloff && st.bulloff !== "off");
const randomOrderUsed = (mode, st) => !bullDecides(mode, st) && store.get("afgooien.randomOrder", true);
function shuffled(list) {
  const a = list.slice();
  for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; }
  return a;
}
function updateOrderHint() {
  const st = lobbyMode === "x01" ? x01Set : {};
  const bull = bullDecides(lobbyMode, st);
  $("lobbyorder").textContent = bull ? t("lobby_order") : t("lobby_order_list");
  $("lobbyorder").classList.toggle("hidden", !bull && store.get("afgooien.randomOrder", true));
  $("randrow").classList.toggle("hidden", bull);
  $("randorder").checked = store.get("afgooien.randomOrder", true);
}
function startGame() {
  $("setuperr").textContent = "";
  const rows = [...$("names").children].map((li) => ({ name: li.querySelector("input").value.trim(), bot: +li.querySelector("select").value }))
    .filter((r) => r.name);
  const settings = {
    target: +$("target").value || 5, darts_per_turn: +$("dpt").value || 3, elimination: $("elim").value,
    miss_penalty: $("r_miss").checked, bull_bonus: $("r_bull").checked, ton_bonus: $("r_ton").checked,
  };
  store.set("afgooien.players", rows);
  if (lobbyMode === "afgooien") store.set("afgooien.settings", settings);
  const st = lobbyMode === "x01" ? { ...x01Set } : lobbyMode === "countup" ? { ...cuSet } : lobbyMode === "free" ? {} : PARTY.includes(lobbyMode) ? { ...partySet[lobbyMode] } : settings;
  const order = randomOrderUsed(lobbyMode, st) ? shuffled(rows) : rows;
  send({ type: "new_game", mode: lobbyMode, players: order.map((r) => r.name), bots: order.map((r) => r.bot), settings: st });
}

// ------------------------------------------------------------------ events
function bind() {
  $("addname").onclick = () => addName();
  $("randorder").onchange = (e) => { store.set("afgooien.randomOrder", e.target.checked); updateOrderHint(); };
  applyI18n();
  applyScale();
  $("zoomin").onclick = () => { uiScale = Math.min(2.4, Math.round((uiScale + 0.1) * 10) / 10); applyScale(); };
  $("zoomout").onclick = () => { uiScale = Math.max(0.8, Math.round((uiScale - 0.1) * 10) / 10); applyScale(); };
  // instellingen: taal en weergave
  $("langpick").addEventListener("click", (e) => {
    const b = e.target.closest(".langbtn");
    if (!b || b.dataset.lang === LANG) return;
    setLang(b.dataset.lang);                    // meteen zichtbaar, de server bewaart hem voor alle schermen
    send({ type: "set_lang", lang: b.dataset.lang });
  });
  $("d_zoom").oninput = (e) => { display.zoom = +e.target.value; applyScale(); };
  $("d_ui").oninput = (e) => { uiScale = +e.target.value; applyScale(); };
  $("d_board").oninput = (e) => { display.board = +e.target.value; applyScale(); };
  $("d_split").oninput = (e) => { display.split = +e.target.value; applyScale(); };
  $("d_fx").onchange = (e) => { display.fx = e.target.checked; if (!display.fx) clearFx(); applyScale(); };
  $("d_awake").onchange = (e) => { display.awake = e.target.checked; applyScale(); syncWake(); };
  $("d_perf").onchange = (e) => { display.perf = e.target.checked; applyScale(); };
  $("d_full").onclick = toggleFull;
  $("d_reset").onclick = () => { Object.assign(display, DISPLAY_DEFAULT); uiScale = display.ui; applyScale(); };
  document.addEventListener("fullscreenchange", updateFullBtn);
  document.addEventListener("webkitfullscreenchange", updateFullBtn);
  document.addEventListener("visibilitychange", () => { wakeLock = null; syncWake(); });
  // Ctrl/Cmd + plus/min/0 = zoom van dit scherm (zelfde als de schuif bij Instellingen)
  document.addEventListener("keydown", (e) => {
    if (!(e.ctrlKey || e.metaKey) || e.altKey) return;
    const z = { "+": 0.05, "=": 0.05, "-": -0.05, "0": 0 }[e.key];
    if (z === undefined) return;
    e.preventDefault();
    display.zoom = z === 0 ? 1 : Math.min(2, Math.max(0.6, Math.round((display.zoom + z) * 100) / 100));
    applyScale();
  });
  $("turn").addEventListener("click", (e) => {
    const sl = e.target.closest(".slot.fixable");
    if (!sl) return;
    const i = +sl.dataset.fix;
    setFix(fixIndex === i ? null : i);
  });
  $("addbot").onclick = addBot;
  $("boardreset").onclick = () => send({ type: "board_reset" });
  $("start").onclick = startGame;
  $("miss").onclick = () => send({ type: "dart", number: 0, multiplier: 0 });
  $("undo").onclick = () => send({ type: "undo" });
  $("undowin").onclick = () => send({ type: "undo" });
  $("next").onclick = () => send({ type: "next" });
  $("again").onclick = () => {
    const st = { ...S.settings };
    delete st.seed;                       // nieuwe willekeurige doubles / finishes / nummers
    const ps = randomOrderUsed(S.mode || "afgooien", st) ? shuffled(S.players) : S.players;
    send({ type: "new_game", mode: S.mode || "afgooien", players: ps.map((p) => p.name), bots: ps.map((p) => p.bot || 0), settings: st });
  };
  $("newplayers").onclick = () => leaveGame(() => setView("lobby"));
  $("up_upload").onclick = uploadUpdate;
  $("up_save").onclick = async () => {
    const tok = $("up_token").value.trim();
    if (await send({ type: "update_config", repo: $("up_repo").value, auto: $("up_auto").checked, ...(tok ? { token: tok } : {}) })) {
      $("up_token").value = ""; upLocalMsg = t("up_saved"); fillUpdate();
    }
  };
  $("up_auto").onchange = (e) => send({ type: "update_config", auto: e.target.checked });
  $("up_check").onclick = async () => {
    if ($("up_repo").value.trim() !== ((S.update && S.update.repo) || "")) await send({ type: "update_config", repo: $("up_repo").value });
    updatePost("check");
  };
  $("up_install").onclick = () => confirmDialog(t("up_q_install", { v: S.update.latest.version }), () => updatePost("install"));
  $("up_rollback").onclick = () => confirmDialog(t("up_q_rollback", { v: S.update.backup }), () => updatePost("rollback"));
  $("winmodes").onclick = () => leaveGame(() => setView("modes"));
  $("winhome").onclick = () => leaveGame(() => setView("home"));
  // aan/uit: alleen op het scherm van de Pi zelf (en alleen als de server het toestaat)
  $("powerbtn").onclick = () => { $("powertext").textContent = t("pw_sub"); $("power").classList.remove("hidden"); };
  $("pwcancel").onclick = () => $("power").classList.add("hidden");
  const powerDo = async (action) => {
    try {
      const r = await (await fetch("/api/power", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action }) })).json();
      if (!r.ok) { $("powertext").textContent = t("pw_fail", { err: r.error || "?" }); return; }
      $("powertext").textContent = t(action === "reboot" ? "pw_bye_reboot" : "pw_bye");
      $("pwoff").disabled = $("pwreboot").disabled = $("pwcancel").disabled = true;
      stopSpeech();
    } catch (e) { $("powertext").textContent = t("pw_fail", { err: "offline" }); }
  };
  $("pwoff").onclick = () => powerDo("poweroff");
  $("pwreboot").onclick = () => powerDo("reboot");
  $("newgame").onclick = () => leaveGame(() => setView("lobby"));
  $("nav-home").onclick = () => leaveGame(() => setView("home"));
  $("brand").onclick = (e) => { e.preventDefault(); leaveGame(() => setView("home")); };
  $("nav-play").onclick = () => { if (!S || S.phase === "setup") setView("modes"); };
  $("nav-stats").onclick = openStats;
  // telefoon koppelen: QR-code met het adres van het telefoonscherm
  $("phonebtn").classList.toggle("hidden", !!LOCAL);
  $("phonebtn").onclick = () => {
    $("qrimg").src = "/qr.svg?t=" + Date.now();
    $("qrurl").textContent = (S && S.mobile_url) || "";
    $("qr").classList.remove("hidden");
  };
  $("qrclose").onclick = () => $("qr").classList.add("hidden");
  $("qr").addEventListener("click", (e) => { if (e.target.id === "qr") $("qr").classList.add("hidden"); });
  $("nav-settings").onclick = () => leaveGame(() => setView("settings"));
  $("regform").addEventListener("submit", (e) => {
    e.preventDefault();
    const n = $("regname").value.trim();
    if (!n) return;
    $("regname").value = "";
    playerAction("player_add", n);
  });
  $("playerlist").addEventListener("click", (e) => {
    if (e.target.closest("[data-rncancel]")) { renderSettings(); return; }
    const b = e.target.closest("button[data-act]");
    if (!b) return;
    const name = b.dataset.name, act = b.dataset.act;
    if (act === "player_rename") { startRename(b.closest(".preg"), name); return; }
    if (act === "player_walkon") { openWalkon(name); return; }
    const q = t(act === "player_delete" ? "q_delete" : "q_reset", { name });
    confirmDialog(q, () => playerAction(act, name));
  });
  $("savedchips").addEventListener("click", (e) => {
    const c = e.target.closest(".chip");
    if (c) addSaved(c.dataset.name);
  });
  $("names").addEventListener("input", () => renderChips());
  $("tile-play").onclick = () => { setLobbyMode("afgooien"); setView("lobby"); };
  $("tile-modes").onclick = () => setView("modes");
  $("tile-stats").onclick = openStats;
  $("modelist").addEventListener("click", (e) => {
    const b = e.target.closest("[data-mode]");
    if (b) { setLobbyMode(b.dataset.mode); setView("lobby"); }
  });
  $("setup").addEventListener("click", (e) => {
    if (genClick(e)) return;
    const st = e.target.closest("[data-step]");
    if (st) { lobbyStep(st.dataset.step, +st.dataset.d); return; }
    const sg = e.target.closest(".seg button");
    if (sg && sg.parentElement.dataset.cuseg) { cuSet.elim = +sg.dataset.v ? cuSet.block : 0; renderLobbyMode(); return; }
    if (sg) { x01Set[sg.parentElement.dataset.seg] = sg.dataset.v; renderLobbyMode(); }
  });
  $("lobbyback").onclick = () => setView("modes");
  $("confirmno").onclick = () => $("confirm").classList.add("hidden");
  // scorebord
  $("winstats").onclick = openStats;
  $("nav-players").onclick = () => leaveGame(() => setView("players"));
  $("plsearch").oninput = renderPlayers;
  $("plsort").onchange = (e) => { plSort = e.target.value; store.set("afgooien.plSort", plSort); renderPlayers(); };
  $("plitems").addEventListener("click", (e) => {
    const b = e.target.closest(".plitem");
    if (!b) return;
    plSel = b.dataset.name; store.set("afgooien.plSel", plSel); plMode = "all";
    renderPlayers();
    if (innerWidth < 980) $("plmain").scrollIntoView({ behavior: "smooth" });
  });
  $("plmain").addEventListener("click", async (e) => {
    const r = e.target.closest(".plrange button");
    if (r) {
      plRange = r.dataset.r; store.set("afgooien.plRange", plRange);
      if (plRange === "custom" && !plFrom) { plTo = isoDay(new Date()); plFrom = isoDay(new Date(Date.now() - 30 * 864e5)); }
      renderPlayerMain(); return;
    }
    if (e.target.closest("#plmail")) {
      const games = playerGames(plSel).filter((g) => inRange(g, plRange, plFrom, plTo));
      $("plmailmsg").textContent = t("pl_mail_busy");
      try {
        const res = await mailPlayer(plSel, games, periodName());
        $("plmailmsg").textContent = res.ok ? t("pl_mail_sent", { to: res.to }) : mlErr(res.error, res.detail);
      } catch (err) { $("plmailmsg").textContent = mlErr("connect"); }
    }
  });
  $("plmain").addEventListener("change", (e) => {
    if (e.target.id === "plfrom") { plFrom = e.target.value; renderPlayerMain(); }
    if (e.target.id === "plto") { plTo = e.target.value; renderPlayerMain(); }
    if (e.target.id === "plmode") { plMode = e.target.value; renderPlayerMain(); }
    if (e.target.id === "plorder") { plOrder = e.target.value; renderPlayerMain(); }
  });
  $("plmailall").onclick = async () => {
    const today = (H.games || []).filter((g) => inRange(g, "today"));
    const who = (H.players || []).filter((p) => p.email && today.some((g) => g.players.some((q) => nkey(q.name) === nkey(p.name))));
    if (!who.length) { $("plmailallmsg").textContent = t("pl_mailall_none"); return; }
    $("plmailallmsg").textContent = t("pl_mail_busy");
    let n = 0, err = null, errDetail = "";
    const per = t("pr_today").toLowerCase() + " (" + dayTxt(isoDay(new Date())) + ")";
    for (const p of who) {
      try {
        const res = await mailPlayer(p.name, playerGames(p.name).filter((g) => inRange(g, "today")), per);
        if (res.ok) n++; else err = res.error, errDetail = res.detail;
      } catch (e2) { err = "connect"; }
    }
    $("plmailallmsg").textContent = t("pl_mailall_done", { n }) + (err ? " " + mlErr(err, errDetail) : "");
  };
  $("statsbody").addEventListener("change", (e) => {
    if (e.target.id === "gorder") { gamesOrder = e.target.value; store.set("afgooien.gamesOrder", gamesOrder); renderStats(); }
  });
  // e-mailadressen bij spelers
  $("playerlist").addEventListener("change", async (e) => {
    const inp = e.target.closest(".pmail");
    if (!inp) return;
    if (await send({ type: "player_email", name: inp.dataset.name, email: inp.value })) { loadHistory(true); }
  });
  // e-mailinstellingen
  $("ml_preset").onchange = (e) => send({ type: "mail_config", preset: e.target.value });
  $("ml_save").onclick = async () => {
    const m = { type: "mail_config", preset: $("ml_preset").value, user: $("ml_user").value, sender: $("ml_user").value,
      host: $("ml_host").value, port: +$("ml_port").value || 587 };
    if ($("ml_pass").value.trim()) m.password = $("ml_pass").value;
    if (await send(m)) { $("ml_pass").value = ""; $("ml_msg").textContent = t("pl_email_saved"); }
  };
  $("ml_test").onclick = async () => {
    $("ml_msg").textContent = t("pl_mail_busy");
    try {
      const r = await (await fetch("/api/mail", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ test: true, subject: "Afgooien test", html: "<p>Het werkt! 🎯</p>", text: "Het werkt!" }) })).json();
      $("ml_msg").textContent = r.ok ? t("ml_sent", { to: r.to }) : mlErr(r.error, r.detail);
    } catch (e) { $("ml_msg").textContent = mlErr("connect"); }
  };
  $("statsclose").onclick = () => $("stats").classList.add("hidden");
  $("stats").addEventListener("click", (e) => { if (e.target.id === "stats") $("stats").classList.add("hidden"); });
  document.querySelectorAll("#stats .tab").forEach((t) => (t.onclick = () => { statsTab = t.dataset.tab; store.set("afgooien.statsTab", statsTab); renderStats(); }));
  $("statsrange").onchange = (e) => { statsRange = e.target.value; store.set("afgooien.statsRange", statsRange); renderStats(); };
  $("statsmode").onchange = (e) => { statsMode = e.target.value; store.set("afgooien.statsMode", statsMode); rankSort = { key: "wins", dir: -1 }; renderStats(); };
  $("statsbody").addEventListener("click", (e) => {
    const th = e.target.closest("th[data-sort]");
    if (!th) return;
    const key = th.dataset.sort, col = rankCols().find((c) => c.key === key);
    rankSort = rankSort.key === key ? { key, dir: -rankSort.dir } : { key, dir: col && (col.asc || col.l) ? 1 : -1 };
    renderStats();
  });
  $("statsclear").onclick = () => confirmDialog(t("q_clear"), async () => { await send({ type: "clear_history" }); loadHistory(true); });
  $("confirmyes").onclick = () => { $("confirm").classList.add("hidden"); if (confirmYes) confirmYes(); };
  $("alloclist").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-i]");
    if (!b || b.disabled) return;
    const i = +b.dataset.i;
    alloc[i] = Math.max(0, (alloc[i] || 0) + +b.dataset.d);
    renderAlloc();
  });
  $("allocok").onclick = () => send({ type: "allocate", alloc: Object.entries(alloc).map(([i, n]) => [+i, n]) });
  $("allocundo").onclick = () => send({ type: "undo" });
  $("sochoice").addEventListener("click", (e) => {
    const b = e.target.closest("[data-so]");
    if (b) send({ type: "shootout", choice: b.dataset.so });
  });
  $("soundo").onclick = () => send({ type: "undo" });
  $("finishbtn").onclick = () => confirmDialog(t("q_free_stop"), () => send({ type: "finish" }));
  // klok in de bovenbalk
  // Altijd Nederlandse tijd (zomer/winter automatisch), ook als de tijdzone van de Pi niet goed staat:
  // de klok van het apparaat zelf (UTC, via internet gelijkgezet) klopt wel.
  let clockFmt = null;
  try { clockFmt = new Intl.DateTimeFormat("nl-NL", { timeZone: "Europe/Amsterdam", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }); } catch (e) { clockFmt = null; }
  const tickClock = () => {
    const d = new Date();
    $("clock").textContent = clockFmt ? clockFmt.format(d)
      : String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
  };
  tickClock();
  setInterval(tickClock, 10000);
  // stem-paneel
  $("sound").onclick = (e) => {
    e.stopPropagation();
    $("musicpanel").classList.add("hidden");
    $("voicepanel").appendChild($("voicebox"));   // zelfde bediening als bij Instellingen
    fillVoices(); $("voicepanel").classList.toggle("hidden");
  };
  $("voicepanel").addEventListener("click", (e) => e.stopPropagation());
  bindMusic();
  bindWalkon();
  $("src").onclick = (e) => {
    e.stopPropagation();
    const src = (S && S.source) || {};
    if (!src.enabled || src.mode === "test") return;
    $("voicepanel").classList.add("hidden");
    $("musicpanel").classList.add("hidden");
    renderAdPanel();
    $("adpanel").classList.toggle("hidden");
  };
  $("adpanel").addEventListener("click", (e) => {
    e.stopPropagation();
    const b = e.target.closest("[data-bm]");
    if (!b || b.disabled) return;
    const a = b.dataset.bm;
    if (a === "reset") send({ type: "board_reset" });
    else if (a === "calibrate") confirmDialog(t("q_bm_cal"), () => send({ type: "board_cmd", action: "calibrate" }));
    else if (a === "restart") confirmDialog(t("q_bm_restart"), () => send({ type: "board_cmd", action: "restart" }));
    else send({ type: "board_cmd", action: a });
  });
  document.addEventListener("click", () => $("adpanel").classList.add("hidden"));
  document.addEventListener("click", () => $("voicepanel").classList.add("hidden"));
  $("v_on").onchange = (e) => { if (!e.target.checked) stopSpeech(); voiceSave({ on: e.target.checked }); };
  $("v_prov").onchange = (e) => { stopSpeech(); bestVoice = undefined; voiceSave({ provider: e.target.value }); };
  $("v_voice").onchange = (e) => { voiceCfg.names[LANG] = e.target.value; bestVoice = undefined; store.set("afgooien.voice", voiceCfg); fillVoices(); };
  $("v_pitch").oninput = (e) => { voiceCfg.pitch = +e.target.value; store.set("afgooien.voice", voiceCfg); $("v_pitch_val").textContent = (+voiceCfg.pitch).toFixed(2); };
  $("v_rate").oninput = (e) => { $("v_rate_val").textContent = (+e.target.value).toFixed(2); };
  $("v_rate").onchange = (e) => voiceSave({ rate: +e.target.value });
  $("v_volume").oninput = (e) => { $("v_volume_val").textContent = Math.round(+e.target.value * 100) + "%"; ttsAudio && (ttsAudio.volume = +e.target.value); };
  $("v_volume").onchange = (e) => voiceSave({ volume: +e.target.value });
  $("v_comm").onchange = (e) => voiceSave({ commentary: e.target.value });
  $("v_esave").onclick = async () => { const k = $("v_ekey").value.trim(); if (k) { await voiceSave({ eleven_key: k }); $("v_ekey").value = ""; } loadEleven(); };
  $("v_eload").onclick = async () => { const k = $("v_ekey").value.trim(); if (k) { await voiceSave({ eleven_key: k }); $("v_ekey").value = ""; } loadEleven(); };
  $("v_evoice").onchange = (e) => { const o = e.target.selectedOptions[0]; stopSpeech(); voiceSave({ eleven_voice: e.target.value, eleven_voice_name: o ? o.textContent.split(" · ")[0] : "" }); };
  $("v_emodel").onchange = (e) => voiceSave({ eleven_model: e.target.value });
  $("v_asave").onclick = async () => { await voiceSave({ azure_key: $("v_akey").value.trim(), azure_region: $("v_areg").value.trim() }); $("v_akey").value = ""; };
  $("v_anl").onchange = (e) => voiceSave({ azure_voice_nl: e.target.value });
  $("v_aen").onchange = (e) => voiceSave({ azure_voice_en: e.target.value });
  $("v_clear").onclick = () => confirmDialog(t("v_clearkeys") + "?", () => { elevenList = null; voiceSave({ clear_keys: true, provider: "auto" }); });
  const testSay = (phrases, fx) => {
    if (REMOTE && !LOCAL) { send({ type: "say", phrases }); return; }   // telefoon: laat het grote scherm praten
    sayPhrases(phrases, true);
    if (fx) runFx(fx);
  };
  $("v_test").onclick = () => testSay([t("v_demo180"), ...(COMMENT[LANG] || COMMENT.nl).c180.slice(0, 1)], [{ type: "ton", score: 180 }]);
  $("v_test2").onclick = () => testSay([t("v_demo_out", { name: "Eloy" }), (COMMENT[LANG] || COMMENT.nl).out[0]]);
  $("v_test3").onclick = () => testSay([LANG === "en" ? "Game shot, and the first leg!" : "Game shot, en de eerste leg!", (COMMENT[LANG] || COMMENT.nl).leg[0]]);
  setSoundIcon(vset().on);
  if (REMOTE) {
    document.documentElement.classList.add("remote");
    $("remotebtn").classList.remove("hidden");
  }

  // verloop in-/uitklappen
  const setLog = (collapsed) => {
    $("logwrap").classList.toggle("collapsed", collapsed);
    $("logarrow").textContent = collapsed ? "▸" : "▾";
    store.set("afgooien.logCollapsed", collapsed);
  };
  setLog(store.get("afgooien.logCollapsed", true));
  $("logtoggle").onclick = () => setLog(!$("logwrap").classList.contains("collapsed"));

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { $("stats").classList.add("hidden"); $("voicepanel").classList.add("hidden"); if (fixIndex !== null) setFix(null); }
    if (!$("stats").classList.contains("hidden")) return;
    if (!S || !["select", "play", "bulloff", "shootout"].includes(S.phase)) return;
    if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT") return;
    if (!$("confirm").classList.contains("hidden")) return;
    if (S.pending) { if (e.key === "Enter" && !$("allocok").disabled) $("allocok").click(); return; }
    if (botTurn() && e.key.toLowerCase() !== "z" && e.key !== "Backspace") return;
    const k = e.key.toLowerCase();
    if (k === "m") send({ type: "dart", number: 0, multiplier: 0 });
    else if (k === "z" || k === "backspace") { e.preventDefault(); send({ type: "undo" }); }
    else if (k === "enter" || k === " ") { e.preventDefault(); send({ type: "next" }); }
  });
}

buildBoard();
bind();
connect();
setTimeout(() => loadHistory(true), 300);
