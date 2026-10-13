#!/usr/bin/env bash
#
# ============================================================================
#  demo_hook.sh -- module2-git lab, end-to-end hook demonstration (bash)
# ============================================================================
#  The bash twin of demo_hook.ps1: it builds a throwaway git repository in the
#  system temp directory, installs the lab's native hooks, and then drives the
#  three scenarios that are the whole point of the module:
#
#    SCENARIO 1  src/ staged, no test staged   -> the commit MUST be blocked
#    SCENARIO 2  src/ + a test staged          -> the commit MUST succeed
#    SCENARIO 3  git commit --no-verify        -> the gate CAN be skipped
#                                                 (the honest limitation)
#    EXTRA       non-ASCII path                -> why the checker asks for -z
#
#  Every scenario ends in assertions; a PASS/FAIL table is printed at the end
#  and the script's own exit code is 0 only when every assertion held.
#
#  HOW TO RUN (Git for Windows / Linux / macOS):
#      bash demo_hook.sh
#      bash demo_hook.sh --keep          # leave the temp repo behind to poke at
#      bash demo_hook.sh --python /path/to/python3
#
#  Inside Git Bash the hook files are copied verbatim, so this script doubles as
#  a check that hooks/pre-commit really is runnable bash. It needs no third-party
#  package: git, a POSIX shell, and a Python 3 interpreter that is not the
#  Microsoft Store stub.
#
#  EXIT CODES (this script)
#      0  every assertion held
#      1  at least one assertion FAILED -- the demonstration did not prove itself
#      2  a precondition was not met (lab file missing, no git, no Python 3)
#
#  NOTE ON ENCODING: this file is pure ASCII on purpose. The only non-ASCII path
#  it needs (the Chinese filename in the EXTRA scenario) is built from octal
#  escapes with printf, so the script survives a GBK console or a C locale.
# ============================================================================

set -u
# NOT `set -e`: a failing `git commit` is a *wanted* outcome here, and every
# command's status is inspected by hand instead of aborting the script.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

CHECKER="$SCRIPT_DIR/scripts/check_tests_touched.py"
HOOK_PRECOMMIT="$SCRIPT_DIR/hooks/pre-commit"
HOOK_PCM="$SCRIPT_DIR/hooks/prepare-commit-msg"

PASS=0
FAIL=0
ROWS=()
LAST_OUT=""
LAST_CODE=0
PY_CMD=()
KEEP=0
PYTHON_OVERRIDE="${PYTHON:-}"

# ---------------------------------------------------------------------------
# output helpers
# ---------------------------------------------------------------------------
banner() {
    printf '\n%s\n%s\n%s\n' \
        '==============================================================================' \
        "$*" \
        '=============================================================================='
}
note() { printf '  [i] %s\n' "$*"; }

# Collapse multi-line command output to one line for the summary table.
flatten() { printf '%s' "$1" | tr '\n' ' ' | sed -e 's/  */ /g' -e 's/^ //' -e 's/ $//'; }
short() {
    local s="$1" n="$2"
    if [ "${#s}" -le "$n" ]; then printf '%s' "$s"; else printf '%s...' "${s:0:$((n - 3))}"; fi
}
# Boolean phrasing helpers, so every assertion compares "true" or a plain value.
nz() { if [ "$1" -ne 0 ]; then printf 'true'; else printf 'false'; fi; }
z() { if [ "$1" -eq 0 ]; then printf 'true'; else printf 'false'; fi; }
# Fixed-string containment ("true"/"false") -- grep -F, never a glob or regex, so
# a needle like "src/\u4e2d\u6587.py" or "\344" cannot be reinterpreted.
contains() { if grep -Fq -- "$2" <<<"$1"; then printf 'true'; else printf 'false'; fi; }

assert_equal() { # SCENARIO ASSERTION EXPECTED ACTUAL
    local scenario="$1" name="$2" expected="$3" actual="$4" verdict
    if [ "$expected" = "$actual" ]; then
        PASS=$((PASS + 1)); verdict=PASS
    else
        FAIL=$((FAIL + 1)); verdict=FAIL
    fi
    if [ "$verdict" = PASS ]; then
        printf '  [PASS] %s\n' "$name"
    else
        printf '  [FAIL] %s\n         expected: %s\n         actual  : %s\n' "$name" "$expected" "$(flatten "$actual")"
    fi
    ROWS+=("$scenario|$name|$expected|$(flatten "$actual")|$verdict")
}

