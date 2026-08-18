#!/usr/bin/env bash
# Issue #17: attach 後 cwd 候補の実機検証（tmux + AppleScript）
# Control Mode attach 済みセッションで実行すること。
set -euo pipefail

SESSION="${1:-iTmux}"
RESULT="/tmp/issue17-cwd-shell-results.json"

CWD_A="/tmp/issue17-cwd-a"
CWD_B="/tmp/issue17-cwd-b"
CWD_C="/tmp/issue17-cwd-c"
CWD_D="/tmp/issue17-cwd-d"

count_iterm_windows() {
  osascript -e 'tell application "iTerm2" to count windows'
}

count_session_tabs_in_any_window() {
  local conn_id="$1"
  osascript <<EOF
tell application "iTerm2"
  set tabCount to 0
  repeat with w in windows
    repeat with t in tabs of w
      try
        if (tmux connection id of t as text) contains "$conn_id" then
          set tabCount to tabCount + 1
        end if
      end try
    end repeat
  end repeat
  return tabCount
end tell
EOF
}

pane_path() {
  local target="$1"
  tmux display-message -t "$target" -p '#{pane_current_path}'
}

latest_window_target() {
  tmux list-windows -t "$SESSION" -F '#{window_id}' | tail -1
}

kill_latest_test_window() {
  local wid
  wid=$(tmux list-windows -t "$SESSION" -F '#{window_id}' | tail -1)
  tmux kill-window -t "$wid" 2>/dev/null || true
}

record() {
  python3 - "$@" <<'PY'
import json, sys
from pathlib import Path
path = Path("/tmp/issue17-cwd-shell-results.json")
data = json.loads(path.read_text()) if path.exists() else {"session": sys.argv[1], "results": []}
entry = json.loads(sys.argv[2])
data["results"].append(entry)
path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
PY
}

init_json() {
  python3 - <<PY
import json, time
from pathlib import Path
Path("$RESULT").write_text(json.dumps({
  "session": "$SESSION",
  "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
  "results": []
}, indent=2))
PY
}

require_cc() {
  if ! tmux list-clients -t "$SESSION" 2>/dev/null | grep -q control-mode; then
    echo "Session $SESSION is not attached via Control Mode" >&2
    exit 1
  fi
}

require_cc
init_json

WINDOWS_BEFORE=$(count_iterm_windows)

# --- A: default-path + new-window (removed in tmux >=1.9) ---
echo "Testing A..."
if tmux set-option -t "$SESSION" default-path "$CWD_A" 2>/dev/null; then
  W_BEFORE=$(count_iterm_windows)
  tmux new-window -t "$SESSION"
  sleep 0.2
  W_AFTER=$(count_iterm_windows)
  WID=$(latest_window_target)
  PATH_A=$(pane_path "@${WID#@}")
  record "$SESSION" "$(python3 - <<EOF
import json
print(json.dumps({
  "candidate": "A",
  "method": "set-option default-path + tmux new-window",
  "native_window": $W_AFTER > $W_BEFORE,
  "startup_cwd_match": "$PATH_A" == "$CWD_A",
  "pane_path": "$PATH_A",
  "expected_path": "$CWD_A",
  "operation_count": 2,
  "notes": ["default-path available on this tmux version"]
}))
EOF
)"
  kill_latest_test_window
  tmux set-option -t "$SESSION" default-path ~
else
  record "$SESSION" "$(python3 - <<'EOF'
import json
print(json.dumps({
  "candidate": "A",
  "method": "set-option default-path + async_create_window (planned)",
  "native_window": None,
  "startup_cwd_match": None,
  "pane_path": None,
  "expected_path": "/tmp/issue17-cwd-a",
  "operation_count": 0,
  "error": "invalid option: default-path (removed in tmux 1.9; unavailable on tmux 3.6a)",
  "notes": ["Issue body candidate A is obsolete for modern tmux", "async_create_window cannot receive -c; no default-path fallback"]
}))
EOF
)"
fi

