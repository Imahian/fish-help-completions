# fish-help-completions (`help2fish`)

Generate [fish shell](https://fishshell.com) tab-completions for **any** command by
parsing its `--help` output — **recursively**, including subcommands and the flags
that belong to each subcommand.

Fish already auto-generates completions from `man` pages. But lots of tools ship no
man page (many pentest / CTF / Go / Rust / Python CLIs), so their flags never show up
on `Tab`. `help2fish` fills that gap: it reads `--help`, walks every subcommand, and
writes a proper `completions/<cmd>.fish` file with per-instance flag gating.

```
$ docker run -<Tab>
-a  Attach to STDIN, STDOUT or STDERR
-d  Run container in background and print container ID
-e  Set environment variables
...
$ docker -<Tab>          # only global flags here — run's flags are gated out
-D  Enable debug mode
-H  Daemon socket to connect to
...
```

## Install

Requires `python3` and `fish`.

```fish
git clone https://github.com/Imahian/fish-help-completions
cd fish-help-completions
./install.fish
```

One-liner:

```fish
curl -sL https://raw.githubusercontent.com/Imahian/fish-help-completions/main/install.fish | fish
```

Open a new shell afterwards (or `source ~/.config/fish/conf.d/help2fish.fish`).

## Usage

### Automatic (default)

Once installed, the first time you run a command that has **no completion and no man
page**, `help2fish` generates its completion in the background. Next time you press
`Tab`, the flags are there. Nothing to do.

Disable it with `set -U __help2fish_auto 0`.

### Manual

```fish
help2fish sqlmap              # write ~/.config/fish/completions/sqlmap.fish
help2fish --depth 3 docker    # recurse deeper into nested subcommands
help2fish --stdout gobuster   # preview without writing
help2fish --force git         # overwrite an existing file
help2fish --all               # generate for every uncovered command in $PATH (slow)
```

### Bulk: cover everything already installed

```fish
help2fish --all
```

Walks every command in `$PATH` and prints a report:

```
help2fish --all report
──────────────────────
  created            412
  updated              0
  already ours         3
  vendor/manual      120   (left untouched)
  from man page     1970   (fish handles these)
  no --help          380
  unparseable         64   ← conflicts to debug
  errors               0
──────────────────────
  total flags generated:        8123
  total subcommands generated:   642

  conflict/debug log: ~/.cache/help2fish/report.txt
```

- **created / updated** — new or refreshed help2fish files.
- **already ours** — a help2fish file already existed (pass `--force` to refresh).
- **vendor/manual** — a handwritten completion exists; never overwritten.
- **from man page** — fish already covers it; skipped.
- **no --help / unparseable** — logged to `~/.cache/help2fish/report.txt` so you
  can see exactly which tools need parser improvements.

`--all` runs `--help` on thousands of binaries, so it takes a while. Day to day you
don't need it — the background hook covers new commands as you use them.

### See what's covered (`--status`)

A **read-only** audit — it executes no binaries, it only inspects existing
completion files, man pages, and the conflict log:

```fish
help2fish --status          # counts only
help2fish --status --list   # also list the command names
```

```
help2fish --status  (read-only; no binaries executed)
────────────────────────────────────────────────────
  total commands in $PATH         5350
  with suggestions                3467
    ├─ by help2fish                127
    ├─ by vendor/handwritten        22
    └─ by man page (fish)         3318
  WITHOUT suggestions             1883
  known errors (from logs)           4
────────────────────────────────────────────────────
```

- **WITHOUT suggestions** — no completion and no man page; these are what
  `help2fish` can fill (run the command once, or `help2fish <name>`).
- **known errors** — commands whose `--help` gave nothing usable, recorded to
  `~/.cache/help2fish/report.txt` as you use them (name + reason), so you can see
  exactly what needs a parser fix. A later successful run clears its entry.

## Package-manager integration

Generate completions **at install time**, so the moment you install a tool its flags
are ready — with a summary printed at the end of the install.

> **Security note:** these hooks run `<newcommand> --help` right after installation
> (as root, for pacman/apt). Only enable them if you trust the packages you install.

### Arch (pacman, and therefore yay / paru)

```fish
./pkg-hooks/install-pacman-hook.fish
```

Installs an ALPM `PostTransaction` hook. After any `pacman -S` / `yay` / `paru`
install or upgrade, completions are generated into
`/usr/share/fish/vendor_completions.d` (shared by all users) and summarised:

```
──[ help2fish ]────────────────────────────────
  completions generated: 3 new, 0 updated  (214 flags, 7 subcommands)
  could not generate: 1  ← report these upstream
    - somebin: help present but nothing parseable
──────────────────────────────────────────────
```

Remove with `./pkg-hooks/install-pacman-hook.fish --remove`.

### Debian / Ubuntu (apt)

```fish
./pkg-hooks/install-apt-hook.fish
```

apt doesn't expose the changed binaries directly, so this reads the last
transaction from `/var/log/dpkg.log` and resolves package files with `dpkg -L`.
Best-effort but works for normal installs.

### pip / pipx

pip has no global hook. Copy the wrapper instead:

```fish
cp pkg-hooks/pip-wrapper.fish ~/.config/fish/conf.d/help2fish-pip.fish
```

It wraps `pip`/`pipx` and, after an `install`, generates completions for any new
executables in `~/.local/bin` (or the active virtualenv's `bin`).

## How it works

1. Runs `<cmd> --help` (falls back to `-h`, then `help`), strips ANSI colour.
2. Parses the **options** columns into short/long flags + whether each takes an
   argument. Handles hyphenated long flags (`--no-canonicalize-headers`), aliases
   (`--headers, -H`), and type-hint metavars (`--url value`, `--n=<int>`).
3. Detects **subcommands** from section headers (`Commands:`, `Available Commands:`,
   `COMMANDS:`, docker's *Management Commands*, git's *"These are common … commands"*)
   and from argparse `{a,b,c}` choice blocks.
4. Recurses into each subcommand (`<cmd> <sub> --help`) up to `--depth`.
5. Emits fish `complete` rules, gating each subcommand's flags behind
   `__fish_seen_subcommand_from <sub>` so they only appear in the right context.

It is heuristic, not magic: a tool whose `--help` is badly formatted (or which has no
`--help` at all) may yield partial or empty output. Handwritten completions and
`man`-derived ones always take precedence — `help2fish` never overwrites an existing
file unless you pass `--force`, and the auto-hook skips anything that has a man page.

## Compatibility

Tested against cobra / urfave-cli (Go), click / argparse (Python), and git- and
docker-style helps. Verified generators produce syntactically valid fish that sources
cleanly for: `git`, `docker`, `pip`, `nmap`, `hashcat`, `ffuf`, `gobuster`, `sqlmap`.

## Files it installs

| Path | Purpose |
|------|---------|
| `~/.local/share/help2fish/help2fish.py` | the parser engine |
| `~/.config/fish/functions/help2fish.fish` | the `help2fish` command |
| `~/.config/fish/conf.d/help2fish.fish`  | startup hook + config |
| `~/.config/fish/completions/*.fish`     | generated output |

Uninstall: delete those four and `~/.cache/help2fish/`.

## License

MIT