usage() {
    cat <<'EOF'
usage: demo_hook.sh [options]

  -k, --keep            leave the throwaway repository in place (prints its path)
  -p, --python PATH     use this Python 3 interpreter instead of searching PATH
  -h, --help            show this help and exit 0

Runs the module2-git hook demo: builds a temp repo, installs hooks/pre-commit and
hooks/prepare-commit-msg, then proves that a src/-only change is blocked, that
adding a test unblocks it, and that --no-verify bypasses the gate.
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        -k | --keep) KEEP=1; shift ;;
        -p | --python)
            PYTHON_OVERRIDE="${2:-}"
            if [ -z "$PYTHON_OVERRIDE" ]; then
                printf 'ERROR: --python needs a path\n' >&2
                exit 2
            fi
            shift 2
            ;;
        -h | --help) usage; exit 0 ;;
        *)
            printf 'ERROR: unknown option: %s\n' "$1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

# ---------------------------------------------------------------------------
# git wrappers
#   gitrun -> merged output (for DISPLAY), status in LAST_CODE
#   gitout -> stdout only   (for ASSERTIONS; a status check must never see the
#             warning text git sometimes writes to stderr)
# ---------------------------------------------------------------------------
gitrun() {
    local repo="$1"; shift
    LAST_OUT="$(git -C "$repo" "$@" 2>&1)"
    LAST_CODE=$?
}
gitout() {
    local repo="$1"; shift
    LAST_OUT="$(git -C "$repo" "$@" 2>/dev/null)"
    LAST_CODE=$?
}
# This machine's git emits a harmless "unable to access '.../.config/git/ignore':
# Permission denied" warning on every invocation. It is filtered from *displayed*
# output only; assertions read stdout, where it never appears.
filter_noise() { grep -v -F -e 'unable to access' -e '.config/git/ignore' || true; }

show_git() { # LABEL
    printf '  > %s\n    exit code: %s\n' "$1" "$LAST_CODE"
    local shown
    shown="$(printf '%s' "$LAST_OUT" | filter_noise)"
    if [ -n "$shown" ]; then
        while IFS= read -r line; do printf '    | %s\n' "$line"; done <<<"$shown"
    else
        printf '    | <no output>\n'
    fi
}

# ---------------------------------------------------------------------------
# preconditions
# ---------------------------------------------------------------------------
banner 'module2-git / demo_hook.sh -- native git hooks, no third-party tools'
note "lab directory : $SCRIPT_DIR"
note "shell         : ${BASH_VERSION}"

missing=0
for f in "$CHECKER" "$HOOK_PRECOMMIT" "$HOOK_PCM"; do
    if [ ! -f "$f" ]; then
        printf 'ERROR: missing lab file: %s\n' "$f" >&2
        missing=1
    fi
done
if [ "$missing" -ne 0 ]; then
    printf 'ERROR: run this script from the module2-git lab (its own directory layout is required).\n' >&2
    exit 2
fi

if ! command -v git >/dev/null 2>&1; then
    printf 'ERROR: git not found on PATH\n' >&2
    exit 2
fi
gitrun . '--version'
note "git           : $LAST_OUT"

# Python 3 discovery. The Store alias `python3.exe` in
# %LOCALAPPDATA%\Microsoft\WindowsApps answers `command -v` and then opens the
# Microsoft Store, so it is rejected by path before the version probe.
probe_ok() { # EXE [extra args...]
    local exe="$1"; shift
    "$exe" "$@" -c 'import sys; raise SystemExit(0 if sys.version_info[0] >= 3 else 1)' >/dev/null 2>&1
}
find_python() {
    local cand exe
    for cand in "$PYTHON_OVERRIDE" python3 python py; do
        [ -n "$cand" ] || continue
        exe="$(command -v "$cand" 2>/dev/null)" || continue
        case "$exe" in
            *Microsoft/WindowsApps* | *Microsoft\\WindowsApps*) continue ;;
        esac
        if [ "$cand" = "py" ]; then
            if probe_ok "$exe" -3; then PY_CMD=("$exe" -3); return 0; fi
        else
            if probe_ok "$exe"; then PY_CMD=("$exe"); return 0; fi
        fi
    done
    return 1
}
if ! find_python; then
    printf 'ERROR: no usable Python 3 interpreter found (tried: %s python3 python py).\n' "${PYTHON_OVERRIDE:-<none>}" >&2
    printf '       Pass one explicitly: bash demo_hook.sh --python /path/to/python3\n' >&2
    exit 2