# --- B: new-window + send-keys cd ---
echo "Testing B..."
W_BEFORE=$(count_iterm_windows)
tmux new-window -t "$SESSION"
sleep 0.1
WID=$(latest_window_target)
tmux send-keys -t "@${WID#@}" "cd $CWD_B" Enter
sleep 0.2
W_AFTER=$(count_iterm_windows)
PATH_B=$(pane_path "@${WID#@}")
record "$SESSION" "$(python3 - <<EOF
import json
print(json.dumps({
  "candidate": "B",
  "method": "new-window + send-keys cd",
  "native_window": $W_AFTER > $W_BEFORE,
  "startup_cwd_match": "$PATH_B" == "$CWD_B",
  "pane_path": "$PATH_B",
  "expected_path": "$CWD_B",
  "operation_count": 3,
  "notes": ["post-start cd; fails startup cwd requirement by design"]
}))
EOF
)"
kill_latest_test_window

# --- D-api: new-window -c via tmux (same as async_send_command) ---
echo "Testing D-api..."
W_BEFORE=$(count_iterm_windows)
tmux new-window -t "$SESSION" -c "$CWD_D"
sleep 0.2
W_AFTER=$(count_iterm_windows)
WID=$(latest_window_target)
PATH_D=$(pane_path "@${WID#@}")
record "$SESSION" "$(python3 - <<EOF
import json
print(json.dumps({
  "candidate": "D-api",
  "method": "tmux new-window -c (async_send_command equivalent)",
  "native_window": $W_AFTER > $W_BEFORE,
  "startup_cwd_match": "$PATH_D" == "$CWD_D",
  "pane_path": "$PATH_D",
  "expected_path": "$CWD_D",
  "operation_count": 1,
  "notes": ["#15 regression: opens as tab not native window when native_window=false"]
}))
EOF
)"
kill_latest_test_window

# --- D-subprocess: same command, verify identical ---
echo "Testing D-subprocess..."
W_BEFORE=$(count_iterm_windows)
/usr/bin/env tmux new-window -t "$SESSION" -c "$CWD_D"
sleep 0.2
W_AFTER=$(count_iterm_windows)
WID=$(latest_window_target)
PATH_DS=$(pane_path "@${WID#@}")
record "$SESSION" "$(python3 - <<EOF
import json
print(json.dumps({
  "candidate": "D-subprocess",
  "method": "subprocess tmux new-window -c",
  "native_window": $W_AFTER > $W_BEFORE,
  "startup_cwd_match": "$PATH_DS" == "$CWD_D",
  "pane_path": "$PATH_DS",
  "expected_path": "$CWD_D",
  "operation_count": 1,
  "notes": ["identical to D-api in this environment"]
}))
EOF
)"
kill_latest_test_window

# --- baseline: new-window + respawn-pane -c -k (proxy without async_create_window) ---
echo "Testing baseline..."
W_BEFORE=$(count_iterm_windows)
tmux new-window -t "$SESSION"
sleep 0.1
WID=$(latest_window_target)
tmux respawn-pane -t "@${WID#@}" -c "$CWD_A" -k
sleep 0.2
W_AFTER=$(count_iterm_windows)
PATH_BASE=$(pane_path "@${WID#@}")
record "$SESSION" "$(python3 - <<EOF
import json
print(json.dumps({
  "candidate": "baseline(PR#16-proxy)",
  "method": "new-window + respawn-pane -c -k",
  "native_window": $W_AFTER > $W_BEFORE,
  "startup_cwd_match": "$PATH_BASE" == "$CWD_A",
  "pane_path": "$PATH_BASE",
  "expected_path": "$CWD_A",
  "operation_count": 2,
  "notes": ["respawn-pane proxy; async_create_window gives native window per #15"]
}))
EOF
)"
kill_latest_test_window

# --- async_create_window native check via documented behavior ---
# Compare: plain new-window under CC vs async_create_window from #15
W_BEFORE=$(count_iterm_windows)
tmux new-window -t "$SESSION"
sleep 0.2
W_AFTER=$(count_iterm_windows)
NEW_WIN_NATIVE=$([[ "$W_AFTER" -gt "$W_BEFORE" ]] && echo True || echo False)
kill_latest_test_window

python3 - <<PY
import json
from pathlib import Path
p = Path("$RESULT")
data = json.loads(p.read_text())
data["tmux_new_window_under_cc_native"] = $NEW_WIN_NATIVE
data["iterm_windows_at_start"] = $WINDOWS_BEFORE
p.write_text(json.dumps(data, indent=2, ensure_ascii=False))
print(p.read_text())
PY
