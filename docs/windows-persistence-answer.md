# Solving the Windows persistence problem with Ori's software

**The question:** the [persistent-shell-sessions gist](https://gist.github.com/YoraiLevi/acaa0b584389cecae0036db4624f0210)
describes a concrete failure — a coding agent runs for hours inside a terminal pane owned by
an ADE; close, restart or swap the ADE and every running agent dies with it. Can AgentCulture
solve it?

**Verdict: partly, and the split is clean.** The gist frames any tool by four independent
questions. Ori's software answers two of them on native Windows. It answers neither of the
other two, and declines one explicitly. Our ConPTY work answers exactly those two.

**They compose. Neither is sufficient alone.**

---

## 1. The four questions, answered

| Question | What it means | AgentCulture | Ours |
|---|---|---|---|
| **Owner** | who calls `CreatePseudoConsole` and holds the `HPCON` | **nothing** — no PTY layer anywhere in the ecosystem | node-pty ConPTY host, ~90 lines, user-scope |
| **Lifetime** | does the owner outlive its launcher (L0–L3) | **L0 as shipped on Windows** — `agentirc start` refuses to daemonize | **L2** via per-user `schtasks`, verified surviving into a separate SSH session |
| **Rendezvous** | what address client and owner meet at | **agentirc — verified working on native Windows** | — adopt his |
| **Payload** | what crosses the boundary | **`PRESENCE :<json>`** — verified round-trip on native Windows | our evidence-carrying state fills the *content* |

**Read as:** he owns the meeting place; we own the thing that survives. The gist's problem is
Owner + Lifetime, so AgentCulture alone does not solve it — but it removes the need to invent
a rendezvous, which the gist spends pages evaluating (named pipes vs loopback TCP vs AF_UNIX).

---

## 2. Evidence — measured on windesk, 2026-08-06

**Correction to our own [ecosystem map](ecosystem-map.md):** it recorded *"Windows is an
explicit refusal at the daemon layer."* That is **too strong**, and the map is wrong.

**Observed.** `agentirc-cli` 9.12.0 installed under `uv` on Windows 11 build 26200 and served:

```
server pid=1568
:agentirc 001 agentirc-winprobe :Welcome to agentirc IRC Network
:agentirc PRESENCELIST :{"nick":"agentirc-winprobe","server":"agentirc","state":"thinking",
                         "since":"2026-08-06T12:00:00Z","presumed_hung":false,…}
:agentirc PRESENCEEND :End of presence list
```

**The refusal is narrower than reported.** `agentirc/cli.py:570-572` guards only
`_daemonize_server`, which needs `os.fork()`:

```python
if sys.platform == "win32":
    print("Daemon mode not supported on Windows. Use --foreground.", file=sys.stderr)
```

**Conclusion:** the server, the wire and the presence protocol all work on native Windows.
Only *self-daemonization* does not — which is a **Lifetime** limitation, i.e. precisely the
gist's own problem, applied to Ori's server itself.

---

## 3. The irony worth noticing

`agentirc serve` on Windows has **the same disease the gist describes.** It cannot
daemonize, so it dies with the shell that launched it — L0.

Our middle layer exists to give an arbitrary child process L2 lifetime on Windows.

**So the middle layer can host his server.** The tool that solves the gist's problem for
coding agents solves it for the mesh daemon too, with no special-casing.

---

## 4. The architecture

```
Windows 11 host
├── scheduled task (per-user, no admin)         ← Lifetime: L2, survives ADE death + logoff
│   └── node ConPTY host (owns the HPCON)       ← Owner
│       ├── claude.exe                          ← the agent, survives its launcher
│       └── agentirc serve --foreground         ← optional: the mesh, same treatment
└── state driver (sidecar + screen + process)   ← what state the agent is in, with evidence
        │
        └── publishes PRESENCE ────────────► agentirc  ← Rendezvous + Payload
                                                 │
                        any client, any machine ─┘   ← discovery, not a guessed pipe name
```

**What each layer buys, in one line each:**

- **ConPTY host** — the agent stops dying when the ADE closes. Nothing in AgentCulture does this.
- **schtasks** — survives logoff and reboot; `fork()` is not available and is not needed.
- **agentirc** — a *discoverable* rendezvous. The gist's alternatives (named pipe, loopback port) require the client to already know the address; `PRESENCE LIST` enumerates surviving sessions instead.
- **state driver** — makes the presence row *true* rather than self-reported.

---

## 5. What this replaces from the gist's own research

| The gist evaluated | Now unnecessary, because |
|---|---|
| Seven standalone PTY daemons | Our 90-line host answers Owner; the daemons were candidates for that slot |
| Named pipe vs loopback TCP vs AF_UNIX rendezvous | agentirc is the rendezvous, and it is already running on the tailnet |
| Inventing a control protocol | `PRESENCE` is specified, tested, and federates between hosts |
| "Which ADE has an override hook" | Still relevant — the override is how the middle layer gets inserted |

**Still unsolved by both, and named honestly:**

- **Double-ConPTY nesting** — the gist flags it as never empirically tested for any candidate. Our host runs one ConPTY; under an ADE that owns its own, that is two, and we have not measured it either.
- **L3 (survives reboot)** — `schtasks` can do it; not verified.
- **Ori's six-state enum has no waiting state**, so a Windows agent blocked on a permission prompt is published as `thinking` and later mislabelled `presumed_hung`. Our draft branch adds `waiting` + `waiting_for`; unsent.

---

## 6. What to do, in order

1. **Insert the middle layer via the ADE's override hook** (`agentCmdOverrides` for ORCA). The
   host spawns `claude.exe` and holds the `HPCON`.
2. **Register it as a scheduled task** so it outlives the ADE. Do not redirect std handles —
   `Start-Process -RedirectStandardOutput` silently kills a ConPTY spawn.
3. **Run `agentirc serve --foreground`**, either on the Windows host under the same middle
   layer, or on a Linux/macOS box on the tailnet where it can daemonize normally.
   *Recommended: a Linux host, so the mesh does not share a failure domain with the agents.*
4. **Publish observed state** from the state driver as `PRESENCE`, nick-prefixed `agentirc-`.
5. **Discover survivors with `PRESENCE LIST`** after an ADE restart, instead of reconnecting to
   a remembered pipe name.

---

## 7. Coverage of this answer

**Verified today:** agentirc installs, serves and speaks presence on native Windows 11;
the daemon guard is `fork`-only; ConPTY hosting and `schtasks` persistence
(`.research/empirical/windows-leg.md`).

**Not verified:** the composed stack end-to-end — nobody has yet run the middle layer *and*
agentirc *and* the state driver together on one Windows host. Double-ConPTY nesting remains
untested by anyone. L3 across reboot is untested.

**Superseded:** the ecosystem map's *"Windows is an explicit refusal at the daemon layer"*
overstated a `fork`-only guard as an ecosystem-wide platform refusal.
