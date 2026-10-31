"use strict";
// Training- en party-spellen: een exacte kopie van afgooien/party.py (voor de testversie).
// tests/test_parity.py controleert dat beide versies precies hetzelfde rekenen.
(function (root) {
  const node = typeof module !== "undefined" && module.exports;
  const E = node ? require("./engine.js") : root.AfgooienEngine;
  const G = node ? require("./games.js") : root.AfgooienGames;
  const { Dart, GameError, tr, labelText, targetText } = E;
  const { BaseGame, DARTS, intOf, has, pyStr, checkout } = G;

  // ------------------------------------------------------------------ hulp
  class Rng {             // mulberry32
    constructor(seed) { this.a = seed | 0; }
    random() {
      this.a = (this.a + 0x6D2B79F5) | 0;
      const a = this.a;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    }
    below(n) { return Math.floor(this.random() * n); }
    shuffle(lst) {
      lst = lst.slice();
      for (let i = lst.length - 1; i > 0; i--) { const j = this.below(i + 1); [lst[i], lst[j]] = [lst[j], lst[i]]; }
      return lst;
    }
  }
  function en(d, k, def, opts) {
    const v = pyStr(has(d, k) ? d[k] : def);
    if (!opts.includes(v)) throw new GameError("err_settings");
    return v;
  }
  const bool = (d, k, def) => !!(has(d, k) ? d[k] : def);
  function rng(d, k, def, lo, hi) {
    const v = intOf(d, k, def);
    if (!(v >= lo && v <= hi)) throw new GameError("err_settings");
    return v;
  }
  const seedOf = (d) => (has(d, "seed") ? intOf(d, "seed", 1) & 0x7FFFFFFF : Math.floor(Math.random() * 2147483646) + 1);
  function cmpArr(a, b) {
    for (let i = 0; i < Math.max(a.length, b.length); i++) {
      if (a[i] < b[i]) return -1;
      if (a[i] > b[i]) return 1;
    }
    return 0;
  }
  function hits(d, t) {
    if (!t || d.isMiss) return false;
    const k = t.t;
    if (k === "num") return d.number === t.n;
    if (k === "dbl") return d.number === t.n && d.multiplier === 2;
    if (k === "trp") return d.number === t.n && d.multiplier === 3;
    if (k === "any_d") return d.multiplier === 2;
    if (k === "any_t") return d.multiplier === 3;
    if (k === "bull") return d.number === 25;
    return false;
  }

  // ================================================================ basis
  class TurnGame extends BaseGame {
    get COUNT_MISSING() { return true; }
    get SCORE_CALL() { return false; }
    resetMode() { this.turn_over = false; this.turn_hits = 0; this.turn_start = 0; this.seq = []; }
    _newPlayer(name, i, bot) {
      return Object.assign(super._newPlayer(name, i, bot), { score: 0, hits: 0, out: false, done: false, won: false }, this.playerExtra());
    }
    playerExtra() { return {}; }
    setup() {}
    roundsTotal() { return null; }
    target() { return null; }
    turnBegin() {}
    onDart() {}
    onTurnEnd() {}
    roundBegin() {}
    rankKey(p) { return [p.won ? 0 : 1, -p.score]; }
    instr(p) {
      const t = this.target(p);
      return t ? ["g_i_aim", { name: p.name, tgt: t }] : ["g_i_throw", { name: p.name }];
    }
    info() { return []; }
    roundLabel() {
      const r = this.roundsTotal();
      return r ? ["g_rp_round", { n: this.turn_no, r }] : ["g_rp_round0", { n: this.turn_no }];
    }
    view(p) { return { big: p.score, meta: [], badge: null }; }
    highlight() {
      const cur = this.current;
      const t = cur !== null && this.phase === "play" ? this.target(this.players[cur]) : null;
      if (!t) return { nums: [], bull: false };
      if (t.t === "num" || t.t === "dbl" || t.t === "trp") return { nums: t.n === 25 ? [] : [t.n], bull: t.n === 25 };
      return { nums: [], bull: t.t === "bull" };
    }
    table() { return null; }
    checkoutRoute() { return null; }
    summaryExtra() { return []; }

    start() {
      this.order = this.players.map((_, i) => i);
      this.phase = "play";
      this.turn_no = 1;
      this.turn_pos = 0;
      this._say("start", "g_l_new", null, { game: this.MODE, names: this.players.map((p) => p.name) });
      this.setup();
      this._beginTurn();
    }
    _cur() { return this.players[this.order[this.turn_pos]]; }
    _beginTurn() {
      const p = this._cur();
      this.turn_darts = []; this.turn_dart_events = [];
      this.turn_score = 0;
      this.turn_over = false;
      this.turn_hits = 0;
      this.turn_start = p.score;
      this.turnBegin(p);
      const t = this.target(p);
      if (t) this._say("turn", "g_l_turn", "s_name", { name: p.name, tgt: t });
      else this._say("turn", "g_l_turn0", "s_name", { name: p.name });
    }
    play(kind, data) {
      const p = this._cur();
      if (kind === "dart") {
        if (this.turn_over || this.turn_darts.length >= DARTS) return this._ignore("n_turn_full", { name: p.name, n: DARTS });
        const d = Dart.fromDict(data);
        this.turn_darts.push(d);
        this.turn_dart_events.push(this._cur_event);
        p.darts += 1;
        this.onDart(p, d);
        if (this.phase === "play" && !this.turn_over && this.turn_darts.length >= DARTS && this.SCORE_CALL) this._callScore(this.turn_score);
        return true;
      }
      if (kind === "next" || kind === "takeout") {
        if (kind === "takeout" && !this.turn_darts.length) return true;
        if (!this.turn_over && this.COUNT_MISSING) p.darts += DARTS - this.turn_darts.length;
        this.onTurnEnd(p);
        if (this.phase === "finished") return true;
        this._advance();
        return true;
      }
      return false;
    }
    _active(i) { const q = this.players[i]; return !q.out && !q.done; }
    _advance() {
      const n = this.order.length;
      let pos = this.turn_pos;
      for (;;) {
        pos += 1;
        if (pos >= n) {
          pos = 0;
          if (this._endOfRound()) return;
        }
        if (this._active(this.order[pos])) break;
      }
      this.turn_pos = pos;
      this._beginTurn();
    }
    _endOfRound() {
      if (!this.order.some((i) => this._active(i))) { this._finish(); return true; }
      const r = this.roundsTotal();
      if (r !== null && this.turn_no >= r) { this._finish(); return true; }
      this.turn_no += 1;
      this.roundBegin();
      return false;
    }
    _finish() {
      this.phase = "finished";
      const keys = this.players.map((p) => this.rankKey(p));
      this.players.forEach((p, i) => { p.place = 1 + keys.filter((k) => cmpArr(k, keys[i]) < 0).length; });
      const tops = this.players.filter((p) => p.place === 1);
      this.winner = tops[0].index;
      if (tops.length > 1) this._say("win", "cu_l_tie", "cu_s_tie", { names: tops.map((p) => p.name), score: tops[0].score });
      else this._say("win", "g_l_win", "g_s_win", { name: tops[0].name, game: this.MODE });
      this._effect("win", { player: this.winner });
    }
    _logDart(p, d) { this._say("muted", "g_l_dart", null, { name: p.name, label: d.label }); }

    summary() {
      if (this.phase !== "finished" || this.winner === null) return null;
      const ranked = this.players.slice().sort((a, b) => a.place - b.place || a.index - b.index);
      const keys = ["name", "place", "bot", "darts", "hits", "score", ...this.summaryExtra()];
      return { mode: this.MODE, winner: ranked.filter((q) => q.place === 1).map((q) => q.name).join(" & "),
        rounds: this.turn_no, settings: { ...this.settings },
        players: ranked.map((q) => Object.fromEntries(keys.map((k) => [k, q[k]]))) };
    }
    state(lang) {
      const st = this._baseState(lang);
      lang = st.lang;
      const cur = this.current;
      const playing = this.phase === "play" && cur !== null;
      st.waiting = playing && (this.turn_over || this.turn_darts.length >= DARTS);
      st.rounds = this.roundsTotal();
      st.target = playing ? this.target(this.players[cur]) : null;
      let instr = null, route = null;
      if (playing) {
        const p = this.players[cur];
        if (st.waiting) instr = tr(lang, "i_takeout", { name: p.name });
        else {
          const [k, prm] = this.instr(p);
          instr = tr(lang, k, prm);
          route = this.checkoutRoute(p);
        }
      } else if (this.phase === "finished" && this.winner !== null) {
        const top = this.players.filter((p) => p.place === 1).map((p) => p.name);
        instr = top.length === 1 ? tr(lang, "i_win", { name: top[0] }) : tr(lang, "cu_i_tie", { names: top });
      }
      st.instruction = instr;
      st.checkout = route ? route.map((c) => labelText(lang, c)) : null;
      st.info = this.info().map(([k, prm]) => tr(lang, k, prm)).join("");
      const [rk, rp] = this.roundLabel();
      st.round_label = this.phase === "play" ? tr(lang, rk, rp) : tr(lang, "g_rp_over");
      st.views = this.players.map((p) => {
        const v = this.view(p);
        return { big: v.big, meta: v.meta.map(([k, prm]) => tr(lang, k, prm)), badge: v.badge ? tr(lang, v.badge) : null,
          dim: p.out || (p.done && this.phase === "play") };
      });
      st.highlight = playing ? this.highlight() : { nums: [], bull: false };
      st.table = this.table();
      return st;
    }
  }

  // ============================================================ Rond de klok
  class AroundClock extends TurnGame {
    get MODE() { return "atc"; }
    defaultSettings() { return { zone: "any", bull: true, jump: false }; }
    cleanSettings(d) {
      d = d || {};
      return { zone: en(d, "zone", "any", ["any", "double", "triple"]), bull: bool(d, "bull", true), jump: bool(d, "jump", false) };
    }
    playerExtra() { return { pos: 1, finish: null }; }
    _last() { return this.settings.bull ? 21 : 20; }
    target(p) {
      if (p.done) return null;
      if (p.pos === 21) return { t: "bull", n: 25 };
      return { t: { any: "num", double: "dbl", triple: "trp" }[this.settings.zone], n: p.pos };
    }
    onDart(p, d) {
      const t = this.target(p);
      if (!hits(d, t)) { this._logDart(p, d); return; }
      const step = this.settings.jump && t.t === "num" ? d.multiplier : 1;
      p.hits += 1;
      p.pos = Math.min(this._last() + 1, p.pos + step);
      p.score = p.pos - 1;
      if (p.pos > this._last()) {
        p.done = true; p.won = true; p.finish = p.darts;
        this.turn_over = true;
        this._say("win", "atc_l_done", null, { name: p.name, darts: p.darts });
        this._finish();
        return;
      }
      this._say("good", "g_l_hit_next", null, { name: p.name, label: d.label, tgt: this.target(p) });
    }
    rankKey(p) { return [p.done ? 0 : 1, -p.pos, p.darts]; }
    info() {
      const out = [["atc_info_" + this.settings.zone, {}]];
      if (this.settings.bull) out.push(["atc_info_bull", {}]);
      if (this.settings.jump && this.settings.zone === "any") out.push(["atc_info_jump", {}]);
      return out;
    }
    view(p) {
      return { big: p.done ? "✓" : targetText("nl", this.target(p)),
        meta: [["v_progress", { n: p.pos - 1, total: this._last() }], ["v_darts", { n: p.darts }]], badge: null };
    }
    summaryExtra() { return ["finish"]; }
  }

  // ================================================================ Shanghai
  class Shanghai extends TurnGame {
    get MODE() { return "shanghai"; }
    get SCORE_CALL() { return true; }
    defaultSettings() { return { rounds: 7, instant: true }; }
    cleanSettings(d) {
      d = d || {};
      const r = intOf(d, "rounds", 7);
      if (![7, 10, 20].includes(r)) throw new GameError("err_settings");
      return { rounds: r, instant: bool(d, "instant", true) };
    }
    playerExtra() { return { shanghai: false }; }
    roundsTotal() { return this.settings.rounds; }
    target() { return { t: "num", n: this.turn_no }; }
    onDart(p, d) {
      const n = this.turn_no;
      if (d.isMiss || d.number !== n) { this._logDart(p, d); return; }
      const pts = n * d.multiplier;
      p.score += pts; p.hits += 1; this.turn_score += pts;
      this._say("good", "g_l_score", null, { name: p.name, label: d.label, score: p.score });
      const mults = new Set(this.turn_darts.filter((x) => x.number === n && !x.isMiss).map((x) => x.multiplier));
      if (this.settings.instant && mults.has(1) && mults.has(2) && mults.has(3)) {
        p.shanghai = true; p.won = true;
        this.turn_over = true;
        this._say("win", "sh_l_shanghai", "sh_s_shanghai", { name: p.name });
        this._finish();
      }
    }
    rankKey(p) { return [p.won ? 0 : 1, -p.score]; }
    info() { return [["sh_info", {}], [this.settings.instant ? "sh_info_instant" : "sh_info_noinstant", {}]]; }
    view(p) { return { big: p.score, meta: [["v_hits", { n: p.hits }]], badge: null }; }
    summaryExtra() { return ["shanghai"]; }
  }

  // ================================================================ Bob's 27
  class Bobs27 extends TurnGame {
    get MODE() { return "bobs27"; }
    defaultSettings() { return { bull: true, negative: false }; }
    cleanSettings(d) { d = d || {}; return { bull: bool(d, "bull", true), negative: bool(d, "negative", false) }; }
    playerExtra() { return { out_round: null }; }
    setup() { for (const p of this.players) p.score = 27; }
    roundsTotal() { return this.settings.bull ? 21 : 20; }
    _n() { return this.turn_no === 21 ? 25 : this.turn_no; }
    target() { return { t: "dbl", n: this._n() }; }
    _value() { return this._n() === 25 ? 50 : 2 * this._n(); }
    onDart(p, d) {
      if (!hits(d, this.target(p))) { this._logDart(p, d); return; }
      p.score += this._value(); p.hits += 1; this.turn_hits += 1;
      this._say("good", "g_l_score", null, { name: p.name, label: d.label, score: p.score });
    }
    onTurnEnd(p) {
      if (this.turn_hits) return;
      p.score -= this._value();
      this._say("hit", "b27_l_minus", null, { name: p.name, v: this._value(), score: p.score });
      if (p.score < 0 && !this.settings.negative) {
        p.out = true; p.out_round = this.turn_no;
        this._say("out", "b27_l_out", "s_out", { name: p.name, by: "" });
      }
    }
    rankKey(p) { return p.out ? [1, -p.out_round, -p.score] : [0, -p.score, 0]; }
    info() { return [["b27_info", {}], [this.settings.negative ? "b27_info_neg" : "b27_info_out", {}]]; }
    view(p) { return { big: p.score, meta: [["v_hits", { n: p.hits }]], badge: p.out ? "badge_out" : null }; }
    summaryExtra() { return ["out_round"]; }
  }

  // ================================================================ Halve-It
  const HALVE_SEQ = [{ t: "num", n: 15 }, { t: "num", n: 16 }, { t: "any_d" }, { t: "num", n: 17 },
    { t: "num", n: 18 }, { t: "any_t" }, { t: "num", n: 19 }, { t: "num", n: 20 }, { t: "bull", n: 25 }];
  class HalveIt extends TurnGame {
    get MODE() { return "halveit"; }
    get SCORE_CALL() { return true; }
    defaultSettings() { return { start: 0 }; }
    cleanSettings(d) {
      const s = intOf(d || {}, "start", 0);
      if (s !== 0 && s !== 40) throw new GameError("err_settings");
      return { start: s };
    }
    setup() { for (const p of this.players) p.score = this.settings.start; }
    roundsTotal() { return HALVE_SEQ.length; }
    target() { return { ...HALVE_SEQ[this.turn_no - 1] }; }
    onDart(p, d) {
      if (!hits(d, this.target(p))) { this._logDart(p, d); return; }
      p.score += d.score; p.hits += 1; this.turn_hits += 1; this.turn_score += d.score;
      this._say("good", "g_l_score", null, { name: p.name, label: d.label, score: p.score });
    }
    onTurnEnd(p) {
      if (this.turn_hits) return;
      p.score = Math.floor(p.score / 2);
      this._say("hit", "hi_l_halved", "hi_s_halved", { name: p.name, score: p.score });
      this._effect("halve", { player: this.order[this.turn_pos] });
    }
    info() { return [["hi_info", {}]]; }
    view(p) { return { big: p.score, meta: [["v_hits", { n: p.hits }]], badge: null }; }
  }

  // ================================================================= Cricket
  const CRICKET = [20, 19, 18, 17, 16, 15, 25];
  class Cricket extends TurnGame {
    get MODE() { return "cricket"; }
    defaultSettings() { return { scoring: "standard", rounds: 20 }; }
    cleanSettings(d) {
      d = d || {};
      const r = intOf(d, "rounds", 20);
      if (![0, 10, 15, 20, 25].includes(r)) throw new GameError("err_settings");
      return { scoring: en(d, "scoring", "standard", ["standard", "cutthroat", "noscore"]), rounds: r };
    }
    playerExtra() { return { marks: CRICKET.map(() => 0), mtotal: 0 }; }
    roundsTotal() { return this.settings.rounds || null; }
    onDart(p, d) {
      if (d.isMiss || !CRICKET.includes(d.number)) { this._logDart(p, d); return; }
      const k = CRICKET.indexOf(d.number);
      let added = 0, scored = 0;
      const sc = this.settings.scoring;
      for (let i = 0; i < d.multiplier; i++) {
        if (p.marks[k] < 3) { p.marks[k] += 1; added += 1; }
        else if (sc !== "noscore") {
          const others = this.players.filter((q) => q !== p && q.marks[k] < 3);
          if (others.length) {
            const v = d.number;
            scored += v;
            if (sc === "standard") p.score += v;
            else for (const q of others) q.score += v;
          }
        }
      }
      p.mtotal += added;
      if (!added && !scored) { this._logDart(p, d); return; }
      p.hits += 1;
      this._say("good", "cr_l_dart", null, { name: p.name, label: d.label, m: added, sc: scored });
      if (p.marks.every((m) => m >= 3)) {
        const others = this.players.filter((q) => q !== p);
        const win = sc === "noscore" || !others.length ||
          (sc === "standard" && p.score >= Math.max(...others.map((q) => q.score))) ||
          (sc === "cutthroat" && p.score <= Math.min(...others.map((q) => q.score)));
        if (win) { p.won = true; this.turn_over = true; this._finish(); }
      }
    }
    rankKey(p) {
      const w = p.won ? 0 : 1, sc = this.settings.scoring;
      if (sc === "standard") return [w, -p.score, -p.mtotal];
      if (sc === "cutthroat") return [w, p.score, -p.mtotal];
      return [w, -p.mtotal, 0];
    }
    info() { return [["cr_info_" + this.settings.scoring, {}]]; }
    view(p) {
      return { big: this.settings.scoring === "noscore" ? p.mtotal : p.score, meta: [["cr_v_marks", { n: p.mtotal }]], badge: null };
    }
    highlight() {
      const cur = this.current;
      if (cur === null || this.phase !== "play") return { nums: [], bull: false };
      const m = this.players[cur].marks;
      return { nums: CRICKET.filter((n, k) => n !== 25 && m[k] < 3), bull: m[m.length - 1] < 3 };
    }
    table() {
      return { cols: ["20", "19", "18", "17", "16", "15", "Bull"], rows: this.players.map((p) => p.marks.slice()),
        closed: CRICKET.map((_, k) => this.players.every((p) => p.marks[k] >= 3)) };
    }
    summaryExtra() { return ["mtotal"]; }
  }

  // ================================================================== Bullen
  class Bulls extends TurnGame {
    get MODE() { return "bulls"; }
    get SCORE_CALL() { return true; }
    defaultSettings() { return { rounds: 10 }; }
    cleanSettings(d) { return { rounds: rng(d || {}, "rounds", 10, 1, 30) }; }
    roundsTotal() { return this.settings.rounds; }
    target() { return { t: "bull", n: 25 }; }
    onDart(p, d) {
      if (d.number !== 25 || d.isMiss) { this._logDart(p, d); return; }
      p.score += d.score; p.hits += 1; this.turn_score += d.score;
      this._say("good", "g_l_score", null, { name: p.name, label: d.label, score: p.score });
    }
    info() { return [["bu_info", {}]]; }
    view(p) { return { big: p.score, meta: [["v_hits", { n: p.hits }], ["v_darts", { n: p.darts }]], badge: null }; }
  }

  // ========================================================= Doubles oefenen
  class Doubles extends TurnGame {
    get MODE() { return "doubles"; }
    defaultSettings() { return { order: "ordered", count: 21, seed: 1 }; }
    cleanSettings(d) {
      d = d || {};
      return { order: en(d, "order", "ordered", ["ordered", "random"]), count: rng(d, "count", 21, 1, 21), seed: seedOf(d) };
    }
    setup() {
      let base = [];
      for (let n = 1; n <= 20; n++) base.push(n);
      base.push(25);
      if (this.settings.order === "random") base = new Rng(this.settings.seed).shuffle(base);
      this.seq = base.slice(0, this.settings.count);
    }
    roundsTotal() { return this.settings.count; }
    target() { return { t: "dbl", n: this.seq[this.turn_no - 1] }; }
    onDart(p, d) {
      if (!hits(d, this.target(p))) { this._logDart(p, d); return; }
      p.score += 1; p.hits += 1;
      this._say("good", "dbl_l_hit", null, { name: p.name, label: d.label, score: p.score });
    }
    rankKey(p) { return [-p.score, 0]; }
    info() { return [["dbl_info", {}]]; }
    view(p) { return { big: p.score, meta: [["v_darts", { n: p.darts }]], badge: null }; }
  }

  // ========================================================= Random checkout
  const CO_RANGES = { easy: [2, 40], mid: [41, 100], hard: [101, 170], all: [2, 170] };
  class RandomCheckout extends TurnGame {
    get MODE() { return "checkout"; }
    defaultSettings() { return { range: "all", rounds: 10, seed: 1 }; }
    cleanSettings(d) {
      d = d || {};
      return { range: en(d, "range", "all", Object.keys(CO_RANGES)), rounds: rng(d, "rounds", 10, 1, 30), seed: seedOf(d) };
    }
    playerExtra() { return { rem: 0 }; }
    setup() {
      const [lo, hi] = CO_RANGES[this.settings.range];
      const valid = [];
      for (let n = lo; n <= hi; n++) if (checkout(n, DARTS, "double")) valid.push(n);
      const r = new Rng(this.settings.seed);
      this.seq = [];
      for (let i = 0; i < this.settings.rounds; i++) this.seq.push(valid[r.below(valid.length)]);
    }
    roundsTotal() { return this.settings.rounds; }
    turnBegin(p) { p.rem = this.seq[this.turn_no - 1]; }
    target() { return { t: "fin", n: this.seq[this.turn_no - 1] }; }
    onDart(p, d) {
      const rem = p.rem - d.score;
      if (rem < 0 || rem === 1 || (rem === 0 && d.multiplier !== 2)) {
        this.turn_over = true;
        p.rem = this.seq[this.turn_no - 1];
        this._say("hit", "co_l_bust", "xo_s_bust", { name: p.name, label: d.label });
        return;
      }
      p.rem = rem;
      if (rem === 0) {
        p.score += 1; p.hits += 1;
        this.turn_over = true;
        this._say("win", "co_l_done", "co_s_done", { name: p.name, label: d.label, n: this.seq[this.turn_no - 1] });
        this._effect("leg", { player: this.order[this.turn_pos], score: this.seq[this.turn_no - 1] });
        return;
      }
      this._say("info", "xo_l_dart", null, { name: p.name, label: d.label, score: rem });
    }
    checkoutRoute(p) { return checkout(p.rem, DARTS - this.turn_darts.length, "double"); }
    instr(p) { return ["co_i", { name: p.name, n: p.rem }]; }
    rankKey(p) { return [-p.score, p.darts]; }
    info() { return [["co_info_" + this.settings.range, {}]]; }
    view(p) {
      return { big: p.score, meta: [["co_v_of", { n: p.score, r: this.settings.rounds }], ["v_darts", { n: p.darts }]], badge: null };
    }
  }

  // ================================================================== Killer
  class Killer extends TurnGame {
    get MODE() { return "killer"; }
    get MIN_PLAYERS() { return 2; }
    defaultSettings() { return { lives: 3, self: true, seed: 1 }; }
    cleanSettings(d) { d = d || {}; return { lives: rng(d, "lives", 3, 1, 9), self: bool(d, "self", true), seed: seedOf(d) }; }
    playerExtra() { return { number: 0, killer: false, kills: 0, out_order: 0 }; }
    setup() {
      const base = [];
      for (let n = 1; n <= 20; n++) base.push(n);
      const nums = new Rng(this.settings.seed).shuffle(base);
      this.players.forEach((p, i) => {
        p.number = nums[i];
        p.score = this.settings.lives;
        this._say("info", "ki_l_number", null, { name: p.name, n: p.number });
      });
    }
    target(p) { return p.killer ? null : { t: "dbl", n: p.number }; }
    instr(p) {
      if (p.killer) return ["ki_i_kill", { name: p.name }];
      return ["ki_i_become", { name: p.name, tgt: { t: "dbl", n: p.number } }];
    }
    onDart(p, d) {
      if (d.multiplier !== 2 || d.number === 25) { this._logDart(p, d); return; }
      const owner = this.players.find((q) => q.number === d.number);
      if (!owner) { this._say("muted", "l_nobody", null, { name: p.name, label: d.label }); return; }
      if (owner === p) {
        if (!p.killer) {
          p.killer = true; p.hits += 1;
          this._say("killer", "ki_l_killer", "ki_s_killer", { name: p.name });
          this._effect("killer", { player: p.index });
        } else if (this.settings.self) this._lose(p, p);
        else this._logDart(p, d);
        return;
      }
      if (!p.killer) this._say("muted", "ki_l_notkiller", null, { name: p.name, label: d.label });
      else if (owner.out) this._say("muted", "l_owner_out", null, { name: p.name, label: d.label, owner: owner.name });
      else { p.hits += 1; this._lose(owner, p); }
    }
    _lose(q, by) {
      q.score -= 1;
      this._say("hit", "ki_l_life", null, { name: by.name, owner: q.name, lives: q.score });
      if (q.score > 0) return;
      q.out = true;
      q.out_order = 1 + this.players.filter((x) => x.out_order).length;
      if (by !== q) by.kills += 1;
      this._say("out", "l_out", "s_out", { name: q.name, by: by.name });
      this._effect("out", { player: q.index });
      if (q === by) this.turn_over = true;
      const alive = this.players.filter((x) => !x.out);
      if (alive.length <= 1) {
        if (alive.length) alive[0].won = true;
        this.turn_over = true;
        this._finish();
      }
    }
    rankKey(p) { return [!p.out ? 0 : 1, -p.out_order]; }
    info() { return [["ki_info", {}], [this.settings.self ? "ki_info_self" : "ki_info_noself", {}]]; }
    roundLabel() { return ["g_rp_round0", { n: this.turn_no }]; }
    view(p) {
      return { big: p.score > 0 ? "♥".repeat(Math.max(0, p.score)) : "✕",
        meta: [["ki_v_num", { n: p.number }], ["ki_v_kills", { n: p.kills }]],
        badge: p.out ? "badge_out" : p.killer ? "badge_killer2" : null };
    }
    highlight() {
      const cur = this.current;
      if (cur === null || this.phase !== "play") return { nums: [], bull: false };
      const p = this.players[cur];
      if (!p.killer) return { nums: [p.number], bull: false };
      return { nums: this.players.filter((q) => q !== p && !q.out).map((q) => q.number), bull: false };
    }
    summaryExtra() { return ["kills", "number"]; }
  }

  // ==================================================================== Golf
  class Golf extends TurnGame {
    get MODE() { return "golf"; }
    get COUNT_MISSING() { return false; }
    defaultSettings() { return { holes: 9 }; }
    cleanSettings(d) {
      const h = intOf(d || {}, "holes", 9);
      if (h !== 9 && h !== 18) throw new GameError("err_settings");
      return { holes: h };
    }
    playerExtra() { return { last: null, holes: [] }; }
    roundsTotal() { return this.settings.holes; }
    target() { return { t: "num", n: this.turn_no }; }
    turnBegin(p) { p.last = null; }
    static strokes(d, h) {
      if (d.isMiss || d.number !== h) return 5;
      return { 2: 1, 3: 2 }[d.multiplier] || 3;
    }
    onDart(p, d) {
      const v = Golf.strokes(d, this.turn_no);
      p.last = v;
      if (v < 5) p.hits += 1;
      this._say(v < 5 ? "good" : "muted", "go_l_dart", null, { name: p.name, label: d.label, v });
    }
    onTurnEnd(p) {
      const v = p.last !== null ? p.last : 5;
      p.score += v;
      p.holes = p.holes.concat([v]);
      p.last = null;
      this._say("info", "go_l_hole", null, { name: p.name, h: this.turn_no, v, score: p.score });
    }
    rankKey(p) { return [p.score, 0]; }
    instr(p) { return ["go_i", { name: p.name, h: this.turn_no }]; }
    roundLabel() { return ["go_rp", { n: this.turn_no, r: this.settings.holes }]; }
    info() { return [["go_info", {}]]; }
    view(p) {
      const meta = [["go_v_holes", { n: p.holes.length }]];
      if (p.last !== null) meta.push(["go_v_now", { n: p.last }]);
      return { big: p.score, meta, badge: null };
    }
  }

  // ================================================================== Gotcha
  class Gotcha extends TurnGame {
    get MODE() { return "gotcha"; }
    defaultSettings() { return { target: 301 }; }
    cleanSettings(d) {
      const t = intOf(d || {}, "target", 301);
      if (![201, 301, 501].includes(t)) throw new GameError("err_settings");
      return { target: t };
    }
    instr(p) { return ["gt_i", { name: p.name, n: this.settings.target - p.score }]; }
    onDart(p, d) {
      const tgt = this.settings.target;
      const nw = p.score + d.score;
      if (nw > tgt) {
        p.score = this.turn_start;
        this.turn_over = true;
        this._say("hit", "gt_l_bust", "xo_s_bust", { name: p.name, label: d.label, score: p.score });
        return;
      }
      p.score = nw;
      this._say("info", "cu_l_dart", null, { name: p.name, label: d.label, score: nw });
      if (nw === tgt) { p.done = true; p.won = true; this.turn_over = true; this._finish(); return; }
      for (const q of this.players) {
        if (q !== p && q.score === nw && nw > 0) {
          q.score = 0; p.hits += 1;
          this._say("hit", "gt_l_gotcha", "gt_s_gotcha", { name: p.name, owner: q.name });
          this._effect("out", { player: q.index });
        }
      }
    }
    checkoutRoute(p) {
      const rem = this.settings.target - p.score;
      return rem <= 60 ? checkout(rem, DARTS - this.turn_darts.length, "straight") : null;
    }
    rankKey(p) { return [p.won ? 0 : 1, -p.score]; }
    info() { return [["gt_info", { n: this.settings.target }]]; }
    view(p) { return { big: p.score, meta: [["gt_v_left", { n: this.settings.target - p.score }]], badge: null }; }
  }

  const PARTY_GAMES = {};
  for (const C of [AroundClock, Shanghai, Bobs27, HalveIt, Cricket, Bulls, Doubles, RandomCheckout, Killer, Golf, Gotcha]) {
    PARTY_GAMES[new C().MODE] = C;
  }
  const api = { PARTY_GAMES, Rng, hits };
  if (node) module.exports = api;
  else root.AfgooienParty = api;
})(typeof window !== "undefined" ? window : globalThis);
