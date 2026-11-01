#!/bin/sh
# One-shot: restart the engine to load new code only at a safe moment — when nothing is running, or when a run
# is parked at a budget pause (then continue that run right after the restart).
API=http://127.0.0.1:8770
while :; do
  state=$(curl -s "$API/api/dashboard" | python3 -c '
import json,sys
d=json.load(sys.stdin); r=d.get("running") or []
if not r: print("idle")
else:
    x=r[0]; b=x.get("budget") or {}
    print("budget %s %s" % (x["id"], x["project"]) if x.get("paused") and (b.get("ratio") or 0) >= 1 else "busy")
' 2>/dev/null)
  case "$state" in
    idle) systemctl --user restart jarvis; exit 0 ;;
    budget*) set -- $state; systemctl --user restart jarvis; sleep 6
       curl -s -X POST -H 'X-Jarvis: 1' -H 'Content-Type: application/json' -d "{\"id\":\"$2\",\"project\":\"$3\"}" "$API/api/continue"; exit 0 ;;
  esac
  sleep 15
done
