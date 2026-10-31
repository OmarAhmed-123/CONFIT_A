#!/usr/bin/env bash
# Real screen-reader pass for the wardrobe stylist (P4).
# Starts Xvfb + a D-Bus session + AT-SPI registry + GNOME Orca (debug log on),
# then runs scripts/qa/stylist_a11y_audit.mjs in HEADED Firefox so Orca sees a
# real accessible application; finally extracts Orca's SPEECH OUTPUT lines.
# Usage: scripts/qa/orca_stylist_session.sh <app_url> <api_url> <out_json>
set -euo pipefail
APP=${1:-http://127.0.0.1:4173}; API=${2:-http://127.0.0.1:8000}; OUT=${3:-docs/qa/stylist_orca_report.json}
export DISPLAY=:99
for p in at-spi-bus-launcher at-spi2-registryd "dbus-daemon --syslog" "dbus-daemon --config-file=/usr/share/defaults/at-spi2" "^orca"; do pkill -f "$p" 2>/dev/null || true; done
pgrep -x Xvfb >/dev/null || { Xvfb :99 -screen 0 1280x900x24 -nolisten tcp >/tmp/xvfb.log 2>&1 & }
XVFB=$(pgrep -x Xvfb | head -1); sleep 1
eval "$(dbus-launch --sh-syntax)"; export DBUS_SESSION_BUS_ADDRESS
/usr/libexec/at-spi-bus-launcher --launch-immediately >/tmp/atspi.log 2>&1 &
sleep 1
export GTK_MODULES=gail:atk-bridge GNOME_ACCESSIBILITY=1 MOZ_ACCESSIBILITY_AT_SPI=1 NO_AT_BRIDGE=0
# Tell the a11y bus an AT is present (no dconf in CI containers, so set it over D-Bus directly)
dbus-send --session --print-reply --dest=org.a11y.Bus /org/a11y/bus org.freedesktop.DBus.Properties.Set string:org.a11y.Status string:IsEnabled variant:boolean:true >/dev/null 2>&1 || true
export GTK_MODULES=gail:atk-bridge
rm -rf /tmp/orca-debug; mkdir -p /tmp/orca-debug
# speech goes to speech-dispatcher → espeak-ng; we don't need audio, we need the transcript
( cd /tmp/orca-debug && orca --replace --debug --no-setup >/tmp/orca.out 2>&1 ) &
ORCA=$!; sleep 4
echo "orca pid $ORCA alive: $(kill -0 $ORCA && echo yes || echo no)"
FF=$(ls -d ~/.cache/ms-playwright/firefox-*/firefox/firefox | head -1)
set +e
(cd frontend && GNOME_ACCESSIBILITY=1 MOZ_ACCESSIBILITY_AT_SPI=1 node scripts/stylist_a11y_audit.mjs --app "$APP" --api "$API" --browser firefox --exe "$FF" --headed 1 --out "../${OUT%.json}_firefox.json")
RC=$?
set -e
sleep 2
kill $ORCA 2>/dev/null || true; sleep 1
python3 - "$OUT" <<'PY'
import glob, json, re, sys
out = sys.argv[1]
lines = []
for f in sorted(glob.glob('/tmp/orca-debug/debug*.out')):
    for ln in open(f, errors='replace'):
        m = re.search(r"SPEECH OUTPUT: '(.*)'", ln)
        if m: lines.append(m.group(1))
        m2 = re.search(r"BRAILLE LINE:\s+'(.*)'", ln)
        if m2: lines.append('[braille] ' + m2.group(1))
json.dump({"screen_reader": "GNOME Orca 48.1", "display": "Xvfb :99", "browser": "Firefox (Playwright build), headed, AT-SPI",
           "speech_output_count": len(lines), "speech_output": lines[:600]}, open(out, 'w'), ensure_ascii=False, indent=2)
print("orca speech lines:", len(lines), "→", out)
PY
kill $XVFB 2>/dev/null || true
exit $RC
