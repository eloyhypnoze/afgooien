// Meet het gemiddelde aantal punten per beurt van de JavaScript-bots (test_bots.py roept dit aan).
const path = require("path");
const { Game } = require(path.join(__dirname, "..", "web", "engine.js"));
const bot = require(path.join(__dirname, "..", "web", "bot.js"));
const games = +(process.argv[2] || 200);
const out = {};
for (let level = 1; level <= 6; level++) {
  let pts = 0, turns = 0;
  for (let k = 0; k < games; k++) {
    const g = new Game();
    g.newGame(["B0", "B1", "B2"], null, [level, level, level]);
    for (let step = 0; step < 5000; step++) {
      const st = g.state();
      if (st.phase === "finished") break;
      const a = bot.nextAction(st);
      if (a.type === "dart") { const d = { ...a }; delete d.type; g.throw_(d); }
      else if (a.type === "next") g.nextPlayer();
      else if (a.type === "allocate") g.allocate(a.alloc);
    }
    for (const p of g.players) { pts += p.gained + p.knocked; turns += p.turns; }
  }
  out[level] = pts / turns;
}
console.log(JSON.stringify(out));
