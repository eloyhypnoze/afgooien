"use strict";
// Bots voor Afgooien: dezelfde logica als afgooien/bot.py (voor de testversie).
(function (root) {
  const SEG = [20, 1, 18, 4, 13, 6, 10, 15, 2, 17, 3, 19, 7, 16, 8, 11, 14, 9, 12, 5];
  const HIT = { 1: 0.096, 2: 0.22, 3: 0.357, 4: 0.471, 5: 0.611, 6: 0.74 };
  const OUTSIDE = { 1: 0.10, 2: 0.07, 3: 0.05, 4: 0.035, 5: 0.02, 6: 0.01 };
  const BULL_SIGMA = { 1: 0.45, 2: 0.36, 3: 0.28, 4: 0.22, 5: 0.17, 6: 0.13 };
  const RINGS = { bullseye: [0.0, 0.035], bull: [0.042, 0.088], inner: [0.12, 0.56], triple: [0.588, 0.623],
                  outer: [0.65, 0.94], double: [0.958, 0.995], out: [1.36, 1.5] };
  const R = Math.random;
  const uni = (a, b) => a + (b - a) * R();
  const pick = (arr) => arr[Math.floor(R() * arr.length)];
  function weighted(items, weights) {
    let t = R() * weights.reduce((a, b) => a + b, 0);
    for (let i = 0; i < items.length; i++) { t -= weights[i]; if (t < 0) return items[i]; }
    return items[items.length - 1];
  }
  function gauss() { let u = 0, v = 0; while (!u) u = R(); while (!v) v = R(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); }
  const r4 = (x) => Math.round(x * 1e4) / 1e4;

  function segmentAt(x, y) {
    const r = Math.hypot(x, y) * 170;
    if (r <= 6.35) return [25, 2];
    if (r <= 15.9) return [25, 1];
    if (r > 170) return [0, 0];
    const ang = Math.atan2(y, x) * 180 / Math.PI;
    const idx = ((Math.round((90 - ang) / 18) % 20) + 20) % 20;
    return [SEG[idx], r >= 162 ? 2 : (r >= 99 && r <= 107) ? 3 : 1];
  }
  function dart(number, ring) {
    const [lo, hi] = RINGS[ring];
    const r = uni(lo, hi);
    const ang = (number === 0 || number === 25) ? uni(0, 360) : 90 - SEG.indexOf(number) * 18 + uni(-7.5, 7.5);
    const x = r * Math.cos(ang * Math.PI / 180), y = r * Math.sin(ang * Math.PI / 180);
    const [num, mult] = segmentAt(x, y);
    return { type: "dart", number: num, multiplier: mult, x: r4(x), y: r4(y) };
  }
  const ringFor = (m) => (m === 3 ? "triple" : m === 2 ? "double" : pick(["inner", "outer"]));

  function dartAt(number, level) {
    if (R() < HIT[level]) return dart(number, ringFor(weighted([1, 2, 3], [70, 15, 15])));
    const r = R();
    if (r < OUTSIDE[level]) return dart(0, "out");
    if (r < OUTSIDE[level] + 0.02) return dart(25, pick(["bull", "bull", "bullseye"]));
    const i = SEG.indexOf(number);
    const nb = R() < 0.8 ? SEG[(i + pick([-1, 1]) + 20) % 20] : pick(SEG);
    return dart(nb, ringFor(weighted([1, 2, 3], [85, 7.5, 7.5])));
  }
  function wrongArmDart() {
    const ring = weighted(["inner", "outer", "triple", "double", "bull", "out"], [42, 43, 5, 5, 2, 3]);
    return dart(ring === "bull" ? 25 : ring === "out" ? 0 : pick(SEG), ring);
  }
  function bullThrow(level) {
    const r = Math.abs(gauss() * BULL_SIGMA[level]), ang = uni(0, 2 * Math.PI);
    const x = r * Math.cos(ang), y = r * Math.sin(ang);
    const [num, mult] = segmentAt(x, y);
    return { type: "dart", number: num, multiplier: mult, x: r4(x), y: r4(y) };
  }
  function chooseAllocation(st, level) {
    const pd = st.pending;
    let left = pd.points;
    const alloc = new Map();
    if (level <= 2) {
      for (let k = 0; k < left; k++) { const t = pick(pd.targets); alloc.set(t, (alloc.get(t) || 0) + 1); }
    } else {
      const order = pd.targets.slice().map((i) => [st.players[i].points, R(), i]).sort((a, b) => a[0] - b[0] || a[1] - b[1]).map((x) => x[2]);
      for (const i of order) {
        if (!left) break;
        const n = Math.min(left, Math.max(1, st.players[i].points));
        alloc.set(i, n); left -= n;
      }
      if (left) alloc.set(order[0], (alloc.get(order[0]) || 0) + left);
    }
    return [...alloc.entries()];
  }
  function chooseTarget(st, me, level) {
    if (me.points < st.settings.target) return me.number;
    const opp = st.players.filter((q) => q.index !== me.index && !q.out);
    if (level <= 2 && R() < 0.5) return pick(opp).number;
    const low = Math.min(...opp.map((q) => q.points));
    return pick(opp.filter((q) => q.points === low)).number;
  }
  // ---- X01 en Count Up: mikken met spreiding (zelfde getallen als afgooien/bot.py)
  const SIGMA = { 1: 86.5, 2: 44.4, 3: 24.6, 4: 18.5, 5: 15.1, 6: 11.5 };
  const GOOD_LEAVES = [40, 32, 16, 36, 24, 20, 8, 12, 28, 18, 10, 4, 38, 34, 30, 26, 22, 14, 6, 2];
  function aimPoint(code) {
    if (code === "Bullseye") return [0, 0];
    if (code === "Bull") return [0, 11];
    const r = { T: 103, D: 166, S: 135 }[code[0]];
    const ang = (90 - SEG.indexOf(+code.slice(1)) * 18) * Math.PI / 180;
    return [r * Math.cos(ang), r * Math.sin(ang)];
  }
  function throwAt(code, level) {
    const [ax, ay] = aimPoint(code);
    const x = (ax + gauss() * SIGMA[level]) / 170, y = (ay + gauss() * SIGMA[level]) / 170;
    const [num, mult] = segmentAt(x, y);
    return { type: "dart", number: num, multiplier: mult, x: r4(x), y: r4(y) };
  }
  function x01Target(st, me) {
    const s = st.settings;
    if (!me.opened) return s.in_mode === "double" ? "D20" : "T20";
    if (st.checkout) return st.checkout[0];
    const rem = me.score, low = s.out_mode === "straight" ? 1 : 2;
    if (rem - 60 >= low && rem > 60) return "T20";
    for (const leave of GOOD_LEAVES) { const single = rem - leave; if (single >= 1 && single <= 20) return "S" + single; }
    return rem - 1 >= low ? "S1" : "S20";
  }
  const CRICKET = [20, 19, 18, 17, 16, 15, 25];
  function code(t, level) {
    const n = t.n;
    if (t.t === "dbl") return n === 25 ? "Bullseye" : "D" + n;
    if (t.t === "trp") return "T" + n;
    if (t.t === "bull" || n === 25) return "Bullseye";
    if (t.t === "any_d") return level <= 3 ? "D16" : "D20";
    if (t.t === "any_t") return "T20";
    return (level >= 4 ? "T" : "S") + n;
  }
  function partyTarget(st, me, level) {
    const mode = st.mode, t = st.target;
    if (st.checkout) return st.checkout[0];
    if (mode === "shanghai") {
      const hit = new Set(st.darts.filter((d) => d.number === t.n).map((d) => d.multiplier));
      const m = [3, 2, 1].find((x) => !hit.has(x)) || 3;
      return "SDT"[m - 1] + t.n;
    }
    if (mode === "cricket") {
      for (let k = 0; k < CRICKET.length; k++) if (me.marks[k] < 3) return CRICKET[k] === 25 ? "Bullseye" : "T" + CRICKET[k];
      if (st.settings.scoring !== "noscore") {
        for (let k = 0; k < CRICKET.length; k++) {
          if (st.players.some((q) => q.index !== me.index && q.marks[k] < 3)) return CRICKET[k] === 25 ? "Bullseye" : "T" + CRICKET[k];
        }
      }
      return "Bullseye";
    }
    if (mode === "killer") {
      if (!me.killer) return "D" + me.number;
      const opp = st.players.filter((q) => q.index !== me.index && !q.out);
      const low = Math.min(...opp.map((q) => q.score));
      return "D" + opp.find((q) => q.score === low).number;
    }
    if (mode === "golf") {
      if (me.last !== null && me.last <= (level >= 4 ? 2 : 3)) return null;
      return "T" + t.n;
    }
    if (mode === "gotcha") return st.settings.target - me.score > 60 ? "T20" : "S1";
    if (mode === "countup") return "T20";
    if (mode === "checkout") return x01Target({ settings: { in_mode: "straight", out_mode: "double" }, checkout: null }, { opened: true, score: me.rem });
    return t ? code(t, level) : "T20";
  }
  function nextActionOther(st, me, level) {
    if (st.waiting) return { type: "next" };
    if (st.phase === "bulloff") return throwAt("Bullseye", level);
    if (st.mode === "x01") return throwAt(x01Target(st, me), level);
    const c = partyTarget(st, me, level);
    if (c === null) return { type: "next" };
    return throwAt(c, level);
  }

  function nextAction(st) {
    const cur = st.current;
    if (cur === null || cur === undefined || !["select", "play", "bulloff"].includes(st.phase)) return null;
    const me = st.players[cur];
    const level = me.bot || 0;
    if (!level) return null;
    if (st.mode && st.mode !== "afgooien") return nextActionOther(st, me, level);
    if (st.phase === "select") {
      if (st.sel_step === "number") return wrongArmDart();
      if (st.sel_step === "bull") return bullThrow(level);
      return { type: "next" };
    }
    if (st.pending) return { type: "allocate", alloc: chooseAllocation(st, level) };
    if (st.darts.length >= st.settings.darts_per_turn) return { type: "next" };
    return dartAt(chooseTarget(st, me, level), level);
  }
  const delayFor = (a) => ({ dart: 1100, next: 1800, allocate: 1500 }[a.type] || 1000);

  const api = { nextAction, delayFor, segmentAt, HIT, SIGMA, x01Target, partyTarget };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.AfgooienBot = api;
})(typeof window !== "undefined" ? window : globalThis);
