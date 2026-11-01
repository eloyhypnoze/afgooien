#!/usr/bin/env python3
"""Bouw de testversie: één losse HTML-pagina die zonder installatie in de browser draait.

De spelregels komen uit web/engine.js: een exacte kopie van afgooien/engine.py
(tests/test_parity.py controleert dat). De pagina werkt zonder server en zonder
internet. Invoer gaat handmatig door op het bord te klikken.

    python tools/build_testversie.py     ->  dist/afgooien-testversie.html
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOADER = r"""
window.AFGOOIEN_LOCAL = (function () {
  const KEY = "afgooien.testversie.spel";
  const HKEY = "afgooien.testversie.geschiedenis";
  const { Dart, GameError, tr } = window.AfgooienEngine;
  const { makeGame } = window.AfgooienGames;
  let g = makeGame("afgooien"), mode = "afgooien";
  const LKEY = "afgooien.testversie.taal";
  let lang = "nl";
  try { const l = localStorage.getItem(LKEY); if (l === "en" || l === "nl") lang = l; } catch (e) { /* */ }
  let n = 0, gameId = null, history = [], hver = 0;
  const pad = (x) => String(x).padStart(2, "0");
  function stamp(sep) {
    const d = new Date();
    return `${d.getFullYear()}${sep}${pad(d.getMonth() + 1)}${sep}${pad(d.getDate())}`;
  }
  function newId() {
    const d = new Date();
    return `${stamp("")}-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}-` +
      Math.floor(Math.random() * 65536).toString(16).padStart(4, "0");
  }
  function nowIso() { const d = new Date(); return `${stamp("-")}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`; }
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) || "null");
    if (saved) { mode = saved.mode || "afgooien"; g = makeGame(mode); g.loadEvents(saved.events || []); gameId = saved.id || null; }
  } catch (e) { /* geen opslag */ }
  try { const h = JSON.parse(localStorage.getItem(HKEY) || "[]"); if (Array.isArray(h)) history = h; } catch (e) { /* */ }
  const PKEY = "afgooien.testversie.spelers";
  let reg = { players: [], since: {} };
  try { const r = JSON.parse(localStorage.getItem(PKEY) || "null"); if (r && Array.isArray(r.players)) reg = { players: r.players, since: r.since || {} }; } catch (e) { /* */ }
  const pk = (n) => String(n).trim().toLowerCase();
  const findP = (n) => reg.players.find((p) => pk(p.name) === pk(n));
  function savePlayers() { reg.players.sort((a, b) => pk(a.name) < pk(b.name) ? -1 : 1); hver++; try { localStorage.setItem(PKEY, JSON.stringify(reg)); } catch (e) { /* */ } }
  function playerCmd(t, name) {
    const n = String(name || "").trim().slice(0, 24);
    if (!n) throw new GameError("err_name_required");
    if (t === "player_add") { if (findP(n)) throw new GameError("err_name_exists", { name: n }); reg.players.push({ name: n, created: nowIso() }); }
    else { const p = findP(n); if (!p) throw new GameError("err_no_player"); if (t === "player_delete") reg.players.splice(reg.players.indexOf(p), 1); reg.since[pk(n)] = nowIso(); }
    savePlayers();
  }
  function saveHistory() { hver++; try { localStorage.setItem(HKEY, JSON.stringify(history)); } catch (e) { /* */ } }
  function sync() {
    if (!gameId) return;
    const sm = g.summary();
    const idx = history.findIndex((h) => h.id === gameId);
    if (!sm) { if (idx < 0) return; history.splice(idx, 1); return saveHistory(); }
    const entry = { id: gameId, ended: nowIso(), ...sm };
    if (idx < 0) history.push(entry);
    else {
      const strip = (o) => JSON.stringify({ ...o, ended: "" });
      if (strip(history[idx]) === strip(entry)) return;
      history[idx] = entry;
    }
    saveHistory();
  }
  let extraNotice = null, botTimer = null;
  const listeners = [];
  function state() {
    const s = g.state(lang);
    if (extraNotice && !s.notice) s.notice = tr(lang, extraNotice);
    s.source = { enabled: false, mode: "test" };
    s.app_version = "__APP_VERSION__";
    s.history_version = hver;
    s.key = g.version + "." + (n++);
    return s;
  }
  function persist() {
    sync();
    try { localStorage.setItem(KEY, JSON.stringify({ id: gameId, mode, events: g.events })); } catch (e) { /* geen opslag */ }
  }
  function scheduleBot() {
    clearTimeout(botTimer);
    const a = window.AfgooienBot.nextAction(g.state());
    if (!a) return;
    const ver = g.version;
    botTimer = setTimeout(() => {
      if (g.version !== ver) return;
      try { apply(a); } catch (e) { if (!(e instanceof GameError)) throw e; return; }
      extraNotice = null;
      persist();
      const st = state();
      listeners.forEach((f) => f(st));
      scheduleBot();
    }, window.AfgooienBot.delayFor(a));
  }
  function apply(cmd) {
    switch (cmd.type) {
        case "new_game": {
          const ng = makeGame(cmd.mode || "afgooien");
          ng.newGame(cmd.players || [], cmd.settings, cmd.bots);
          g = ng; mode = cmd.mode || "afgooien"; gameId = newId();
          let added = false;
          g.players.filter((p) => !p.bot).forEach((p) => { if (!findP(p.name)) { reg.players.push({ name: p.name, created: nowIso() }); added = true; } });
          if (added) savePlayers();
          break;
        }
        case "player_add": case "player_delete": case "player_reset": playerCmd(cmd.type, cmd.name); break;
        case "dart": g.throw_(Dart.fromDict(cmd)); break;
        case "correct": g.correct(cmd.index, Dart.fromDict(cmd)); break;
        case "next": g.nextPlayer(); break;
        case "allocate": g.allocate(cmd.alloc || []); break;
        case "finish": if (!g.finish) throw new GameError("err_unknown_cmd", { cmd: cmd.type }); g.finish(); break;
        case "shootout": if (!g.choose) throw new GameError("err_unknown_cmd", { cmd: cmd.type }); g.choose(cmd.choice); break;
        case "undo": g.undo(); break;
        case "reset": g.reset(); gameId = null; break;
        case "clear_history": history = []; saveHistory(); if (g.phase === "finished") gameId = null; break;
        case "board_reset": case "board_cmd": extraNotice = "x_test_nocam"; break;
        case "set_lang":
          if (cmd.lang !== "nl" && cmd.lang !== "en") throw new GameError("err_lang");
          lang = cmd.lang; hver++;
          try { localStorage.setItem(LKEY, lang); } catch (e) { /* */ }
          break;
        default: throw new GameError("err_unknown_cmd", { cmd: cmd.type });
    }
  }
  function send(cmd) {
    extraNotice = null;
    try { apply(cmd); } catch (e) {
      if (e instanceof GameError) return Promise.resolve({ ok: false, error: e.text(lang) });
      throw e;
    }
    persist();
    scheduleBot();
    return Promise.resolve({ ok: true, state: state() });
  }
  setTimeout(scheduleBot, 500);   // een lopend potje met een bot aan de beurt hervatten
  return { ready: Promise.resolve(state()), send, onUpdate: (f) => listeners.push(f),
           history: () => Promise.resolve({ version: hver, games: history, players: reg.players, since: reg.since }) };
})();
"""


def js_str(s: str) -> str:
    return json.dumps(s).replace("</", "<\\/")


def build() -> Path:
    html = (ROOT / "web" / "index.html").read_text("utf-8")
    css = (ROOT / "web" / "style.css").read_text("utf-8")
    app = (ROOT / "web" / "app.js").read_text("utf-8")
    messages = (ROOT / "afgooien" / "messages.json").read_text("utf-8")
    engine = ("window.AFGOOIEN_MESSAGES = " + messages + ";\n" + (ROOT / "web" / "engine.js").read_text("utf-8")
              + "\n" + (ROOT / "web" / "games.js").read_text("utf-8")
              + "\n" + (ROOT / "web" / "party.js").read_text("utf-8")
              + "\n" + (ROOT / "web" / "bot.js").read_text("utf-8"))
    i18n = (ROOT / "web" / "i18n.js").read_text("utf-8")

    version = re.search(r'__version__ = "([^"]+)"', (ROOT / "afgooien" / "__init__.py").read_text("utf-8")).group(1)
    import base64
    def font_uri(m):
        data = (ROOT / "web" / "fonts" / m.group(1)).read_bytes()
        return 'url("data:font/woff;base64,' + base64.b64encode(data).decode() + '")'
    css = re.sub(r'url\("fonts/([^"]+\.woff)"\)', font_uri, css)
    html = html.replace('<link rel="stylesheet" href="/static/style.css">', f"<style>\n{css}\n</style>")
    html = html.replace("<title>Afgooien</title>", "<title>Afgooien – testversie</title>")
    icon = base64.b64encode((ROOT / "web" / "icon.png").read_bytes()).decode()
    html = html.replace('href="/static/icon.png"', f'href="data:image/png;base64,{icon}"')
    app_safe = app.replace("</script", "<\\/script")
    scripts = (
        f"<script>\n{engine.replace('</script', '<' + chr(92) + '/script')}\n{LOADER.replace('__APP_VERSION__', version)}</script>\n"
        f"<script>\n{i18n.replace('</script', '<' + chr(92) + '/script')}\n</script>\n"
        f"<script>\n{app_safe}\n</script>"
    )
    html, n = re.subn(r'<script src="/static/i18n.js"></script>\s*<script src="/static/app.js"></script>', lambda m: scripts, html)
    assert n == 1, "app.js-tag niet gevonden"
    out = ROOT / "dist" / "afgooien-testversie.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(html, "utf-8")
    return out


if __name__ == "__main__":
    p = build()
    print(f"Gemaakt: {p} ({p.stat().st_size // 1024} KB)")
