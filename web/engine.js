"use strict";
// Spelregels van Afgooien in JavaScript: een exacte kopie van afgooien/engine.py,
// voor de losse testversie (die zonder server en zonder internet draait).
// tests/test_parity.py controleert dat beide versies precies hetzelfde rekenen.
(function (root) {
  const BOARD_RADIUS_MM = 170.0;
  const OFF_BOARD_R = round(225.5 / BOARD_RADIUS_MM, 4);
  const ELIMINATION_RULES = ["any", "scored", "reached_target"];
  const MAX_BOT_LEVEL = 6;

  // Alle teksten (NL/EN) komen uit afgooien/messages.json (zelfde bestand als de Python-versie).
  const MESSAGES = (typeof module !== "undefined" && module.exports)
    ? require("../afgooien/messages.json") : root.AFGOOIEN_MESSAGES;
  const tpl = (lang, key) => {
    const m = MESSAGES[lang] || MESSAGES.nl;
    return key in m ? m[key] : (key in MESSAGES.nl ? MESSAGES.nl[key] : key);
  };
  const labelText = (lang, code) => (code === "Miss" ? tpl(lang, "lbl_miss") : String(code));
  function param(lang, k, v) {
    if (k.endsWith("label")) return labelText(lang, v);
    if (k === "pts") return `${v} ${tpl(lang, v === 1 ? "w_point" : "w_points")}`;
    if (k === "reason") return v.t === "ton" ? tr(lang, "r_ton", { score: v.score }) : labelText(lang, v.label);
    if (k === "names") return v.length === 1 ? v[0] : v.slice(0, -1).join(", ") + tpl(lang, "j_and") + v[v.length - 1];
    if (k === "order") return v.join(", ");
    if (k === "dist") return v.mm === null ? labelText(lang, v.label) : tr(lang, "dist_mm", { label: v.label, mm: v.mm });
    if (k === "targets") return v.map((t) => tr(lang, "s_target_item", t)).join(", ");
    if (k === "game") return tpl(lang, "gn_" + v);
    if (k === "tgt") return targetText(lang, v);
    return v;
  }
  function targetText(lang, t) {
    const k = t.t;
    if (k === "dbl") return t.n === 25 ? "Bullseye" : "D" + t.n;
    if (k === "trp") return "T" + t.n;
    if (k === "num") return t.n === 25 ? "Bull" : String(t.n);
    if (k === "bull") return "Bull";
    if (k === "any_d" || k === "any_t") return tpl(lang, "tg_" + k);
    return String(t.n === undefined ? "" : t.n);
  }
  function tr(lang, key, params) {
    const out = {};
    for (const [k, v] of Object.entries(params || {})) out[k] = param(lang, k, v);
    return tpl(lang, key).replace(/\{(\w+)\}/g, (m, n) => (n in out ? String(out[n]) : m));
  }

  class GameError extends Error {
    constructor(key, params) { super(tr("nl", key, params || {})); this.key = key; this.params = params || {}; }
    text(lang) { return tr(lang, this.key, this.params); }
  }

  function toInt(v, err) {
    if (v === null || v === undefined || v === false) return 0;
    if (v === true) return 1;
    if (typeof v === "number" && Number.isFinite(v)) return Math.trunc(v);
    if (typeof v === "string" && /^\s*[+-]?\d+\s*$/.test(v)) return parseInt(v, 10);
    throw new GameError(err);
  }
  // Precies zoals Python round(x, n): exact op de binaire waarde, bij een exacte
  // helft naar het even getal.
  function round(x, n) {
    if (!Number.isFinite(x)) return x;
    const neg = x < 0, a = Math.abs(x);
    const q = a * 2 ** (n + 1);                 // exact (macht van 2)
    let r;
    if (Number.isInteger(q) && q % 2 === 1) {   // exacte helft
      const m = (q * 5 ** n - 1) / 2;
      r = (m % 2 === 0 ? m : m + 1) / 10 ** n;
    } else r = parseFloat(a.toFixed(n));        // toFixed rondt exact af
    return neg ? -r : r;
  }
  function fmt0(x) {             // zoals Python f"{x:.0f}" (bankiersafronding bij exact .5)
    const fl = Math.floor(x);
    if (x - fl === 0.5) return String(fl % 2 === 0 ? fl : fl + 1);
    return x.toFixed(0);
  }
  const has = (o, k) => o && Object.prototype.hasOwnProperty.call(o, k);
  const getd = (o, k, d) => (has(o, k) ? o[k] : d);

  class Dart {
    constructor(number = 0, multiplier = 0, x = null, y = null) {
      this.number = number; this.multiplier = multiplier; this.x = x; this.y = y;
    }
    static fromDict(d) {
      d = d || {};
      let number = toInt(d.number || 0, "err_dart");
      let mult = toInt(d.multiplier || 0, "err_dart");
      if (number === 0 || mult === 0) { number = 0; mult = 0; }
      else if (number === 25) { if (mult !== 1 && mult !== 2) throw new GameError("err_bull_mult"); }
      else if (number >= 1 && number <= 20) { if (mult < 1 || mult > 3) throw new GameError("err_mult"); }
      else throw new GameError("err_number", { number });
      let x = d.x, y = d.y;
      if (x === null || x === undefined || y === null || y === undefined) { x = null; y = null; }
      else {
        x = Number(x); y = Number(y);
        if (!(Number.isFinite(x) && Number.isFinite(y))) { x = null; y = null; }
      }
      return new Dart(number, mult, x, y);
    }
    toDict() {
      const d = { number: this.number, multiplier: this.multiplier, label: this.label };
      if (this.x !== null) { d.x = round(this.x, 5); d.y = round(this.y, 5); }
      return d;
    }
    get isMiss() { return this.number === 0 || this.multiplier === 0; }
    get label() {
      if (this.isMiss) return "Miss";
      if (this.number === 25) return this.multiplier === 2 ? "Bullseye" : "Bull";
      return "SDT"[this.multiplier - 1] + this.number;
    }
    get offBoard() {
      if (!this.isMiss) return false;
      if (this.x === null || this.y === null) return true;
      return Math.hypot(this.x, this.y) > OFF_BOARD_R;
    }
    get score() {
      if (this.isMiss) return 0;
      if (this.number === 25) return this.multiplier === 2 ? 50 : 25;
      return this.number * this.multiplier;
    }
    bullDistance() {
      if (this.x !== null && this.y !== null) return round(Math.hypot(this.x, this.y), 4);
      if (this.isMiss) return Infinity;
      if (this.number === 25) return this.multiplier === 2 ? 0.0 : 0.065;
      return { 1: 0.5, 2: 0.98, 3: 0.61 }[this.multiplier];
    }
  }

  function settingsFromDict(d) {
    d = d || {};
    const s = { target: 5, darts_per_turn: 3, elimination: "any", miss_penalty: true, bull_bonus: true, ton_bonus: true };
    s.target = toInt(getd(d, "target", s.target), "err_settings");
    s.darts_per_turn = toInt(getd(d, "darts_per_turn", s.darts_per_turn), "err_settings");
    s.elimination = String(getd(d, "elimination", s.elimination));
    for (const k of ["miss_penalty", "bull_bonus", "ton_bonus"]) s[k] = !!getd(d, k, s[k]);
    if (!(s.target >= 1 && s.target <= 15)) throw new GameError("err_target");
    if (!(s.darts_per_turn >= 1 && s.darts_per_turn <= 6)) throw new GameError("err_dpt");
    if (!ELIMINATION_RULES.includes(s.elimination)) throw new GameError("err_elim");
    return s;
  }

  function newPlayer(name, color, bot = 0) {
    return { name, color, bot, number: null, bull: [], bull_dart: null, points: 0, out: false, place: null,
             out_by: null, scored: false, reached_target: false, darts: 0, gained: 0, knocked: 0, kills: 0,
             useful: 0, outside: 0, triples: 0, doubles: 0, bulls: 0, tons: 0, n180: 0, max_turn: 0,
             score_total: 0, darts_to_target: null, turns: 0 };
  }
  const SUMMARY_KEYS = ["name", "number", "place", "kills", "knocked", "gained", "darts", "useful", "outside",
    "triples", "doubles", "bulls", "tons", "n180", "max_turn", "score_total", "darts_to_target", "out_by", "turns", "bot"];

  function cmpArr(a, b) {
    const n = Math.min(a.length, b.length);
    for (let i = 0; i < n; i++) { if (a[i] < b[i]) return -1; if (a[i] > b[i]) return 1; }
    return a.length - b.length;
  }
  const eqArr = (a, b) => a.length === b.length && a.every((v, i) => v === b[i]);

  class Game {
    constructor() { this.events = []; this.version = 0; this._reset(); }

    _reset() {
      this.phase = "setup";
      this.settings = settingsFromDict({});
      this.players = [];
      this.log = [];
      this.announce = [];
      this.fx = [];
      this.notice = null;
      this._replaying = false;
      this.sel_queue = [];
      this.sel_step = "number";
      this.tiebreak = 0;
      this.sel_darts = [];
      this.order = [];
      this.turn_pos = 0;
      this.turn_darts = [];
      this.turn_no = 0;
      this.turn_score = 0;
      this.turn_bonus = false;
      this.pending = [];
      this.queued = [];
      this.pending_seq = 0;
      this._dart_killer = false;
      this.winner = null;
      this._cur_event = 0;
      this.sel_dart_events = [];
      this.turn_dart_events = [];
    }

    // ---------------------------------------------------------- public API
    newGame(names, settings, bots) {
      bots = bots || [];
      const clean = [], levels = [];
      (names || []).forEach((raw, i) => {
        const n = String(raw).trim().slice(0, 24);
        if (!n) return;
        const lvl = i < bots.length ? toInt(bots[i] || 0, "err_botlevel") : 0;
        if (!(lvl >= 0 && lvl <= MAX_BOT_LEVEL)) throw new GameError("err_botrange", { max: MAX_BOT_LEVEL });
        clean.push(n); levels.push(lvl);
      });
      if (clean.length < 2) throw new GameError("err_min2");
      if (new Set(clean.map((n) => n.toLowerCase())).size !== clean.length) throw new GameError("err_unique");
      const s = settingsFromDict(settings);
      const data = { names: clean, settings: { ...s } };
      if (levels.some((l) => l)) data.bots = levels;
      this.events = [["start", data]];
      this._rebuild(true);
      this.version += 1;
    }
    throw_(dart) {
      if (!(dart instanceof Dart)) dart = Dart.fromDict(dart);
      return this._record(["dart", dart.toDict()]);
    }
    nextPlayer() { return this._record(["next", null]); }
    takeout() { return this._record(["takeout", null]); }
    allocate(alloc) {
      let pairs = Array.isArray(alloc) ? alloc : Object.entries(alloc || {});
      let clean;
      try {
        clean = pairs.filter(([, n]) => toInt(n, "x") > 0).map(([i, n]) => [toInt(i, "x"), toInt(n, "x")]);
      } catch (e) { throw new GameError("err_alloc"); }
      return this._record(["allocate", clean]);
    }
    correct(index, dart) {
      this.announce = []; this.fx = []; this.notice = null;
      if (!["select", "play", "finished"].includes(this.phase)) { this.notice = ["n_no_correct", {}]; return false; }
      if (!(dart instanceof Dart)) dart = Dart.fromDict(dart);
      const lst = this.phase === "select" ? this.sel_dart_events : this.turn_dart_events;
      let i;
      try { i = toInt(index, "x"); } catch (e) { i = -1; }
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
      this.events = (events || []).map((e) => [e[0], e[1]]);
      try { this._rebuild(); } catch (e) { this.events = []; this._rebuild(); }
      this.version += 1;
    }

    // ----------------------------------------------------------- internals
    _record(ev) {
      this.announce = []; this.fx = []; this.notice = null;
      if (this.phase === "setup" || this.phase === "finished") {
        this.notice = [this.phase === "setup" ? "n_start_first" : "n_finished", {}];
        return false;
      }
      this._cur_event = this.events.length;
      const applied = this._apply(ev);
      if (applied) { this.events.push(ev); this.version += 1; }
      return applied;
    }
    _rebuild(live = false) {
      const events = this.events.slice();
      this._reset();
      this._replaying = !live;
      events.forEach((ev, i) => { this._cur_event = i; this._apply(ev); });
      this._replaying = false;
      this.events = events;
    }
    // Regel in het verloop (berichtcode + parameters), optioneel ook uitgesproken.
    _say(kind, key, speak, p) {
      p = p || {};
      this.log.push({ k: key, p, kind });
      if (this.log.length > 300) this.log = this.log.slice(-300);
      if (speak && !this._replaying) this.announce.push([speak, p]);
    }
    _speak(key, p) { if (!this._replaying) this.announce.push([key, p || {}]); }
    _effect(type, data) { if (!this._replaying) this.fx.push({ type, ...data }); }
    _ignore(key, p) { this.notice = [key, p || {}]; return false; }

    _apply([kind, data]) {
      if (kind === "start") {
        this.settings = settingsFromDict(data.settings);
        const bots = data.bots || [];
        this.players = data.names.map((n, i) => newPlayer(n, i, i < bots.length ? toInt(bots[i], "x") : 0));
        this.phase = "select";
        this.sel_queue = this.players.map((_, i) => i);
        this.sel_step = "number";
        this._say("start", "l_new", null, { names: data.names.slice() });
        this._say("turn", "l_wrong_arm", "s_wrong_arm", { name: this.players[0].name });
        return true;
      }
      if (this.phase === "select") return this._applySelect(kind, data);
      if (this.phase === "play") return this._applyPlay(kind, data);
      return false;
    }

    // ----------------------------------------------------------- keuzefase
    _applySelect(kind, data) {
      const p = this.players[this.sel_queue[0]];
      if (kind === "dart") {
        const dart = Dart.fromDict(data);
        if (this.sel_step === "done") return this._ignore("n_sel_done", { name: p.name });
        this.sel_darts.push(dart);
        this.sel_dart_events.push(this._cur_event);
        if (this.sel_step === "number") {
          if (dart.isMiss || dart.number === 25) {
            this._say("warn", "l_sel_invalid", "s_rethrow", { name: p.name, label: dart.label });
            return true;
          }
          const owner = this.players.find((q) => q.number === dart.number);
          if (owner) {
            this._say("warn", "l_sel_taken", "s_taken", { name: p.name, number: dart.number, owner: owner.name });
            return true;
          }
          p.number = dart.number;
          this.sel_step = "bull";
          this._say("good", "l_sel_number", "s_number", { name: p.name, number: dart.number });
          return true;
        }
        p.bull.push(dart.bullDistance());
        p.bull_dart = dart.toDict();
        this.sel_step = "done";
        this._say("info", "l_sel_bull", null, { name: p.name, dist: Game._dist(dart) });
        return true;
      }
      if (this.sel_step !== "done") {
        if (kind === "takeout") { this.sel_darts = []; this.sel_dart_events = []; return true; }
        return this._ignore(this.sel_step === "number" ? "n_sel_wait_number" : "n_sel_wait_bull", { name: p.name });
      }
      this.sel_queue.shift();
      this.sel_darts = [];
      this.sel_dart_events = [];
      if (this.sel_queue.length) {
        const nxt = this.players[this.sel_queue[0]];
        this.sel_step = this.tiebreak ? "bull" : "number";
        if (this.tiebreak) this._say("turn", "l_tie_retry", "s_tie_retry", { name: nxt.name });
        else this._say("turn", "l_wrong_arm", "s_wrong_arm", { name: nxt.name });
        return true;
      }
      this._resolveOrder();
      return true;
    }

    _resolveOrder() {
      const key = (i) => this.players[i].bull;
      const idx = this.players.map((_, i) => i);
      let best = key(idx[0]);
      for (const i of idx) if (cmpArr(key(i), best) < 0) best = key(i);
      const top = idx.filter((i) => eqArr(key(i), best));
      if (top.length > 1) {
        this.tiebreak += 1;
        this.sel_queue = top;
        this.sel_step = "bull";
        this._say("warn", "l_tie", "s_tie", { names: top.map((i) => this.players[i].name) });
        return;
      }
      this.order = idx.slice().sort((a, b) => cmpArr(key(a), key(b)) || a - b);
      this.phase = "play";
      this.turn_pos = 0;
      this.turn_darts = [];
      this.turn_dart_events = [];
      this.turn_score = 0;
      this.turn_bonus = false;
      this.turn_no = 1;
      this.players[this.order[0]].turns += 1;
      const starter = this.players[this.order[0]].name;
      this._say("start", "l_order", null, { order: this.order.map((i) => this.players[i].name) });
      this._say("turn", "l_starts", "s_gameon", { name: starter, target: this.settings.target });
    }

    static _dist(dart) {
      if (dart.x !== null) return { label: dart.label, mm: fmt0(dart.bullDistance() * BOARD_RADIUS_MM) };
      return { label: dart.label, mm: null };
    }

    // ----------------------------------------------------------- speelfase
    get current() {
      if (this.phase === "select" && this.sel_queue.length) return this.sel_queue[0];
      if ((this.phase === "play" || this.phase === "finished") && this.order.length) return this.order[this.turn_pos];
      return null;
    }

    _applyPlay(kind, data) {
      if (kind === "allocate") {
        if (!this.pending.length) return this._ignore("n_no_pending");
        this._allocate(data);
        this._drainQueue();
        return true;
      }
      if (this.pending.length) {
        if (kind === "next") return this._ignore("n_choose_first");
        if (kind === "dart") this._say("muted", "l_queued", null, { label: Dart.fromDict(data).label });
        this.queued.push([kind, data, this._cur_event]);
        return true;
      }
      return this._playEvent(kind, data);
    }

    _playEvent(kind, data) {
      const p = this.players[this.order[this.turn_pos]];
      if (kind === "dart") {
        if (this.turn_darts.length >= this.settings.darts_per_turn) {
          return this._ignore("n_turn_full", { name: p.name, n: this.settings.darts_per_turn });
        }
        const dart = Dart.fromDict(data);
        this.turn_darts.push(dart);
        this.turn_dart_events.push(this._cur_event);
        this.turn_score += dart.score;
        p.darts += 1;
        p.score_total += dart.score;
        if (dart.number === 25) p.bulls += 1;
        else if (dart.multiplier === 3) p.triples += 1;
        else if (dart.multiplier === 2) p.doubles += 1;
        p.max_turn = Math.max(p.max_turn, this.turn_score);
        if (this.turn_score === 180 && dart.score > 0) p.n180 += 1;
        this._dart_killer = p.points >= this.settings.target;   // alleen wie vóór deze pijl al op 5 stond mag afgooien
        this._score(p, dart);
        if (!this.turn_bonus && this.turn_score >= 100) {
          this.turn_bonus = true;
          p.tons += 1;
          if (this.phase === "play" && this.settings.ton_bonus) {
            const sc = this.turn_score;
            if (sc === 180) this._speak("s_180"); else this._speak("s_score", { score: sc });
            this._effect("ton", { score: sc, player: this.order[this.turn_pos] });
            this._bonus(p, 3, { t: "ton", score: sc });
          }
        }
        return true;
      }
      if (kind === "takeout" && !this.turn_darts.length) return false;
      this._advance();
      return true;
    }

    _drainQueue() {
      while (this.queued.length && !this.pending.length && this.phase === "play") {
        const [kind, data, evI] = this.queued.shift();
        const here = this._cur_event;
        this._cur_event = evI;
        this._playEvent(kind, data);
        this._cur_event = here;
      }
      if (this.phase !== "play") this.queued = [];
    }

    _gain(p, amount, reason) {
      const t = this.settings.target;
      const gain = Math.min(amount, t - p.points);
      p.points += gain;
      p.gained += gain;
      p.scored = true;
      this._say("good", gain < amount ? "l_gain_max" : "l_gain", null, { name: p.name, reason, gain, points: p.points });
      if (p.points === t && gain > 0) {
        p.reached_target = true;
        if (p.darts_to_target === null) p.darts_to_target = p.darts;
        this._say("killer", "l_killer", "s_killer", { name: p.name, target: t });
        this._speak("s_targets", { targets: this._targets(p) });
        this._effect("killer", { player: this.players.indexOf(p) });
      }
    }

    // Een andere speler pakt punten af (pijl of bonus): wie zo op 0 komt, of al op 0 stond en geraakt wordt, is af.
    _hit(p, owner, amount, reason) {
      const loss = Math.min(amount, owner.points);
      owner.points -= loss;
      p.knocked += loss;
      this._say("hit", "l_hit", null, { name: p.name, reason, owner: owner.name, loss, points: owner.points });
      if (owner.points === 0 && this._canEliminate(owner)) this._eliminate(owner, p);
    }
    _bonusTargets() {
      const cur = this.order[this.turn_pos];
      return this.order.filter((i) => i !== cur && !this.players[i].out && this.players[i].points > 0);
    }

    _bonus(p, amount, reason) {
      if (p.points < this.settings.target) { this._gain(p, amount, reason); return; }
      if (!this._dart_killer) { this._say("muted", "l_bonus_new_killer", null, { name: p.name, reason }); return; }
      const targets = this._bonusTargets();
      if (!targets.length) { this._say("muted", "l_bonus_lost", null, { name: p.name, reason }); return; }
      if (targets.length === 1) { this._hit(p, this.players[targets[0]], amount, reason); return; }
      this.pending_seq += 1;
      this.pending.push({ points: amount, reason, id: this.pending_seq });
      this._say("killer", "l_choose", "s_choose", { name: p.name, reason, pts: amount });
    }

    _allocate(pairs) {
      const p = this.players[this.order[this.turn_pos]];
      const need = this.pending[0].points;
      const alloc = new Map();
      for (const pair of pairs || []) {
        const i = toInt(pair[0], "err_alloc"), n = toInt(pair[1], "err_alloc");
        if (n <= 0) continue;
        if (!this._bonusTargets().includes(i)) throw new GameError("err_alloc_who");
        alloc.set(i, (alloc.get(i) || 0) + n);
      }
      let sum = 0;
      for (const v of alloc.values()) sum += v;
      if (sum !== need) throw new GameError("err_alloc_exact", { pts: need });
      const item = this.pending.shift();
      for (const [i, n] of alloc) {
        if (this.phase !== "play") break;
        this._hit(p, this.players[i], n, item.reason);
      }
      if (this.phase !== "play") this.pending = [];
    }

    _score(p, dart) {
      const t = this.settings.target;
      if (dart.isMiss) {
        if (!dart.offBoard) { this._say("muted", "l_miss_onboard", null, { name: p.name }); return; }
        p.outside += 1;
        if (this.settings.miss_penalty && p.points > 0) {
          p.points -= 1;
          this._say("hit", "l_miss_penalty", null, { name: p.name, points: p.points });
        } else this._say("muted", "l_miss_off", null, { name: p.name });
        return;
      }
      if (dart.number === 25) {
        if (this.settings.bull_bonus) {
          p.useful += 1;
          this._speak("s_label", { label: dart.label });
          this._effect("bull", { label: dart.label, player: this.players.indexOf(p) });
          this._bonus(p, dart.multiplier === 2 ? 3 : 1, { t: "label", label: dart.label });
        }
        else this._say("muted", "l_nocount", null, { name: p.name, label: dart.label });
        return;
      }
      const m = dart.multiplier;
      if (dart.number === p.number) {
        if (p.points >= t) { this._say("muted", "l_own_full", null, { name: p.name, label: dart.label, target: t }); return; }
        p.useful += 1;
        this._gain(p, m, { t: "label", label: dart.label });
        return;
      }
      const owner = this.players.find((q) => q.number === dart.number);
      if (!owner) { this._say("muted", "l_nobody", null, { name: p.name, label: dart.label }); return; }
      if (owner.out) { this._say("muted", "l_owner_out", null, { name: p.name, label: dart.label, owner: owner.name }); return; }
      if (p.points < t) {
        this._say("muted", "l_not_killer", null, { name: p.name, label: dart.label, owner: owner.name, target: t });
        return;
      }
      p.useful += 1;
      this._hit(p, owner, m, { t: "label", label: dart.label });
    }

    _canEliminate(q) {
      const rule = this.settings.elimination;
      if (rule === "scored") return q.scored;
      if (rule === "reached_target") return q.reached_target;
      return true;
    }

    _eliminate(victim, by) {
      const active = this.players.filter((q) => !q.out);
      victim.out = true;
      victim.place = active.length;
      victim.out_by = by.name;
      by.kills += 1;
      this._say("out", "l_out", "s_out", { name: victim.name, by: by.name });
      this._effect("out", { player: this.players.indexOf(victim), by: this.players.indexOf(by) });
      const left = this.players.map((q, i) => (q.out ? -1 : i)).filter((i) => i >= 0);
      if (left.length === 1) {
        this.winner = left[0];
        const w = this.players[left[0]];
        w.place = 1;
        this.phase = "finished";
        this.pending = []; this.queued = [];
        this._say("win", "l_win", "s_win", { name: w.name });
        this._effect("win", { player: left[0] });
      }
    }

    _advance() {
      const n = this.order.length;
      let pos = this.turn_pos;
      for (let k = 0; k < n; k++) {
        pos = (pos + 1) % n;
        if (pos === 0) this.turn_no += 1;
        if (!this.players[this.order[pos]].out) break;
      }
      this.turn_pos = pos;
      this.turn_darts = [];
      this.turn_dart_events = [];
      this.turn_score = 0;
      this.turn_bonus = false;
      const p = this.players[this.order[pos]];
      p.turns += 1;
      const t = this.settings.target;
      if (p.points >= t) this._say("turn", "l_turn_killer", "s_turn_killer", { name: p.name, targets: this._targets(p) });
      else this._say("turn", "l_turn_pts", "s_name", { name: p.name, points: p.points, target: t });
    }

    // Tegenstanders voor de aankondiging: naam, nummer, punten.
    _targets(p) {
      const me = this.players.indexOf(p);
      return this.order.filter((i) => i !== me && !this.players[i].out).map((i) => {
        const q = this.players[i];
        return { name: q.name, number: q.number, pts: q.points };
      });
    }

    // -------------------------------------------------------------- export
    summary() {
      if (this.phase !== "finished" || this.winner === null) return null;
      const ranked = this.players.slice().sort((a, b) => (a.place || 99) - (b.place || 99));
      return {
        winner: this.players[this.winner].name,
        rounds: this.turn_no,
        settings: { ...this.settings },
        players: ranked.map((q) => Object.fromEntries(SUMMARY_KEYS.map((k) => [k, q[k]]))),
      };
    }

    state(lang) {
      lang = lang && MESSAGES[lang] ? lang : "nl";
      const cur = this.current;
      const t = this.settings.target;
      const players = this.players.map((p, i) => ({
        ...p, bull: p.bull.map((b) => (b === Infinity ? null : b)),
        bull_dart: p.bull_dart ? { ...p.bull_dart } : null,
        killer: p.points >= t && !p.out, index: i,
      }));
      const darts = (this.phase === "select" ? this.sel_darts : this.turn_darts).map((d) => {
        const o = d.toDict(); o.label = labelText(lang, d.label); return o;
      });
      let instruction = null;
      if (cur !== null && this.phase === "select") {
        const key = { number: "i_sel_number", bull: "i_sel_bull", done: "i_takeout" }[this.sel_step];
        instruction = tr(lang, key, { name: this.players[cur].name });
      } else if (cur !== null && this.phase === "play") {
        const p = this.players[cur];
        if (this.pending.length) instruction = tr(lang, "i_choose", { name: p.name, pts: this.pending[0].points });
        else if (this.turn_darts.length >= this.settings.darts_per_turn) instruction = tr(lang, "i_takeout", { name: p.name });
        else if (p.points >= t) instruction = tr(lang, "i_killer", { name: p.name });
        else instruction = tr(lang, "i_build", { name: p.name, number: p.number, points: p.points, target: t });
      } else if (this.phase === "finished" && this.winner !== null) {
        instruction = tr(lang, "i_win", { name: this.players[this.winner].name });
      }
      let pending = null;
      if (this.pending.length && this.phase === "play") {
        pending = { ...this.pending[0], reason: param(lang, "reason", this.pending[0].reason), player: cur, more: this.pending.length - 1,
                    targets: this._bonusTargets() };
      }
      return {
        version: this.version,
        phase: this.phase,
        settings: { ...this.settings },
        players,
        current: cur,
        sel_step: this.phase === "select" ? this.sel_step : null,
        tiebreak: this.tiebreak,
        order: this.order.slice(),
        turn_no: this.turn_no,
        darts,
        turn_score: this.phase === "play" ? this.turn_score : 0,
        pending,
        queued: this.queued.length,
        instruction,
        winner: this.winner,
        log: this.log.slice(-60).map((e) => ({ text: tr(lang, e.k, e.p), kind: e.kind })),
        announce: this.announce.map(([k, p]) => tr(lang, k, p)),
        fx: this.fx.map((f) => ({ ...f })),
        notice: this.notice ? tr(lang, this.notice[0], this.notice[1]) : null,
        lang,
        mode: "afgooien",
        can_undo: this.events.length > 1,
      };
    }
  }

  const api = { Game, Dart, GameError, settingsFromDict, tr, labelText, targetText, fmt0, MESSAGES };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.AfgooienEngine = api;
})(typeof window !== "undefined" ? window : globalThis);