fi
note "python        : ${PY_CMD[*]}  ($("${PY_CMD[@]}" -c 'import sys; print(sys.version.split()[0])'))"
note "checker       : $CHECKER"

# ---------------------------------------------------------------------------
# throwaway repository
# ---------------------------------------------------------------------------
REPO="$(mktemp -d "${TMPDIR:-/tmp}/module2-git-demo-XXXXXX")" || {
    printf 'ERROR: mktemp -d failed\n' >&2
    exit 2
}

cleanup() {
    if [ "$KEEP" -eq 1 ]; then
        printf '\n[i] --keep given, temp repo left in place: %s\n' "$REPO"
        return
    fi
    case "$REPO" in
        */module2-git-demo-*)
            # Guarded delete: only ever remove the throwaway directory we made.
            # Leave it first, because on Windows a directory cannot be removed
            # while it is the current directory of a process.
            cd / 2>/dev/null || cd "$HOME" 2>/dev/null || true
            if rm -rf -- "$REPO"; then
                printf '[i] removed temp repo: %s\n' "$REPO"
            else
                printf '[!] could not remove %s (left behind)\n' "$REPO" >&2
            fi
            ;;
        *) printf '[!] refusing to delete %s (not a demo directory)\n' "$REPO" >&2 ;;
    esac
}
trap cleanup EXIT

note "temp repo     : $REPO"

# git >= 2.28 supports `init -b`; older ones need symbolic-ref on the unborn HEAD.
gitrun "$REPO" init -q -b feature/hooked
if [ "$LAST_CODE" -ne 0 ]; then
    gitrun "$REPO" init -q
    gitrun "$REPO" symbolic-ref HEAD refs/heads/feature/hooked
fi

# Deterministic config: an identity (otherwise commit refuses outright), no
# signing, no line-ending rewriting, and an explicit hooks path so a global
# core.hooksPath cannot silently redirect which hooks run.
gitrun "$REPO" config user.email 'lab@example.com'
gitrun "$REPO" config user.name 'Module2 Lab'
gitrun "$REPO" config commit.gpgsign false
gitrun "$REPO" config core.autocrlf false
# Worktree-relative on purpose. In Git Bash, $REPO is an msys path like
# /tmp/module2-git-demo-x, and `git config` stores its value VERBATIM: native
# git.exe would later read that POSIX path as C:/tmp/... and look for the hooks
# in a directory that does not exist. A relative value is resolved against the
# worktree root by git itself, so it is correct on every platform -- and a
# repo-local value still overrides a global core.hooksPath.
gitrun "$REPO" config core.hooksPath .git/hooks
gitout "$REPO" symbolic-ref --short HEAD
note "branch        : $LAST_OUT"

mkdir -p "$REPO/src" "$REPO/tests"
cat >"$REPO/src/app.py" <<'PY'
def add(a, b):
    return a + b
PY
cat >"$REPO/tests/test_app.py" <<'PY'
from src.app import add


def test_add():
    assert add(1, 2) == 3
PY
printf '%s\n' '__pycache__/' '*.pyc' >"$REPO/.gitignore"
note 'fixture       : src/app.py, tests/test_app.py, .gitignore'

# ---------------------------------------------------------------------------
# install the hooks
# ---------------------------------------------------------------------------
HOOKS_DIR="$REPO/.git/hooks"
cp -f "$HOOK_PRECOMMIT" "$HOOKS_DIR/pre-commit"
cp -f "$HOOK_PCM" "$HOOKS_DIR/prepare-commit-msg"

