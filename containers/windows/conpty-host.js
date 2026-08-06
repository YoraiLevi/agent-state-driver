// The Windows hosting layer: one ConPTY host per agent session.
// Windows sibling of the tmux backend — see docs/.research/empirical/windows-leg.md
// (this is that document's Appendix driver, with the target made a parameter and
// no hard-coded user path).
//
//   node conpty-host.js <workdir> <statedir> [exe] [args...]
//
// Commands are appended as lines to <statedir>\inbox.txt:
//   TEXT <s> | CR | ESC | CTRLC | UP | DOWN | DIGIT n | KILL
// State is published to <statedir>\{meta.json,raw.log,screen.txt}.
//
// Env: CLAUDE_EXE (target if not given as argv), DRIVER_TTL_MS (default 600000 —
// a bounded run, so a forgotten host cannot sit on a subscription indefinitely).

const fs = require('fs'), path = require('path'), pty = require('node-pty');
const { Terminal } = require('@xterm/headless');

const [workdir, statedir, ...rest] = process.argv.slice(2);
if (!workdir || !statedir) {
  console.error('usage: node conpty-host.js <workdir> <statedir> [exe] [args...]');
  process.exit(2);
}
const exe = rest[0] || process.env.CLAUDE_EXE || 'claude.exe';
const args = rest.slice(1);

fs.mkdirSync(statedir, { recursive: true });
const rawPath = path.join(statedir, 'raw.log');
const inboxPath = path.join(statedir, 'inbox.txt');
fs.writeFileSync(rawPath, '');
fs.writeFileSync(inboxPath, '');

const p = pty.spawn(exe, args, {
  name: 'xterm-256color', cols: 120, rows: 40, cwd: workdir, env: process.env,
});

// ptyPid is simultaneously the agent PID, the sidecar filename and the liveness
// handle. Cache it at launch: the sidecar that names it is deleted on clean exit,
// so a lookup at death time fails exactly when it is needed (PITFALLS).
fs.writeFileSync(path.join(statedir, 'meta.json'), JSON.stringify({
  ptyPid: p.pid, driverPid: process.pid, exe, args, workdir, startedAt: Date.now(),
}));

const term = new Terminal({ cols: 120, rows: 40, allowProposedApi: true, scrollback: 2000 });

setInterval(() => {                                   // the screen channel
  const b = term.buffer.active, out = [];
  for (let i = 0; i < term.rows; i++) {
    const l = b.getLine(b.viewportY + i);
    out.push(l ? l.translateToString(true) : '');
  }
  // Visible viewport only — never scrollback. Matching liveness over history
  // reports busy on a session idle for minutes (PITFALLS, capture-region rule).
  fs.writeFileSync(path.join(statedir, 'screen.txt'), out.join('\n') + '\n');
}, 500);

p.onData((d) => { fs.appendFileSync(rawPath, d); term.write(d); });
p.onExit((e) => {
  fs.appendFileSync(rawPath, '\n[[exited ' + JSON.stringify(e) + ']]\n');
  process.exit(0);
});

let offset = 0;                                       // the drive channel
setInterval(() => {
  const s = fs.readFileSync(inboxPath, 'utf8');
  if (s.length <= offset) return;
  const chunk = s.slice(offset); offset = s.length;
  for (const line of chunk.split('\n')) {
    if (!line.trim()) continue;
    const sp = line.indexOf(' ');
    const verb = sp === -1 ? line.trim() : line.slice(0, sp);
    const arg = sp === -1 ? '' : line.slice(sp + 1);
    if (verb === 'TEXT') p.write(arg);
    else if (verb === 'CR') p.write('\r');
    else if (verb === 'ESC') p.write('\x1b');
    else if (verb === 'CTRLC') p.write('\x03');
    else if (verb === 'DOWN') p.write('\x1b[B');
    else if (verb === 'UP') p.write('\x1b[A');
    else if (verb === 'DIGIT') p.write(arg.trim());
    else if (verb === 'KILL') p.kill();
  }
}, 250);

setTimeout(() => { p.kill(); setTimeout(() => process.exit(0), 1500); },
           Number(process.env.DRIVER_TTL_MS || 600000));
