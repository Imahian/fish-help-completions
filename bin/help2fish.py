#!/usr/bin/env python3
"""
help2fish — generate fish shell completions for ANY command by parsing its
`--help` output, recursively, including subcommands and their per-instance flags.

Works with common CLI frameworks (cobra, urfave/cli, click, argparse, docker-style,
git-style) via heuristic parsing. No man page required.

Usage:
    help2fish.py <command> [--depth N] [--out DIR] [--stdout] [--force]

Exit codes:
    0 ok  1 usage  2 no help output  3 nothing parseable
"""
import argparse
import os
import re
import subprocess
import sys

# ---------------------------------------------------------------------------
# Help-text acquisition
# ---------------------------------------------------------------------------

HELP_FLAGS = ("--help", "-h", "help")
MAX_HELP_BYTES = 400_000
HELP_TIMEOUT = 5


def _safe_env():
    """Environment that discourages a probed binary from doing anything but
    printing help. Crucially, DISPLAY / WAYLAND_DISPLAY are removed so GUI
    programs cannot open a window when they ignore --help."""
    env = {
        k: v for k, v in os.environ.items()
        if k not in ("DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY",
                     "DBUS_SESSION_BUS_ADDRESS")
    }
    env.update(GIT_PAGER="cat", PAGER="cat", NO_COLOR="1", TERM="dumb")
    return env


def _probe_cwd():
    """An isolated directory to run probes in, so a binary that dumps files on
    --help (config, caches, .fit/.wav/.json artifacts) pollutes here and not the
    user's working directory."""
    d = os.path.expanduser("~/.cache/help2fish/probe")
    try:
        os.makedirs(d, exist_ok=True)
        return d
    except OSError:
        return None


def get_help(argv):
    """Run `argv --help` (and fallbacks); return combined stdout+stderr or None.

    Runs each probe in its own process group with stdin closed, no display, and
    an isolated cwd, and kills the whole group on timeout — so a binary that
    ignores --help and tries to launch (a GUI, a REPL, a daemon) cannot linger,
    open a window, or litter the user's directory.
    """
    env = _safe_env()
    cwd = _probe_cwd()
    for flag in HELP_FLAGS:
        try:
            p = subprocess.Popen(
                argv + [flag],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                cwd=cwd,
                start_new_session=True,  # own process group
            )
        except OSError:
            continue
        try:
            out, err = p.communicate(timeout=HELP_TIMEOUT)
        except subprocess.TimeoutExpired:
            _kill_group(p)
            p.communicate()
            continue
        text = (out or "") + ("\n" + err if err else "")
        text = strip_ansi(text)
        if text.strip() and len(text) <= MAX_HELP_BYTES:
            return text
    return None


def _kill_group(p):
    import signal
    try:
        os.killpg(os.getpgid(p.pid), signal.SIGKILL)
    except (OSError, ProcessLookupError):
        try:
            p.kill()
        except OSError:
            pass


ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def strip_ansi(s):
    return ANSI.sub("", s)


# ---------------------------------------------------------------------------
# Flag parsing
# ---------------------------------------------------------------------------

# A line that starts an option entry: leading whitespace, then a dash-option,
# then (after >=2 spaces, or a tab, or end-of-line) an optional description.
OPT_START = re.compile(r"^[ \t]{1,10}(-[^\s].*?)(?:  +|\t+|$)(.*)$")

# One option token inside the option column, e.g. "-w", "--wordlist", possibly
# followed by a metavar: "--url value", "--url=URL", "-u URL", "--n <int>".
# The lookbehind (?<![\w-]) prevents matching *inside* a long flag name, so
# "--no-canonicalize-headers" stays whole instead of splitting at each hyphen.
OPT_TOKEN = re.compile(
    r"(?<![\w-])"
    r"(--?[A-Za-z0-9][A-Za-z0-9-]*)"                       # the flag
    r"(?:[ =](<[^>]+>|\[[^\]]+\]|[A-Za-z0-9_.:/|-]+))?"    # optional metavar
)


