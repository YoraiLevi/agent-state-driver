// Credential-free Windows equivalent of prototypes/mockagent/portability_check.py.
//
// The Linux check drives a mock agent under tmux. There is no tmux on Windows;
// the hosting layer is node-pty (ConPTY) + @xterm/headless (docs/.research/
// empirical/windows-leg.md). This asserts THAT layer works inside the container:
// the PTY spawns, bytes flow, the headless terminal renders them, injected
// keystrokes reach the child, and exit is observed. Those are exactly the four
// capabilities the real driver needs from the host; nothing here needs claude,
// credentials or the network.
//
// Exit 0 = all checks passed.

const fs = require('fs');
const path = require('path');

const results = [];
function check(name, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  results.push({ name, want, got, ok });
  console.log(
    name.padEnd(34) + ' want=' + String(want).padEnd(20) +
    ' got=' + String(got).padEnd(20) + (ok ? ' ok' : ' FAIL'));
  return ok;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  console.log('platform:', process.platform, '| node', process.versions.node,
              '| modules', process.versions.modules);

  let pty = null;
  try { pty = require('node-pty'); } catch (e) { console.log('require failed:', e.message); }
  check('node-pty loads', pty !== null, true);
  check('node-pty exports spawn', pty !== null && typeof pty.spawn === 'function', true);

  // node-pty vendors the ConPTY runtime; if these are missing the spawn will
  // fail at runtime on a machine with no Windows Terminal installed.
  const rel = path.join(path.dirname(require.resolve('node-pty')), '..', 'build', 'Release', 'conpty');
  check('conpty.dll vendored', fs.existsSync(path.join(rel, 'conpty.dll')), true);
  check('OpenConsole.exe vendored', fs.existsSync(path.join(rel, 'OpenConsole.exe')), true);

  const { Terminal } = require('@xterm/headless');
  const term = new Terminal({ cols: 120, rows: 30, allowProposedApi: true, scrollback: 200 });
  check('@xterm/headless constructs', typeof term.write === 'function', true);

  const screen = () => {
    const b = term.buffer.active;
    const out = [];
    for (let i = 0; i < term.rows; i++) {
      const l = b.getLine(b.viewportY + i);
      out.push(l ? l.translateToString(true) : '');
    }
    return out.join('\n');
  };

  let bytes = 0;
  let exitEvent = null;
  const p = pty.spawn(process.env.COMSPEC || 'C:\\Windows\\System32\\cmd.exe', [], {
    name: 'xterm-256color', cols: 120, rows: 30, cwd: process.env.TEMP || 'C:\\',
    env: process.env,
  });
  p.onData((d) => { bytes += d.length; term.write(d); });
  p.onExit((e) => { exitEvent = e; });

  check('ConPTY spawn returns a pid', Number.isInteger(p.pid) && p.pid > 0, true);

  await sleep(2500);
  check('bytes flow from the pty', bytes > 0, true);
  check('headless terminal renders', screen().trim().length > 0, true);

  // Keystroke injection — the drive channel. Same write path the real driver
  // uses to answer a trust or permission dialog.
  p.write('echo HELLO-CONPTY\r');
  await sleep(2500);
  check('injected keys reach child', screen().includes('HELLO-CONPTY'), true);

  p.write('exit\r');
  for (let i = 0; i < 40 && exitEvent === null; i++) await sleep(250);
  check('clean exit observed', exitEvent !== null, true);
  check('exit code 0', exitEvent && exitEvent.exitCode, 0);

  const bad = results.filter((r) => !r.ok);
  console.log('\n' + (results.length - bad.length) + '/' + results.length + ' checks passed');
  process.exit(bad.length ? 1 : 0);
}

main().catch((e) => { console.error('selftest crashed:', e); process.exit(1); });