# On Linux/macOS this bit is what makes the hook runnable at all. On Windows it
# is accepted and ignored: NTFS has no POSIX execute bit and git for Windows
# decides whether a hook is runnable from its shebang / contents. `git
# update-index --chmod=+x` is the closest native equivalent and cannot help,
# because it only touches files tracked by the index and .git/hooks never is.
chmod +x "$HOOKS_DIR/pre-commit" "$HOOKS_DIR/prepare-commit-msg" 2>/dev/null || true
printf '  [i] chmod +x attempted (informational: Windows git keys off the shebang, not the mode bit)\n'
gitrun "$REPO" update-index --chmod=+x .git/hooks/pre-commit
printf '  [i] git update-index --chmod=+x .git/hooks/pre-commit -> exit %s: %s\n' "$LAST_CODE" "$(flatten "$LAST_OUT")"
note "installed hooks: $(cd "$HOOKS_DIR" && ls -1 | grep -v '\.sample$' | tr '\n' ' ')"

# The bash hook finds the checker relative to the repository (.git/hooks/,
# scripts/, lab/module2-git/scripts/). This throwaway repo has none of those
# paths, so point it at the lab copy through the environment variable the hook
# honours -- that is exactly what that override exists for. git passes its own
# environment through to hooks, so exported is all it takes.
export TESTS_TOUCHED_CHECKER="$CHECKER"

# ===========================================================================
# SCENARIO 1 -- src/ staged, no test staged -> commit must be blocked
# ===========================================================================
banner 'SCENARIO 1 / stage src/ only -> the commit MUST be blocked'

gitrun "$REPO" reset -q
cat >"$REPO/src/app.py" <<'PY'
def add(a, b):
    return a + b


def sub(a, b):
    return a - b
PY
gitrun "$REPO" add src/app.py
show_git 'git add src/app.py'

gitrun "$REPO" commit -m 'feat: change src only'
show_git 'git commit -m "feat: change src only"'

assert_equal 'S1' 'the commit is blocked (non-zero exit)' 'true' "$(nz "$LAST_CODE")"
gitrun "$REPO" rev-parse --verify -q HEAD
assert_equal 'S1' 'git really refused it (HEAD still unborn)' 'true' "$(nz "$LAST_CODE")"
gitout "$REPO" diff --cached --name-only
assert_equal 'S1' 'the staged change survived the abort' 'src/app.py' "$LAST_OUT"

# ===========================================================================
# SCENARIO 2 -- src/ + tests/ staged -> commit must succeed
# ===========================================================================
banner 'SCENARIO 2 / also stage a test -> the commit MUST succeed'

gitrun "$REPO" add tests/test_app.py
show_git 'git add tests/test_app.py'

gitrun "$REPO" commit -m 'feat: add app and test'
show_git 'git commit -m "feat: add app and test"'

assert_equal 'S2' 'the commit succeeded (exit 0)' '0' "$LAST_CODE"
gitrun "$REPO" rev-parse --verify -q HEAD
assert_equal 'S2' 'HEAD exists now' 'true' "$(z "$LAST_CODE")"
gitout "$REPO" rev-list --count HEAD
assert_equal 'S2' 'exactly one commit landed' '1' "$LAST_OUT"
gitout "$REPO" log -1 --pretty=format:%s
assert_equal 'S2' 'subject is untouched' 'feat: add app and test' "$LAST_OUT"
gitout "$REPO" log -1 --pretty=format:%B
assert_equal 'S2' 'prepare-commit-msg injected the branch' 'true' "$(contains "$LAST_OUT" '[branch feature/hooked]')"

# ===========================================================================
# SCENARIO 3 -- --no-verify bypasses the gate (honest limitation)
# ===========================================================================
banner 'SCENARIO 3 / git commit --no-verify -> the gate CAN be skipped'

gitrun "$REPO" reset -q
cat >"$REPO/src/app.py" <<'PY'
def add(a, b):
    return a + b


def sub(a, b):
    return a - b


def mul(a, b):
    return a * b
PY
gitrun "$REPO" add src/app.py
show_git 'git add src/app.py'

gitrun "$REPO" commit --no-verify -m 'chore: bypass the hook'
show_git 'git commit --no-verify -m "chore: bypass the hook"'

