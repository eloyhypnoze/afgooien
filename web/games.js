"use strict";
// X01 en Count Up in JavaScript: een exacte kopie van afgooien/games.py (voor de testversie).
// tests/test_parity.py controleert dat beide versies precies hetzelfde rekenen.
(function (root) {
  const E = (typeof module !== "undefined" && module.exports) ? require("./engine.js") : root.AfgooienEngine;
  const { Dart, GameError, tr, labelText, fmt0 } = E;
  const MAX_BOT_LEVEL = 6;
  const DARTS = 3;
  const X01_SCORES = [101, 170, 201, 301, 401, 501, 601, 701, 801, 901, 1001];
  const MAX_PLAYERS = 8;

  // ---------------------------------------------------------------- uitgooien
  const ALL = [];
  for (let n = 20; n >= 1; n--) ALL.push(["T" + n, 3 * n, "T"]);
  for (let n = 20; n >= 1; n--) ALL.push(["D" + n, 2 * n, "D"]);
  for (let n = 20; n >= 1; n--) ALL.push(["S" + n, n, "S"]);
  ALL.push(["Bull", 25, "B"], ["Bullseye", 50, "E"]);
  const DBL_RANK = [20, 16, 8, 10, 12, 18, 4, 6, 14, 2, 19, 17, 15, 13, 11, 9, 7, 5, 3, 1];

  function finishOk(kind, out) {
    if (out === "double") return kind === "D" || kind === "E";
    if (out === "master") return kind === "D" || kind === "T" || kind === "E";
    return true;
  }
  function lastCost(code, kind) {
    if (kind === "E") return 150;
    if (kind === "D") return DBL_RANK.indexOf(+code.slice(1)) * 10;
    if (kind === "T") return 200 + (20 - +code.slice(1)) * 5;
    if (kind === "B") return 160;
    return 100 + (20 - +code.slice(1)) * 2;
  }
  function setupCost(code, kind) {
    if (kind === "T") { const n = +code.slice(1); return { 20: 0, 19: 10, 18: 20, 17: 30 }[n] ?? 50 + (20 - n); }
    if (kind === "S") return 20 + (20 - +code.slice(1));
    if (kind === "B" || kind === "E") return 60;
    return 80 + (20 - +code.slice(1));
  }
  function* routes(rem, n, out) {
    if (n === 1) { for (const d of ALL) if (d[1] === rem && finishOk(d[2], out)) yield [d]; return; }
    for (const d of ALL) {
      const left = rem - d[1];
      if (left < 1 || (out !== "straight" && left < 2)) continue;
      for (const rest of routes(left, n - 1, out)) yield [d, ...rest];
    }
  }
  const CO_CACHE = new Map();
  function checkout(rem, darts, out) {
    if (rem < 1 || rem > 180 || darts < 1) return null;
    const key = rem + "|" + darts + "|" + out;
    if (!CO_CACHE.has(key)) CO_CACHE.set(key, checkoutCalc(rem, darts, out));
    const r = CO_CACHE.get(key);
    return r ? r.slice() : null;
  }
  function checkoutCalc(rem, darts, out) {
    let best = null, bestCost = null;
    for (let n = 1; n <= darts; n++) {
      for (const r of routes(rem, n, out)) {
        let cost = lastCost(r[r.length - 1][0], r[r.length - 1][2]);
        for (const d of r.slice(0, -1)) cost += setupCost(d[0], d[2]);
        if (bestCost === null || cost < bestCost) { best = r; bestCost = cost; }
      }
      if (best) return best.map((d) => d[0]);
    }
    return null;
  }
  const oneDartFinish = (rem, out) => ALL.some((d) => d[1] === rem && finishOk(d[2], out));

  // ------------------------------------------------------------------ basis
  // zoals Python int(): getallen afkappen, tekst alleen als heel getal, None = fout
  function pyInt(v, err) {
    if (v === true) return 1;
    if (v === false) return 0;
    if (typeof v === "number" && Number.isFinite(v)) return Math.trunc(v);
    if (typeof v === "string" && /^\s*[+-]?\d+\s*$/.test(v)) return parseInt(v, 10);
    throw new GameError(err);
  }
  const has = (o, k) => o && Object.prototype.hasOwnProperty.call(o, k);
  const intOf = (d, k, def) => pyInt(has(d, k) ? d[k] : def, "err_settings");
  const pyStr = (v) => (v === null || v === undefined ? "None" : v === true ? "True" : v === false ? "False" : String(v));

  function cleanNames(names, bots, minimum) {
    bots = bots || [];
    const clean = [], levels = [];
    (names || []).forEach((raw, i) => {
      const n = String(raw).trim().slice(0, 24);
      if (!n) return;
      let lvl = 0;
      if (i < bots.length) { const b = bots[i]; lvl = b ? pyInt(b, "err_botlevel") : 0; }
      if (!(lvl >= 0 && lvl <= MAX_BOT_LEVEL)) throw new GameError("err_botrange", { max: MAX_BOT_LEVEL });
      clean.push(n); levels.push(lvl);
    });
    if (clean.length < minimum) throw new GameError(minimum === 1 ? "err_min1" : "err_min2");
    if (clean.length > MAX_PLAYERS) throw new GameError("err_max8");
    if (new Set(clean.map((n) => n.toLowerCase())).size !== clean.length) throw new GameError("err_unique");
    return [clean, levels];
  }

  class BaseGame {
    constructor() { this.events = []; this.version = 0; this._reset(); }
    get MIN_PLAYERS() { return 1; }
    _reset() {
      this.phase = "setup";
      this.settings = this.defaultSettings();
      this.players = [];
      this.log = [];
      this.announce = [];
      this.fx = [];
      this.notice = null;
      this._replaying = false;
      this.order = [];
      this.turn_pos = 0;
      this.turn_darts = [];
      this.turn_dart_events = [];
      this.turn_score = 0;
      this.turn_no = 0;
      this.winner = null;
      this._cur_event = 0;
      this.resetMode();
    }
    defaultSettings() { return {}; }
    cleanSettings() { return { ...this.defaultSettings() }; }
    resetMode() {}

    newGame(names, settings, bots) {
      const [clean, levels] = cleanNames(names, bots, this.MIN_PLAYERS);
      const data = { names: clean, settings: this.cleanSettings(settings) };
      if (levels.some((l) => l)) data.bots = levels;
      this.events = [["start", data]];
      this._rebuild(true);
      this.version += 1;
    }
    throw_(dart) { if (!(dart instanceof Dart)) dart = Dart.fromDict(dart); return this._record(["dart", dart.toDict()]); }
    nextPlayer() { return this._record(["next", null]); }
    takeout() { return this._record(["takeout", null]); }
    allocate() { this.announce = []; this.fx = []; this.notice = ["n_no_pending", {}]; return false; }
    choose(choice) {
      if (!["setup", "finished", "shootout"].includes(this.phase)) {
        this.announce = []; this.fx = [];
        return this._ignore("n_no_choice");
      }
      return this._record(["choose", pyStr(choice)]);
    }
    correct(index, dart) {
      this.announce = []; this.fx = []; this.notice = null;
      if (this.phase === "setup") { this.notice = ["n_no_correct", {}]; return false; }
      if (!(dart instanceof Dart)) dart = Dart.fromDict(dart);
      const lst = this.turn_dart_events;
      let i;
      try { i = pyInt(index, "x"); } catch (e) { i = -1; }
      if (!(i >= 0 && i < lst.length)) { this.notice = ["n_no_dart", {}]; return false; }
      const evI = lst[i];
      const old = this.events[evI];
      this.events[evI] = ["dart", dart.toDict()];
      try { this._rebuild(); } catch (e) {
        this.events[evI] = old;
        this._rebuild();
        throw new GameError("err_correct_conflict");
      }
      this.notice = ["n_corrected", { i: i + 1, label: dart.label }];
      this.version += 1;
      return true;
    }
    undo() {
      this.announce = []; this.fx = []; this.notice = null;
      if (this.events.length <= 1) { this.notice = ["n_nothing_undo", {}]; return false; }
      this.events.pop();
      this._rebuild();
      this.notice = ["n_undone", {}];
      this.version += 1;
      return true;
    }
    reset() { this.events = []; this._rebuild(); this.version += 1; }
    loadEvents(events) {
      this.events = events.map((e) => [e[0], e[1]]);
      try { this._rebuild(); } catch (e) { this.events = []; this._rebuild(); }
      this.version += 1;
    }
    get current() {
      if ((this.phase === "bulloff" || this.phase === "play") && this.order.length) return this.order[this.turn_pos];
      return null;
    }
    _record(ev) {
      this.announce = []; this.fx = []; this.notice = null;
      if (this.phase === "setup" || this.phase === "finished") {
        this.notice = [this.phase === "setup" ? "n_start_first" : "n_finished", {}];
        return false;
      }
      this._cur_event = this.events.length;
      const ok = this._apply(ev);
      if (ok) { this.events.push(ev); this.version += 1; }
      return ok;
    }
    _rebuild(live = false) {
      const events = this.events.slice();
      this._reset();
      this._replaying = !live;
      events.forEach((ev, i) => { this._cur_event = i; this._apply(ev); });
      this._replaying = false;
      this.events = events;
    }
    _say(kind, key, speak, p) {
      p = p || {};
      this.log.push({ k: key, p, kind });
      if (this.log.length > 300) this.log = this.log.slice(-300);
      if (speak && !this._replaying) this.announce.push([speak, p]);
    }
    _speak(key, p) { if (!this._replaying) this.announce.push([key, p || {}]); }
    _effect(type, data) { if (!this._replaying) this.fx.push({ type, ...data }); }
    _ignore(key, p) { this.notice = [key, p || {}]; return false; }
    _newPlayer(name, i, bot) {
      return { name, index: i, color: i, bot, place: null, darts: 0, points: 0, n180: 0, n140: 0, n100: 0, hi_turn: 0 };
    }
    _apply([kind, data]) {
      if (kind === "start") {
        this.settings = this.cleanSettings(data.settings);
        const bots = data.bots || [];
        this.players = data.names.map((n, i) => this._newPlayer(n, i, i < bots.length ? pyInt(bots[i], "x") : 0));
        this.start();
        return true;
      }
      return this.play(kind, data);
    }
    _turnStats(p, pts) {
      if (pts === 180) p.n180 += 1;
      else if (pts >= 140) p.n140 += 1;
      else if (pts >= 100) p.n100 += 1;
      p.hi_turn = Math.max(p.hi_turn, pts);
    }
    _callScore(pts) {
      if (pts === 180) { this._speak("s_180"); this._effect("ton", { score: 180, player: this.current, pts: 0 }); }
      else if (pts === 0) this._speak("g_s_noscore");
      else {
        this._speak("s_score", { score: pts });
        if (pts >= 100) this._effect("ton", { score: pts, player: this.current, pts: 0 });
      }
    }
    _baseState(lang) {
      lang = lang === "en" || lang === "nl" ? lang : "nl";
      return {
        mode: this.MODE,
        version: this.version,
        phase: this.phase,
        settings: { ...this.settings },
        players: this.players.map((p) => JSON.parse(JSON.stringify(p))),
        current: this.current,
        order: this.order.slice(),
        turn_no: this.turn_no,
        darts: this.turn_darts.map((d) => { const o = d.toDict(); o.label = labelText(lang, d.label); return o; }),
        turn_score: this.phase === "play" ? this.turn_score : 0,
        pending: null,
        queued: 0,
        sel_step: null,
        winner: this.winner,
        log: this.log.slice(-60).map((e) => ({ text: tr(lang, e.k, e.p), kind: e.kind })),
        announce: this.announce.map(([k, p]) => tr(lang, k, p)),
        fx: this.fx.map((f) => ({ ...f })),
        notice: this.notice ? tr(lang, this.notice[0], this.notice[1]) : null,
        can_undo: this.events.length > 1,
        lang,
      };
    }
  }

  function dist(d) {
    if (d.x !== null) return { label: d.label, mm: fmt0(d.bullDistance() * 170.0) };
    return { label: d.label, mm: null };
  }

  // =================================================================== X01
  class X01Game extends BaseGame {
    get MODE() { return "x01"; }
    defaultSettings() {
      return { start: 501, match: "legs", legs: 1, sets: 1, in_mode: "straight", out_mode: "double", bulloff: "off", shootout: "off" };
    }
    cleanSettings(d) {
      d = d || {};
      const s = this.defaultSettings();
      s.start = intOf(d, "start", s.start);
      s.legs = intOf(d, "legs", s.legs);
      s.sets = intOf(d, "sets", s.sets);
      for (const [k, opts] of [["match", ["off", "legs", "sets"]], ["in_mode", ["straight", "double", "master"]],
        ["out_mode", ["straight", "double", "master"]], ["bulloff", ["off", "wdf", "pdc"]],
        ["shootout", ["off", "on"]]]) {
        s[k] = pyStr(has(d, k) ? d[k] : s[k]);
        if (!opts.includes(s[k])) throw new GameError("err_settings");
      }
      if (!X01_SCORES.includes(s.start) || !(s.legs >= 1 && s.legs <= 11) || !(s.sets >= 1 && s.sets <= 7)) throw new GameError("err_settings");
      if (s.match === "off") { s.legs = 1; s.sets = 1; } else if (s.match === "legs") s.sets = 1;
      return s;
    }
    resetMode() {
      this.leg_no = 0; this.set_no = 1; this.bust = false; this.leg_done = null;
      this.turn_start = 0; this.turn_opened = false; this.bo_queue = []; this.bo_darts = new Map(); this.tiebreak = 0;
      this.turn_on_finish = false;
      this.so_choice = null; this.so_chooser = null; this.so_rest = []; this.so_queue = []; this.so_vals = new Map();
      this.so_next_place = 0; this.so_round = 0;
    }
    _newPlayer(name, i, bot) {
      return Object.assign(super._newPlayer(name, i, bot), {
        score: 0, legs: 0, sets: 0, legs_total: 0, opened: false, darts_leg: 0, f9_points: 0, f9_darts: 0,
        hi_checkout: 0, best_leg: null, co_att: 0, co_hit: 0, busts: 0, avg_points: 0, avg_darts: 0,
      });
    }
    start() {
      const s = this.settings;
      this._say("start", "xo_l_new", null, { start: s.start, names: this.players.map((p) => p.name) });
      if (s.bulloff !== "off" && this.players.length > 1) {
        this.phase = "bulloff";
        this.order = this.players.map((_, i) => i);
        this.bo_queue = this.order.slice();
        this.turn_pos = 0;
        this._say("turn", "xo_l_bulloff", "xo_s_bulloff", { name: this.players[0].name });
        return;
      }
      this.order = this.players.map((_, i) => i);
      this._startLeg();
    }
    _legOrderStart() { return this.leg_no % this.order.length; }
    _startLeg() {
      this.phase = "play";
      for (const p of this.players) { p.score = this.settings.start; p.opened = this.settings.in_mode === "straight"; p.darts_leg = 0; }
      this.turn_pos = this._legOrderStart();
      this.turn_no = 1;
      this.leg_done = null;
      this._beginTurn(true);
    }
    _beginTurn(first = false) {
      const p = this.players[this.order[this.turn_pos]];
      this.turn_darts = []; this.turn_dart_events = [];
      this.turn_score = 0;
      this.bust = false;
      this.turn_start = p.score;
      this.turn_opened = p.opened;
      this.turn_on_finish = !!(p.opened && checkout(p.score, DARTS, this.settings.out_mode));
      if (first) {
        if (this.settings.match === "sets") this._say("start", "xo_l_leg_set", null, { set: this.set_no, leg: this._legInSet(), name: p.name });
        else this._say("start", "xo_l_leg", null, { leg: this.leg_no + 1, name: p.name });
        this._say("turn", "xo_l_turn", this.leg_no === 0 ? "xo_s_gameon" : "xo_s_leg_start", { name: p.name, score: p.score });
        return;
      }
      const route = p.opened ? checkout(p.score, DARTS, this.settings.out_mode) : null;
      this._say("turn", "xo_l_turn", route ? "xo_s_require" : "s_name", { name: p.name, score: p.score });
    }
    _legInSet() { return this.players.reduce((a, p) => a + p.legs, 0) + 1; }
    get current() {
      if (this.phase === "shootout") return this.so_queue.length ? this.so_queue[0] : this.so_chooser;
      return super.current;
    }
    play(kind, data) {
      if (this.phase === "bulloff") return this._playBulloff(kind, data);
      if (this.phase === "shootout") return this._playShootout(kind, data);
      if (kind === "choose") return this._ignore("n_no_choice");
      const p = this.players[this.order[this.turn_pos]];
      const waiting = this.leg_done !== null || this.bust || this.turn_darts.length >= DARTS;
      if (kind === "dart") {
        if (waiting) return this._ignore("n_turn_full", { name: p.name, n: DARTS });
        this._dart(p, Dart.fromDict(data));
        return true;
      }
      if (kind === "next" || kind === "takeout") {
        if (kind === "takeout" && !this.turn_darts.length && this.leg_done === null) return true;
        this._endTurn(p);
        return true;
      }
      return false;
    }
    _inOk(d) {
      const m = this.settings.in_mode;
      if (m === "double") return d.multiplier === 2;
      if (m === "master") return d.multiplier === 2 || d.multiplier === 3;
      return !d.isMiss;
    }
    _dart(p, d) {
      this.turn_darts.push(d);
      this.turn_dart_events.push(this._cur_event);
      p.darts += 1;
      p.darts_leg += 1;
      const out = this.settings.out_mode;
      if (p.opened && oneDartFinish(p.score, out)) p.co_att += 1;
      let sc = d.score;
      let logged = false;
      if (!p.opened) {
        logged = true;
        if (this._inOk(d)) { p.opened = true; this._say("good", "xo_l_opened", null, { name: p.name, label: d.label, score: p.score - sc }); }
        else { this._say("muted", "xo_l_notopen", null, { name: p.name, label: d.label }); sc = 0; }
      }
      const nw = p.score - sc;
      const kind = d.multiplier === 2 && d.number !== 25 ? "D" : d.number === 25 && d.multiplier === 2 ? "E"
        : d.multiplier === 3 ? "T" : d.number === 25 ? "B" : "S";
      const bust = nw < 0 || (nw === 1 && out !== "straight") || (nw === 0 && !finishOk(kind, out));
      if (bust) {
        this.bust = true;
        p.score = this.turn_start;
        p.opened = this.turn_opened;
        p.busts += 1;
        this._say("hit", "xo_l_bust", "xo_s_bust", { name: p.name, label: d.label, score: p.score });
        this._effect("bust", { player: this.order[this.turn_pos] });
        this._turnPoints(p, 0);
        this.turn_score = 0;
        return;
      }
      p.score = nw;
      this.turn_score += sc;
      if (nw === 0) { this._legWon(p, d); return; }
      if (!logged) this._say("info", "xo_l_dart", null, { name: p.name, label: d.label, score: nw });
      if (this.turn_darts.length >= DARTS) { this._turnPoints(p, this.turn_score); this._callScore(this.turn_score); }
    }
    _turnPoints(p, pts) {
      p.points += pts;
      if (!this.turn_on_finish) { p.avg_points += pts; p.avg_darts += this.turn_darts.length; }
      const before = p.darts_leg - this.turn_darts.length;
      if (before < 9) { p.f9_points += pts; p.f9_darts += Math.min(this.turn_darts.length, 9 - before); }
      this._turnStats(p, pts);
    }
    _legWon(p, d) {
      const idx = this.order[this.turn_pos];
      const co = this.turn_score;
      this._turnPoints(p, co);
      p.co_hit += 1;
      p.hi_checkout = Math.max(p.hi_checkout, co);
      if (p.best_leg === null || p.darts_leg < p.best_leg) p.best_leg = p.darts_leg;
      p.legs += 1;
      p.legs_total += 1;
      const s = this.settings;
      let setWon = false;
      if (s.match === "sets" && p.legs >= s.legs) { p.sets += 1; setWon = true; }
      const matchWon = s.match === "sets" ? p.sets >= s.sets : p.legs >= s.legs;
      this._say("win", "xo_l_checkout", null, { name: p.name, label: d.label, score: co, darts: p.darts_leg });
      if (matchWon) {
        this.winner = idx;
        if (s.shootout === "on" && this.players.length >= 3) {
          p.place = 1;
          this._say("win", "xo_l_match", "s_win", { name: p.name });
          this._effect("win", { player: idx });
          this._startShootout();
          return;
        }
        this.phase = "finished";
        this._place();
        this._say("win", "xo_l_match", "s_win", { name: p.name });
        this._effect("win", { player: idx });
        return;
      }
      this.leg_done = idx;
      if (setWon) this._say("win", "xo_l_set", "xo_s_set", { name: p.name, set: this.set_no });
      else this._speak("xo_s_leg", { name: p.name });
      this._effect("leg", { player: idx, score: co });
    }
    _endTurn(p) {
      if (this.leg_done !== null) {
        if (this.settings.match === "sets" && this.players[this.leg_done].legs >= this.settings.legs) {
          for (const q of this.players) q.legs = 0;
          this.set_no += 1;
        }
        this.leg_no += 1;
        this._startLeg();
        return;
      }
      if (!this.bust && this.turn_darts.length < DARTS) {
        const missing = DARTS - this.turn_darts.length;
        p.darts += missing;
        p.darts_leg += missing;
        this._turnPointsPartial(p);
      }
      const n = this.order.length;
      this.turn_pos = (this.turn_pos + 1) % n;
      if (this.turn_pos === this._legOrderStart()) this.turn_no += 1;
      this._beginTurn();
    }
    _turnPointsPartial(p) {
      const pts = this.turn_score;
      p.points += pts;
      if (!this.turn_on_finish) { p.avg_points += pts; p.avg_darts += DARTS; }
      const before = p.darts_leg - DARTS;
      if (before < 9) { p.f9_points += pts; p.f9_darts += Math.min(DARTS, 9 - before); }
      this._turnStats(p, pts);
      this._callScore(pts);
    }
    _place() {
      const w = this.winner, P = this.players;
      const rest = P.map((_, i) => i).filter((i) => i !== w).sort((a, b) =>
        (P[b].sets - P[a].sets) || (P[b].legs_total - P[a].legs_total) || (P[a].score - P[b].score) || (a - b));
      P[w].place = 1;
      rest.forEach((i, k) => { P[i].place = k + 2; });
    }
    _playBulloff(kind, data) {
      const cur = this.order[this.turn_pos];
      const p = this.players[cur];
      if (kind === "choose") return this._ignore("n_no_choice");
      if (kind === "dart") {
        if (this.bo_darts.has(cur)) return this._ignore("n_sel_done", { name: p.name });
        const d = Dart.fromDict(data);
        this.turn_darts = [d];
        this.turn_dart_events = [this._cur_event];
        const pdc = this.settings.bulloff === "pdc";
        const val = pdc ? (d.number === 25 && d.multiplier === 2 ? 0 : d.number === 25 ? 1 : 9) : d.bullDistance();
        this.bo_darts.set(cur, val);
        if (pdc) this._say("info", "xo_l_bo_pdc", null, { name: p.name, label: d.label });
        else this._say("info", "l_sel_bull", null, { name: p.name, dist: dist(d) });
        return true;
      }
      if (kind === "next" || kind === "takeout") {
        if (!this.bo_darts.has(cur)) {
          if (kind === "takeout") { this.turn_darts = []; this.turn_dart_events = []; return true; }
          return this._ignore("n_sel_wait_bull", { name: p.name });
        }
        this.bo_queue.shift();
        this.turn_darts = []; this.turn_dart_events = [];
        if (this.bo_queue.length) {
          this.turn_pos = this.order.indexOf(this.bo_queue[0]);
          this._say("turn", "xo_l_bulloff", "xo_s_bulloff", { name: this.players[this.bo_queue[0]].name });
          return true;
        }
        this._resolveBulloff();
        return true;
      }
      return false;
    }
    _resolveBulloff() {
      const keys = [...this.bo_darts.keys()].sort((a, b) => a - b);
      const best = Math.min(...keys.map((k) => this.bo_darts.get(k)));
      const top = keys.filter((k) => this.bo_darts.get(k) === best);
      if (top.length > 1 || best === 9) {
        this.tiebreak += 1;
        this.bo_darts = new Map();
        this.bo_queue = best !== 9 ? top : keys;
        this.turn_pos = this.order.indexOf(this.bo_queue[0]);
        this._say("warn", "l_tie", "s_tie", { names: this.bo_queue.map((i) => this.players[i].name) });
        return;
      }
      const w = top[0], n = this.players.length;
      this.order = Array.from({ length: n }, (_, k) => (w + k) % n);
      this._say("start", "l_order", null, { order: this.order.map((i) => this.players[i].name) });
      this._startLeg();
    }
    // ------------------------------------------------------- shoot-out
    _startShootout() {
      const P = this.players;
      const rest = P.map((_, i) => i).filter((i) => i !== this.winner).sort((a, b) =>
        (P[b].sets - P[a].sets) || (P[b].legs_total - P[a].legs_total) || (P[a].score - P[b].score) || (a - b));
      this.phase = "shootout";
      this.so_rest = rest;
      this.so_chooser = rest[0];
      this.so_choice = null;
      this.so_queue = [];
      this.so_vals = new Map();
      this.so_next_place = P.length;
      this.so_round = 0;
      this.turn_darts = []; this.turn_dart_events = [];
      this.turn_score = 0;
      this.bust = false;
      this.leg_done = null;
      this._say("turn", "xo_l_so_start", "xo_s_so_choose", { name: P[rest[0]].name });
    }
    _soNeed() { return this.so_choice === "bull" ? 1 : DARTS; }
    _soNewRound(who) {
      this.so_round += 1;
      let order = this.order.filter((i) => who.includes(i));
      const k = order.indexOf(this.so_chooser);
      if (k >= 0) order = order.slice(k).concat(order.slice(0, k));
      this.so_queue = order;
      this.so_vals = new Map();
      this.turn_darts = []; this.turn_dart_events = [];
      this.turn_score = 0;
      this._say("turn", "xo_l_so_turn", "s_name", { name: this.players[order[0]].name });
    }
    _playShootout(kind, data) {
      const P = this.players;
      if (kind === "choose") {
        if (this.so_choice !== null || (data !== "bull" && data !== "score")) return this._ignore("n_no_choice");
        this.so_choice = data;
        this._say("start", data === "bull" ? "xo_l_so_bull" : "xo_l_so_score_pick", null, { name: P[this.so_chooser].name });
        this._soNewRound(this.so_rest);
        return true;
      }
      if (this.so_choice === null) {
        if (kind === "takeout") return false;
        return this._ignore("n_so_choose", { name: P[this.so_chooser].name });
      }
      const cur = this.so_queue[0];
      const p = P[cur];
      const bull = this.so_choice === "bull";
      if (kind === "dart") {
        if (this.turn_darts.length >= this._soNeed()) return this._ignore("n_turn_full", { name: p.name, n: this._soNeed() });
        const d = Dart.fromDict(data);
        this.turn_darts.push(d);
        this.turn_dart_events.push(this._cur_event);
        if (bull) {
          this.so_vals.set(cur, d.bullDistance());
          this._say("info", "l_sel_bull", null, { name: p.name, dist: dist(d) });
        } else {
          this.turn_score += d.score;
          this.so_vals.set(cur, -this.turn_score);
          this._say("info", "xo_l_so_dart", null, { name: p.name, label: d.label, score: this.turn_score });
        }
        return true;
      }
      if (kind === "next" || kind === "takeout") {
        if (!this.turn_darts.length) {
          if (kind === "takeout") return false;
          return this._ignore(bull ? "n_sel_wait_bull" : "n_so_wait", { name: p.name });
        }
        if (!bull) {
          this._say("info", "xo_l_so_score", null, { name: p.name, score: this.turn_score });
          this._callScore(this.turn_score);
        }
        this.so_queue.shift();
        this.turn_darts = []; this.turn_dart_events = [];
        this.turn_score = 0;
        if (this.so_queue.length) {
          this._say("turn", "xo_l_so_turn", "s_name", { name: P[this.so_queue[0]].name });
          return true;
        }
        this._soResolve();
        return true;
      }
      return false;
    }
    _soResolve() {
      const P = this.players;
      const keys = [...this.so_vals.keys()];
      const worst = Math.max(...keys.map((k) => this.so_vals.get(k)));
      const losers = keys.filter((k) => this.so_vals.get(k) === worst).sort((a, b) => a - b);
      if (losers.length > 1) {
        this.tiebreak += 1;
        this._say("warn", "xo_l_so_tie", "xo_s_so_tie", { names: losers.map((i) => P[i].name) });
        this._soNewRound(losers);
        return;
      }
      const out = losers[0];
      const place = this.so_next_place;
      this.so_next_place -= 1;
      P[out].place = place;
      this.so_rest = this.so_rest.filter((i) => i !== out);
      this._say("hit", "xo_l_so_out", "xo_s_so_out", { name: P[out].name, place });
      this._effect("out", { player: out });
      if (this.so_rest.length === 1) {
        const last = this.so_rest[0];
        P[last].place = this.so_next_place;
        this.so_queue = [];
        this.phase = "finished";
        this._say("win", "xo_l_so_done", null, { name: P[last].name, place: this.so_next_place });
        return;
      }
      this._soNewRound(this.so_rest);
    }
    _soState() {
      if (this.so_chooser === null) return null;
      const bull = this.so_choice === "bull";
      const vals = [...this.so_vals.keys()].sort((a, b) => a - b).map((i) => {
        const v = this.so_vals.get(i);
        return { i, v: bull ? (v === Infinity ? null : Math.floor(v * 170.0 + 0.5)) : (v === 0 ? 0 : -v) };
      });
      return { choice: this.so_choice, chooser: this.so_chooser, rest: this.so_rest.slice(),
        queue: this.so_queue.slice(), vals, round: this.so_round };
    }
    summary() {
      if (this.phase !== "finished" || this.winner === null) return null;
      const ranked = this.players.slice().sort((a, b) => (a.place || 99) - (b.place || 99));
      const keys = ["name", "place", "bot", "darts", "points", "f9_points", "f9_darts", "n180", "n140", "n100", "hi_turn",
        "hi_checkout", "best_leg", "legs_total", "sets", "co_att", "co_hit", "busts", "avg_points", "avg_darts"];
      return { mode: "x01", winner: this.players[this.winner].name, rounds: this.leg_no + 1, settings: { ...this.settings },
        players: ranked.map((q) => Object.fromEntries(keys.map((k) => [k, q[k]]))) };
    }
    state(lang) {
      const st = this._baseState(lang);
      lang = st.lang;
      const cur = this.current;
      st.tiebreak = this.tiebreak;
      st.leg_no = this.leg_no;
      st.set_no = this.set_no;
      st.bust = this.bust;
      st.leg_done = this.leg_done;
      st.waiting = (this.phase === "bulloff" && this.bo_darts.has(cur)) || (this.phase === "play" &&
        (this.leg_done !== null || this.bust || this.turn_darts.length >= DARTS)) ||
        (this.phase === "shootout" && this.so_queue.length > 0 && this.turn_darts.length >= this._soNeed());
      st.shootout = this._soState();
      let route = null, instr = null;
      if (this.phase === "bulloff" && cur !== null) {
        instr = tr(lang, this.bo_darts.has(cur) ? "i_takeout" : "xo_i_bulloff", { name: this.players[cur].name });
      } else if (this.phase === "play" && cur !== null) {
        const p = this.players[cur];
        if (this.leg_done !== null) instr = tr(lang, "xo_i_legwon", { name: this.players[this.leg_done].name });
        else if (st.waiting) instr = tr(lang, "i_takeout", { name: p.name });
        else if (!p.opened) instr = tr(lang, "xo_i_open_" + this.settings.in_mode, { name: p.name });
        else {
          route = checkout(p.score, DARTS - this.turn_darts.length, this.settings.out_mode);
          instr = tr(lang, "xo_i_throw", { name: p.name, score: p.score });
        }
      } else if (this.phase === "shootout" && cur !== null) {
        const p = this.players[cur];
        if (this.so_choice === null) instr = tr(lang, "xo_i_so_choose", { name: p.name });
        else if (st.waiting) instr = tr(lang, "i_takeout", { name: p.name });
        else instr = tr(lang, "xo_i_so_" + this.so_choice, { name: p.name, score: this.turn_score });
      } else if (this.phase === "finished" && this.winner !== null) {
        instr = tr(lang, "i_win", { name: this.players[this.winner].name });
      }
      st.instruction = instr;
      st.checkout = route ? route.map((c) => labelText(lang, c)) : null;
      return st;
    }
  }

  // ================================================================ Count Up
  class CountUpGame extends BaseGame {
    get MODE() { return "countup"; }
    defaultSettings() { return { rounds: 8, elim: 0 }; }
    cleanSettings(d) {
      const s = { rounds: intOf(d || {}, "rounds", 8), elim: intOf(d || {}, "elim", 0) };
      if (!(s.rounds >= 1 && s.rounds <= 30) || !(s.elim >= 0 && s.elim <= 30)) throw new GameError("err_settings");
      return s;
    }
    _newPlayer(name, i, bot) { return Object.assign(super._newPlayer(name, i, bot), { score: 0, rounds: [], best_round: 0, out: false }); }
    _elim() { return this.settings.elim > 0 && this.players.length > 1; }
    start() {
      this.order = this.players.map((_, i) => i);
      this.phase = "play";
      this.turn_no = 1;
      this.turn_pos = 0;
      if (this._elim()) this._say("start", "cu_l_new_elim", null, { every: this.settings.elim, names: this.players.map((p) => p.name) });
      else this._say("start", "cu_l_new", null, { rounds: this.settings.rounds, names: this.players.map((p) => p.name) });
      this._beginTurn();
    }
    _left() { const e = this.settings.elim; return e - ((this.turn_no - 1) % e); }
    _beginTurn() {
      const p = this.players[this.order[this.turn_pos]];
      this.turn_darts = []; this.turn_dart_events = [];
      this.turn_score = 0;
      if (this._elim()) this._say("turn", "cu_l_turn_elim", "s_name", { name: p.name, round: this.turn_no, left: this._left() });
      else this._say("turn", "cu_l_turn", "s_name", { name: p.name, round: this.turn_no, rounds: this.settings.rounds });
    }
    play(kind, data) {
      const p = this.players[this.order[this.turn_pos]];
      if (kind === "dart") {
        if (this.turn_darts.length >= DARTS) return this._ignore("n_turn_full", { name: p.name, n: DARTS });
        const d = Dart.fromDict(data);
        this.turn_darts.push(d);
        this.turn_dart_events.push(this._cur_event);
        p.darts += 1;
        this.turn_score += d.score;
        p.score += d.score;
        this._say("info", "cu_l_dart", null, { name: p.name, label: d.label, score: p.score });
        if (this.turn_darts.length >= DARTS) this._callScore(this.turn_score);
        return true;
      }
      if (kind === "next" || kind === "takeout") {
        if (kind === "takeout" && !this.turn_darts.length) return true;
        const missing = DARTS - this.turn_darts.length;
        p.darts += missing;
        if (missing) this._callScore(this.turn_score);
        p.points += this.turn_score;
        p.rounds = p.rounds.concat([this.turn_score]);
        p.best_round = Math.max(p.best_round, this.turn_score);
        this._turnStats(p, this.turn_score);
        this.turn_pos += 1;
        if (this.turn_pos >= this.order.length) {
          this.turn_pos = 0;
          if (this._elim()) {
            if (this.turn_no % this.settings.elim === 0 && this._cut()) return true;
          } else if (this.turn_no >= this.settings.rounds) { this._finish(); return true; }
          this.turn_no += 1;
        }
        this._beginTurn();
        return true;
      }
      return false;
    }
    _cut() {
      const active = this.order.map((i) => this.players[i]);
      const low = Math.min(...active.map((p) => p.score));
      const bottom = active.filter((p) => p.score === low);
      if (bottom.length > 1) {
        this._say("warn", "cu_l_cut_tie", null, { names: bottom.map((p) => p.name), score: low });
        return false;
      }
      const q = bottom[0];
      q.out = true;
      q.place = active.length;
      this.order = this.order.filter((i) => i !== q.index);
      this._say("hit", "cu_l_out", "cu_s_out", { name: q.name, score: q.score, place: q.place });
      this._effect("out", { player: q.index });
      if (this.order.length === 1) {
        const w = this.players[this.order[0]];
        w.place = 1;
        this.winner = w.index;
        this.phase = "finished";
        this.turn_darts = []; this.turn_dart_events = [];
        this._say("win", "cu_l_win", "cu_s_win", { name: w.name, score: w.score });
        this._effect("win", { player: this.winner });
        return true;
      }
      return false;
    }
    _finish() {
      this.phase = "finished";
      this.turn_darts = []; this.turn_dart_events = [];
      const P = this.players;
      const topScore = Math.max(...P.map((p) => p.score));
      for (const p of P) p.place = 1 + P.filter((q) => q.score > p.score).length;
      const top = P.filter((p) => p.score === topScore);
      this.winner = top[0].index;
      const names = top.map((p) => p.name);
      if (top.length > 1) this._say("win", "cu_l_tie", "cu_s_tie", { names, score: topScore });
      else this._say("win", "cu_l_win", "cu_s_win", { name: names[0], score: topScore });
      this._effect("win", { player: this.winner });
    }
    summary() {
      if (this.phase !== "finished" || this.winner === null) return null;
      const ranked = this.players.slice().sort((a, b) => a.place - b.place || a.index - b.index);
      const keys = ["name", "place", "bot", "darts", "points", "score", "best_round", "n180", "n140", "n100", "hi_turn"];
      return { mode: "countup", winner: ranked.filter((q) => q.place === 1).map((q) => q.name).join(" & "),
        rounds: this._elim() ? this.turn_no : this.settings.rounds, settings: { ...this.settings },
        players: ranked.map((q) => Object.fromEntries(keys.map((k) => [k, q[k]]))) };
    }
    state(lang) {
      const st = this._baseState(lang);
      lang = st.lang;
      const cur = this.current;
      st.waiting = this.phase === "play" && this.turn_darts.length >= DARTS;
      st.rounds = this._elim() ? null : this.settings.rounds;
      st.elim_left = this._elim() && this.phase === "play" ? this._left() : null;
      let instr = null;
      if (this.phase === "play" && cur !== null) {
        const p = this.players[cur];
        instr = st.waiting ? tr(lang, "i_takeout", { name: p.name })
          : this._elim() ? tr(lang, "cu_i_throw_elim", { name: p.name, round: this.turn_no, left: this._left() })
          : tr(lang, "cu_i_throw", { name: p.name, round: this.turn_no, rounds: this.settings.rounds });
      } else if (this.phase === "finished" && this.winner !== null) {
        const top = this.players.filter((p) => p.place === 1).map((p) => p.name);
        instr = top.length === 1 ? tr(lang, "i_win", { name: top[0] }) : tr(lang, "cu_i_tie", { names: top });
      }
      st.instruction = instr;
      st.checkout = null;
      return st;
    }
  }

  const GAMES = { x01: X01Game, countup: CountUpGame };
  function makeGame(mode) {
    if (!mode || mode === "afgooien") return new E.Game();
    const P = (typeof module !== "undefined" && module.exports) ? require("./party.js") : root.AfgooienParty;
    const cls = GAMES[mode] || (P && P.PARTY_GAMES[mode]);
    if (!cls) throw new GameError("err_mode");
    return new cls();
  }

  const api = { X01Game, CountUpGame, makeGame, checkout, X01_SCORES, BaseGame, DARTS, pyInt, intOf, has, pyStr };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.AfgooienGames = api;
})(typeof window !== "undefined" ? window : globalThis);