def parse_flags(text):
    """Return list of dicts: {shorts, longs, desc, takes_arg}."""
    entries = []
    cur = None
    for raw in text.splitlines():
        line = raw.rstrip()
        m = OPT_START.match(line)
        if m and looks_like_option(m.group(1)):
            optcol, desc = m.group(1), m.group(2)
            shorts, longs, takes_arg = split_option_column(optcol)
            if not shorts and not longs:
                cur = None
                continue
            cur = {
                "shorts": shorts,
                "longs": longs,
                "desc": desc.strip(),
                "takes_arg": takes_arg,
            }
            entries.append(cur)
            continue
        # continuation of a wrapped description
        if cur is not None and re.match(r"^[ \t]{2,}\S", line) and not line.lstrip().startswith("-"):
            cur["desc"] = (cur["desc"] + " " + line.strip()).strip()
        elif not line.strip():
            cur = None
    # dedupe
    seen = set()
    out = []
    for e in entries:
        key = (tuple(e["shorts"]), tuple(e["longs"]))
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


def looks_like_option(optcol):
    # First token must be a real flag, not e.g. "-- some prose"
    return bool(re.match(r"^--?[A-Za-z0-9]", optcol.strip()))


def split_option_column(optcol):
    """Parse the option column into (shorts, longs, takes_arg).

    Handles urfave repetition markers like:
        --headers value, -H value [ --headers value, -H value ]
    by cutting at the first '[' that introduces a repetition block.
    """
    # cut trailing repetition/hint block  "[ ... ]" that repeats the option
    optcol = re.split(r"\s\[\s*--", optcol, maxsplit=1)[0]
    shorts, longs = [], []
    takes_arg = False
    for mm in OPT_TOKEN.finditer(optcol):
        flag, metavar = mm.group(1), mm.group(2)
        if metavar is not None:
            takes_arg = True
        if flag.startswith("--"):
            longs.append(flag[2:])
        elif len(flag) == 2:
            shorts.append(flag[1:])
        else:
            # e.g. "-hh" (multi-char single-dash) -> old-style long
            longs.append(("OLD", flag[1:]))
    return shorts, longs, takes_arg


# ---------------------------------------------------------------------------
# Subcommand parsing
# ---------------------------------------------------------------------------

SUBCMD_HEADERS = re.compile(
    r"^\s*("
    r"available commands|commands|subcommands|management commands|"
    r"core commands|common commands|"
    r"positional arguments"
    r")\s*:?\s*$",
    re.IGNORECASE,
)
# git-style: "These are common Git commands used in various situations:"
GITSTYLE_HEADER = re.compile(r"^\s*these are .*\bcommands\b", re.IGNORECASE)

# a subcommand entry:  "  dir        Uses directory enumeration mode"
SUBCMD_ENTRY = re.compile(
    r"^[ \t]{2,8}([a-z][a-z0-9][a-z0-9:_-]*)(?:,\s*[a-z][\w-]*)?[ \t]{2,}(\S.*)$"
)

# argparse "{init,add,commit,...}" positional block
ARGPARSE_CHOICES = re.compile(r"\{([a-z0-9][a-z0-9,_-]{2,})\}")

STOP_SUBCMDS = {"help", "h", "version", "completion", "completions"}

# Col-0 headers that mean "the command list is over" — used to bound the region
# that follows a commands header (which may itself contain grouped sub-headers,
# as git's `--help` does).
TERMINATOR_HEADER = re.compile(
    r"^("
    r"options|flags|global options|global flags|arguments|args|"
    r"examples?|environment.*|see ?also|reporting bugs|report bugs.*|"
    r"authors?|copyright|notes?|description|usage|synopsis|version"
    r")\b.*:?\s*$",
    re.IGNORECASE,
)