assert_equal 'S3' 'the bypassed commit succeeded' '0' "$LAST_CODE"
gitout "$REPO" rev-list --count HEAD
assert_equal 'S3' 'two commits now exist' '2' "$LAST_OUT"
gitout "$REPO" show --name-only --pretty=format: HEAD
assert_equal 'S3' 'it landed with no test change at all' 'src/app.py' "$LAST_OUT"
gitout "$REPO" log -1 --pretty=format:%B
assert_equal 'S3' '--no-verify does NOT skip prepare-commit-msg' 'true' "$(contains "$LAST_OUT" '[branch ')"

# Re-proof: the identical staged state is blocked the moment the flag is gone.
note 're-proof: undo that commit (keep the index) and commit again without the flag'
gitrun "$REPO" reset --soft HEAD~1
show_git 'git reset --soft HEAD~1'
gitrun "$REPO" commit -m 'chore: same state, no bypass'
show_git 'git commit -m "chore: same state, no bypass"'
assert_equal 'S3' 'same state WITHOUT the flag is blocked' 'true' "$(nz "$LAST_CODE")"
gitout "$REPO" rev-list --count HEAD
assert_equal 'S3' 'still only one commit (nothing slid through)' '1' "$LAST_OUT"
gitrun "$REPO" commit --no-verify -m 'chore: bypass again'
show_git 'git commit --no-verify (again)'

# ===========================================================================
# EXTRA -- why -z: git C-quotes non-ASCII paths unless you ask for -z
# ===========================================================================
banner 'EXTRA / why the checker uses `git diff --cached --name-only -z`'

# Built from octal escapes on purpose: this file stays pure ASCII, so neither a
# GBK console nor a C locale can mangle the source itself. printf turns these
# three UTF-8 bytes into the character U+4E2D, which is exactly what a
# Windows/UTF-8 filesystem stores in the filename.
cn="$(printf '\344\270\255\346\226\207')"
cn_rel="src/${cn}.py"
printf '# non-ASCII filename\n' >"$REPO/$cn_rel"
gitrun "$REPO" add "$cn_rel"
show_git "git add src/<utf8-3-byte-name>.py  (U+4E2D U+6587)"

gitout "$REPO" diff --cached --name-only
plain="$LAST_OUT"
printf '  > git diff --cached --name-only  (default: C-quoted, unreadable)\n'
while IFS= read -r line; do printf '    | %s\n' "$line"; done <<<"$plain"

json_out="$(cd "$REPO" && "${PY_CMD[@]}" "$CHECKER" --json 2>/dev/null)"
json_code=$?
printf '  > check_tests_touched.py --json  (with -z: raw UTF-8, escaped for the payload)\n'
printf '    | %s\n' "$json_out"

assert_equal 'X' 'plain git output is C-quoted (the trap)' 'true' "$(contains "$plain" '\344')"
assert_equal 'X' 'the checker sees the real path, not the C-quoted one' 'true' "$(contains "$json_out" 'src/\u4e2d\u6587.py')"
assert_equal 'X' 'and it still blocks: src staged, no test' '1' "$json_code"

# ===========================================================================
# summary
# ===========================================================================
banner 'SUMMARY'
printf '%-4s %-40s %-14s %-30s %-7s\n' 'SC' 'ASSERTION' 'EXPECTED' 'ACTUAL' 'RESULT'
printf '%s\n' '--------------------------------------------------------------------------------------------------'
for row in ${ROWS[@]+"${ROWS[@]}"}; do
    IFS='|' read -r r_sc r_name r_exp r_act r_verdict <<<"$row"
    printf '%-4s %-40s %-14s %-30s %-7s\n' \
        "$(short "$r_sc" 4)" "$(short "$r_name" 40)" "$(short "$r_exp" 14)" "$(short "$r_act" 30)" "$r_verdict"
done
printf '\nRESULT: %d passed, %d failed  (flavour: bash)\n' "$PASS" "$FAIL"
if [ "$FAIL" -eq 0 ]; then
    printf 'ALL ASSERTIONS PASSED\n'
    exit 0
fi
printf 'SOME ASSERTIONS FAILED\n'
exit 1
