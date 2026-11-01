// Speelt de opdrachten uit test_parity.py met web/engine.js en vergelijkt de spelstand.
const fs = require("fs");
const path = require("path");
const { GameError } = require(path.join(__dirname, "..", "web", "engine.js"));
const { makeGame } = require(path.join(__dirname, "..", "web", "games.js"));

function canon(v) {          // volgorde van sleutels negeren
  if (Array.isArray(v)) return v.map(canon);
  if (v && typeof v === "object") {
    const o = {};
    for (const k of Object.keys(v).sort()) o[k] = canon(v[k]);
    return o;
  }
  return v;
}
function firstDiff(a, b, p = "") {
  if (JSON.stringify(a) === JSON.stringify(b)) return null;
  if (a && b && typeof a === "object" && typeof b === "object") {
    for (const k of new Set([...Object.keys(a), ...Object.keys(b)])) {
      const d = firstDiff(a[k], b[k], `${p}.${k}`);
      if (d) return d;
    }
  }
  return `${p}: py=${JSON.stringify(a)} js=${JSON.stringify(b)}`;
}

const data = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
let steps = 0;
for (const [gi, run] of data.entries()) {
  const g = makeGame(run[0].mode);
  for (const [si, step] of run.entries()) {
    const c = step.cmd;
    let err = null;
    try {
      if (c.type === "new_game") g.newGame(c.players, c.settings, c.bots);
      else if (c.type === "dart") { const d = { ...c }; delete d.type; g.throw_(d); }
      else if (c.type === "takeout") g.takeout();
      else if (c.type === "next") g.nextPlayer();
      else if (c.type === "undo") g.undo();
      else if (c.type === "allocate") g.allocate(c.alloc);
      else if (c.type === "choose") g.choose(c.choice);
      else if (c.type === "finish") g.finish();
      else if (c.type === "correct") { const d = { ...c }; delete d.type; delete d.index; g.correct(c.index, d); }
    } catch (e) {
      if (!(e instanceof GameError)) throw e;
      err = { nl: e.text("nl"), en: e.text("en") };
    }
    const want = canon({ error: step.error, state: step.state, state_en: step.state_en, events: step.events, summary: step.summary });
    const got = canon({ error: err, state: g.state(), state_en: g.state("en"), events: g.events, summary: g.summary() });
    const d = firstDiff(want, got);
    if (d) {
      console.log(`VERSCHIL in potje ${gi}, stap ${si}, opdracht ${JSON.stringify(c)}\n${d}`);
      process.exit(1);
    }
    steps++;
  }
}
console.log(`OK: ${data.length} potjes, ${steps} stappen identiek`);