def parse_subcommands(text):
    """Return dict {name: description}."""
    subs = {}
    lines = text.splitlines()

    # 1) header-delimited region. Once we enter a commands section we keep
    #    collecting entries until a terminator header (col 0) or EOF. Blank
    #    lines and grouped sub-headers (git style) do NOT end the region.
    in_section = False
    for raw in lines:
        line = raw.rstrip()
        if not in_section:
            if SUBCMD_HEADERS.match(line) or GITSTYLE_HEADER.match(line):
                in_section = True
            continue
        # inside the commands region
        if line and re.match(r"^\S", line) and TERMINATOR_HEADER.match(line.strip()):
            in_section = False
            continue
        m = SUBCMD_ENTRY.match(line)
        if m:
            name, desc = m.group(1), m.group(2).strip()
            if name.lower() not in STOP_SUBCMDS:
                subs.setdefault(name, desc)
        elif re.match(r"^[ \t]{2,}[a-z][\w:-]*\s*$", line):
            # bare subcommand name, no description
            name = line.strip()
            if name.lower() not in STOP_SUBCMDS:
                subs.setdefault(name, "")

    # 2) argparse choices block  "{init,add,commit}"  (fallback)
    if len(subs) < 2:
        m = ARGPARSE_CHOICES.search(text)
        if m:
            for name in m.group(1).split(","):
                name = name.strip()
                if name and name.lower() not in STOP_SUBCMDS:
                    subs.setdefault(name, "")

    return subs


# ---------------------------------------------------------------------------
# Recursive tree build
# ---------------------------------------------------------------------------


def build_tree(argv, depth, seen_paths):
    key = tuple(argv)
    if key in seen_paths:
        return None
    seen_paths.add(key)
    help_text = get_help(argv)
    if not help_text:
        return {"flags": [], "subs": {}, "children": {}}
    flags = parse_flags(help_text)
    subs = parse_subcommands(help_text) if depth > 0 else {}
    children = {}
    for name in list(subs)[:60]:
        child = build_tree(argv + [name], depth - 1, seen_paths)
        if child is not None:
            children[name] = child
    return {"flags": flags, "subs": subs, "children": children}


# ---------------------------------------------------------------------------
# Fish emission
# ---------------------------------------------------------------------------


def esc(s):
    return s.replace("\\", "\\\\").replace("'", r"\'")


def clip(s, n=200):
    s = " ".join(s.split())
    return s[: n - 1] + "…" if len(s) > n else s


def flag_complete(cmd, flag, condition):
    parts = [f"complete -c {cmd}"]
    if condition:
        parts.append(f"-n {condition}")
    for s in flag["shorts"]:
        parts.append(f"-s {s}")
    for l in flag["longs"]:
        if isinstance(l, tuple):  # old-style single-dash long
            parts.append(f"-o {l[1]}")
        else:
            parts.append(f"-l {l}")
    if flag["takes_arg"]:
        parts.append("-r")
    if flag["desc"]:
        parts.append(f"-d '{esc(clip(flag['desc']))}'")
    return " ".join(parts)


STAMP = "auto-generated by help2fish"


def emit(cmd, tree):
    out = [
        f"# fish completions for `{cmd}` — {STAMP}",
        f"# https://github.com/Imahian/fish-help-completions",
        "",
    ]

    def walk(node, path):
        # path = list of subcommand names from root (excludes cmd itself)
        cond_seen = fish_condition(path, list(node["subs"].keys()))
        # subcommands offered at this level
        for name, desc in node["subs"].items():
            c = flag_offer_subcommand(cmd, path, name, desc, node["subs"])
            out.append(c)
        # flags valid at this level
        for fl in node["flags"]:
            out.append(flag_complete(cmd, fl, cond_seen))
        # recurse
        for name, child in node["children"].items():
            walk(child, path + [name])

    walk(tree, [])
    return "\n".join(out) + "\n"


def fish_condition(path, child_names):
    """Condition selecting the context where `path` subcommands are active."""
    if not path:
        # root-level flags: only before any subcommand chosen? No — globals are
        # usually valid everywhere, so leave unconditional.
        return ""
    clauses = [f"__fish_seen_subcommand_from {p}" for p in path]
    return '"' + "; and ".join(clauses) + '"'


