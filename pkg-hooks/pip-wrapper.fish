# Optional pip / pipx integration for help2fish.
# pip has no global post-install hook, so we wrap the command: snapshot the
# script dirs before/after an install and generate completions for anything new.
#
# To use: copy this file to ~/.config/fish/conf.d/help2fish-pip.fish

function __help2fish_after_pip_install
    set -l dirs ~/.local/bin
    test -n "$VIRTUAL_ENV"; and set -a dirs $VIRTUAL_ENV/bin
    for d in $dirs
        test -d $d; or continue
        for bin in $d/*
            test -x "$bin"; and test -f "$bin"; or continue
            set -l name (basename $bin)
            test -f ~/.config/fish/completions/$name.fish; and continue
            help2fish $name >/dev/null 2>&1
            and echo "help2fish: added completions for $name"
        end
    end
end

function pip --wraps pip --description "pip + help2fish"
    command pip $argv
    set -l st $status
    if contains -- install $argv
        __help2fish_after_pip_install
    end
    return $st
end

function pipx --wraps pipx --description "pipx + help2fish"
    command pipx $argv
    set -l st $status
    if contains -- install $argv
        __help2fish_after_pip_install
    end
    return $st
end
