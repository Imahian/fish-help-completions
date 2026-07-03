# help2fish — startup config: locate the engine and register the auto-generate hook.
# https://github.com/Imahian/fish-help-completions

# Path to the Python engine (install.fish copies it here).
if not set -q __help2fish_py
    set -gx __help2fish_py "$HOME/.local/share/help2fish/help2fish.py"
end

# Where we remember commands we already tried, so a failed parse is not retried
# every session.
if not set -q __help2fish_state
    set -gx __help2fish_state "$HOME/.cache/help2fish/tried"
end

# Opt-out: `set -U __help2fish_auto 0` to disable background auto-generation.
if not set -q __help2fish_auto
    set -g __help2fish_auto 1
end

function __help2fish_hook --on-event fish_preexec --description "Auto-generate completions for new commands"
    test "$__help2fish_auto" = 1; or return
    test -f "$__help2fish_py"; or return
    type -q python3; or return

    set -l cmd (string split -- ' ' $argv[1])[1]
    test -n "$cmd"; or return
    # ignore paths, variable assignments, builtins
    string match -q -- '*/*' $cmd; and return
    string match -q -- '*=*' $cmd; and return
    command -sq -- $cmd; or return

    # already have a completion?
    test -f ~/.config/fish/completions/$cmd.fish; and return

    # already tried this command before?
    set -l marker $__help2fish_state/$cmd
    test -f $marker; and return
    mkdir -p $__help2fish_state
    touch $marker

    # if a man page exists, fish already auto-generates from it — leave it alone
    if type -q man; and man -w $cmd >/dev/null 2>&1
        return
    end

    # generate in a detached process so it survives the terminal closing
    if type -q setsid
        setsid -f python3 "$__help2fish_py" -- $cmd >/dev/null 2>&1 &
    else
        python3 "$__help2fish_py" -- $cmd >/dev/null 2>&1 &
    end
    disown 2>/dev/null
end