def flag_offer_subcommand(cmd, path, name, desc, siblings):
    parts = [f"complete -c {cmd} -f"]
    if not path:
        parts.append("-n __fish_use_subcommand")
    else:
        clauses = [f"__fish_seen_subcommand_from {p}" for p in path]
        # not yet descended into any child of this node
        parts.append('-n "' + "; and ".join(clauses) + '"')
    parts.append(f"-a {name}")
    if desc:
        parts.append(f"-d '{esc(clip(desc))}'")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def default_outdir():
    return os.path.expanduser("~/.config/fish/completions")


def is_ours(path):
    """True if the completion file at `path` was generated by help2fish."""
    try:
        with open(path, "r", errors="ignore") as f:
            return STAMP in f.read(400)
    except OSError:
        return False


def has_man(cmd):
    try:
        r = subprocess.run(["man", "-w", cmd], capture_output=True, timeout=5)
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


class Result:
    """Outcome of generating one command."""
    def __init__(self, name, status, flags=0, subs=0, path=None, detail=""):
        self.name, self.status = name, status
        self.flags, self.subs = flags, subs
        self.path, self.detail = path, detail


def generate_one(cmd, depth, outdir, force):
    """Generate a completion for one command. Returns a Result.

    status ∈ created | updated | vendor | man | nohelp | empty | error
    """
    if "/" in cmd:
        cmd = os.path.basename(cmd)
    outpath = os.path.join(outdir, f"{cmd}.fish")

    exists = os.path.exists(outpath)
    if exists and not force:
        return Result(cmd, "vendor" if not is_ours(outpath) else "have", path=outpath)
    if exists and force and not is_ours(outpath):
        # never clobber handwritten / vendor completions
        return Result(cmd, "vendor", path=outpath)

    if get_help([cmd]) is None:
        return Result(cmd, "nohelp", detail="no --help/-h output")

    try:
        tree = build_tree([cmd], depth, set())
    except Exception as e:  # never let one bad command abort a batch
        return Result(cmd, "error", detail=str(e))

    if not tree["flags"] and not tree["subs"]:
        return Result(cmd, "empty", detail="help present but nothing parseable")

    content = emit(cmd, tree)
    nf, ns = count_flags(tree), count_subs(tree)
    try:
        os.makedirs(outdir, exist_ok=True)
        with open(outpath, "w") as f:
            f.write(content)
    except OSError as e:
        return Result(cmd, "error", detail=str(e))
    return Result(cmd, "updated" if exists else "created", nf, ns, outpath)


def iter_path_commands():
    seen = set()
    for d in os.environ.get("PATH", "").split(os.pathsep):
        if not d or not os.path.isdir(d):
            continue
        try:
            entries = os.listdir(d)
        except OSError:
            continue
        for name in sorted(entries):
            if name in seen:
                continue
            p = os.path.join(d, name)
            if os.path.isfile(p) and os.access(p, os.X_OK):
                seen.add(name)
                yield name


