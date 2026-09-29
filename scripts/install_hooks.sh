#!/usr/bin/env bash
# Install the git hooks of this repository (git does not version .git/hooks); safe to re-run.
#   pre-commit  hygiene of the staged changes (audit files, personal paths, assistant mentions) and ruff
#   commit-msg  the subject's form "[TAG] one sentence" (docs/decisions/0005-commits.md), no forbidden mentions
here="$(cd "$(dirname "$0")" && pwd)"
root="$(dirname "$here")"
hooks="$(git -C "$root" rev-parse --git-path hooks)"
case "$hooks" in /*) ;; *) hooks="$root/$hooks" ;; esac
mkdir -p "$hooks"
cat > "$hooks/pre-commit" <<'HOOK'
#!/usr/bin/env bash
root="$(git rev-parse --show-toplevel)"
python3 "$root/scripts/hygiene.py" --staged || exit 1
ruff="$root/.venv-$(uname -s)-$(uname -m)/bin/ruff"
files=$(git diff --cached --name-only --diff-filter=ACMR -- '*.py')
if [ -n "$files" ]; then
  if [ -x "$ruff" ]; then (cd "$root" && "$ruff" check $files) || exit 1
  else echo "pre-commit: no ruff in the environment (scripts/setup_env.sh --dev): lint skipped" >&2; fi
fi
HOOK
cat > "$hooks/commit-msg" <<'HOOK'
#!/usr/bin/env bash
python3 "$(git rev-parse --show-toplevel)/scripts/hygiene.py" --message "$1"
HOOK
chmod +x "$hooks/pre-commit" "$hooks/commit-msg"
echo "installed: $hooks/pre-commit, $hooks/commit-msg"
