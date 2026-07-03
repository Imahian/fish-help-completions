function help2fish --description "Generate fish completions for any command by parsing its --help"
    if not set -q __help2fish_py; or not test -f "$__help2fish_py"
        echo "help2fish: engine not found ($__help2fish_py). Re-run install.fish." >&2
        return 1
    end
    if not type -q python3
        echo "help2fish: python3 is required." >&2
        return 1
    end

    argparse 'h/help' 'a/all' 'd/depth=' 'f/force' 's/stdout' -- $argv
    or return 1

    if set -q _flag_help; or test (count $argv) -eq 0
        echo "Usage: help2fish [options] <command>..."
        echo ""
        echo "Generate fish completions from a command's --help output, recursively"
        echo "(subcommands and their per-instance flags)."
        echo ""
        echo "Options:"
        echo "  -d, --depth N   subcommand recursion depth (default 2)"
        echo "  -f, --force     overwrite an existing completion file"
        echo "  -s, --stdout    print to stdout instead of writing the file"
        echo "  -a, --all       regenerate for every command already in \$PATH that"
        echo "                  lacks a completion and a man page (slow)"
        echo "  -h, --help      show this help"
        echo ""
        echo "Examples:"
        echo "  help2fish sqlmap"
        echo "  help2fish --depth 3 docker"
        echo "  help2fish --stdout gobuster | less"
        return 0
    end

    set -l opts
    set -q _flag_depth; and set -a opts --depth $_flag_depth
    set -q _flag_force; and set -a opts --force
    set -q _flag_stdout; and set -a opts --stdout

    if set -q _flag_all
        __help2fish_all
        return
    end

    for cmd in $argv
        python3 "$__help2fish_py" $opts -- $cmd
    end
end

function __help2fish_all --description "Generate completions for all uncovered commands in PATH"
    set -l count 0
    for dir in $PATH
        test -d $dir; or continue
        for bin in $dir/*
            test -x "$bin"; and test -f "$bin"; or continue
            set -l name (basename $bin)
            test -f ~/.config/fish/completions/$name.fish; and continue
            if type -q man; and man -w $name >/dev/null 2>&1
                continue
            end
            python3 "$__help2fish_py" -- $name >/dev/null 2>&1
            and set count (math $count + 1)
        end
    end
    echo "help2fish: generated $count completion file(s)."
end
