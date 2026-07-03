#!/usr/bin/env fish
# help2fish installer — copies the engine + fish glue into place.
# Works with or without a plugin manager.
#
#   git clone https://github.com/Imahian/fish-help-completions
#   cd fish-help-completions
#   ./install.fish
#
# or one-liner:
#   curl -sL https://raw.githubusercontent.com/Imahian/fish-help-completions/main/install.fish | fish

set -l repo "https://github.com/Imahian/fish-help-completions"

# --- locate source files (repo dir if run locally, else clone to a tmp dir) ---
set -l src (status dirname)
if not test -f "$src/bin/help2fish.py"
    echo "help2fish: fetching from $repo ..."
    type -q git; or begin; echo "git is required for remote install"; exit 1; end
    set src (mktemp -d)
    git clone --depth 1 $repo $src; or begin; echo "clone failed"; exit 1; end
end

# --- checks ---
if not type -q python3
    echo "help2fish: python3 is required but was not found in PATH." >&2
    exit 1
end

set -l fishcfg $HOME/.config/fish
set -l engine_dir $HOME/.local/share/help2fish

mkdir -p $engine_dir $fishcfg/functions $fishcfg/conf.d $fishcfg/completions

cp "$src/bin/help2fish.py" $engine_dir/help2fish.py
chmod +x $engine_dir/help2fish.py
cp "$src/functions/help2fish.fish" $fishcfg/functions/
cp "$src/conf.d/help2fish.fish" $fishcfg/conf.d/

echo "help2fish: installed."
echo "  engine    -> $engine_dir/help2fish.py"
echo "  function  -> $fishcfg/functions/help2fish.fish"
echo "  hook      -> $fishcfg/conf.d/help2fish.fish"
echo ""
echo "Open a new shell (or run: source $fishcfg/conf.d/help2fish.fish)."
echo "Then either run a command once to auto-generate, or force one now:"
echo "    help2fish sqlmap"