def run_all(depth, outdir, force, quiet=False):
    """Generate completions for every command in PATH; print a report."""
    sys.stderr.write(
        "help2fish --all: probing every command in $PATH with --help.\n"
        "Display is disabled and hung probes are killed, but this is still a\n"
        "heavy, best-effort sweep. The on-demand hook is the recommended path.\n\n"
    )
    buckets = {k: [] for k in
               ("created", "updated", "have", "vendor", "man", "nohelp", "empty", "error")}
    for name in iter_path_commands():
        outpath = os.path.join(outdir, f"{name}.fish")
        if not os.path.exists(outpath) and has_man(name):
            buckets["man"].append(Result(name, "man"))
            continue
        r = generate_one(name, depth, outdir, force)
        buckets[r.status].append(r)
        if not quiet and r.status in ("created", "updated"):
            print(f"  + {name}: {r.flags} flags, {r.subs} subcommands")

    # conflict / debug log
    logdir = os.path.expanduser("~/.cache/help2fish")
    os.makedirs(logdir, exist_ok=True)
    logpath = os.path.join(logdir, "report.txt")
    with open(logpath, "w") as f:
        for status in ("empty", "nohelp", "error"):
            for r in buckets[status]:
                f.write(f"{status}\t{r.name}\t{r.detail}\n")

    tf = sum(r.flags for r in buckets["created"] + buckets["updated"])
    ts = sum(r.subs for r in buckets["created"] + buckets["updated"])

    print()
    print("help2fish --all report")
    print("──────────────────────")
    print(f"  created         {len(buckets['created']):>5}")
    print(f"  updated         {len(buckets['updated']):>5}")
    print(f"  already ours    {len(buckets['have']):>5}")
    print(f"  vendor/manual   {len(buckets['vendor']):>5}   (left untouched)")
    print(f"  from man page   {len(buckets['man']):>5}   (fish handles these)")
    print(f"  no --help       {len(buckets['nohelp']):>5}")
    print(f"  unparseable     {len(buckets['empty']):>5}   ← conflicts to debug")
    print(f"  errors          {len(buckets['error']):>5}")
    print("──────────────────────")
    print(f"  total flags generated:        {tf}")
    print(f"  total subcommands generated:  {ts}")
    if buckets["empty"] or buckets["nohelp"] or buckets["error"]:
        print(f"\n  conflict/debug log: {logpath}")
        sample = (buckets["empty"] + buckets["error"])[:10]
        if sample:
            print("  unparseable/error (sample):")
            for r in sample:
                print(f"    - {r.name}: {r.detail}")


def main():
    ap = argparse.ArgumentParser(prog="help2fish", add_help=True)
    ap.add_argument("command", nargs="?", help="command to generate for (omit with --all)")
    ap.add_argument("--all", action="store_true", help="generate for every command in $PATH")
    ap.add_argument("--depth", type=int, default=2, help="subcommand recursion depth (default 2)")
    ap.add_argument("--out", default=None, help="output dir (default ~/.config/fish/completions)")
    ap.add_argument("--stdout", action="store_true", help="print to stdout instead of writing file")
    ap.add_argument("--force", action="store_true", help="overwrite existing help2fish files")
    ap.add_argument("--quiet", action="store_true", help="suppress per-command lines in --all")
    args = ap.parse_args()

    outdir = args.out or default_outdir()

    if args.all:
        run_all(args.depth, outdir, args.force, quiet=args.quiet)
        return

    if not args.command:
        ap.error("a command is required (or pass --all)")

    cmd = args.command
    if "/" in cmd:
        cmd = os.path.basename(cmd)

    if args.stdout:
        if get_help([cmd]) is None:
            print(f"[help2fish] {cmd}: no --help/-h output", file=sys.stderr)
            sys.exit(2)
        tree = build_tree([cmd], args.depth, set())
        if not tree["flags"] and not tree["subs"]:
            print(f"[help2fish] {cmd}: nothing parseable", file=sys.stderr)
            sys.exit(3)
        sys.stdout.write(emit(cmd, tree))
        return

    r = generate_one(cmd, args.depth, outdir, args.force)
    if r.status in ("created", "updated"):
        print(f"[help2fish] {cmd}: {r.flags} flags, {r.subs} subcommands ({r.status}) -> {r.path}")
    elif r.status in ("vendor", "have"):
        print(f"[help2fish] {cmd}: completion already exists ({r.status}); use --force", file=sys.stderr)
    elif r.status == "nohelp":
        print(f"[help2fish] {cmd}: no --help/-h output", file=sys.stderr); sys.exit(2)
    elif r.status == "empty":
        print(f"[help2fish] {cmd}: nothing parseable", file=sys.stderr); sys.exit(3)
    else:
        print(f"[help2fish] {cmd}: {r.detail}", file=sys.stderr); sys.exit(1)


def count_flags(node):
    return len(node["flags"]) + sum(count_flags(c) for c in node["children"].values())


def count_subs(node):
    return len(node["subs"]) + sum(count_subs(c) for c in node["children"].values())


if __name__ == "__main__":
    main()
