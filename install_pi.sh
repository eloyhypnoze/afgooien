#!/bin/bash
# Afgooien installeren op een Raspberry Pi (Raspberry Pi OS met bureaublad, 64-bit).
#
#   bash install_pi.sh                      alles: dienst + Chromium op volledig scherm bij het opstarten
#   bash install_pi.sh --geen-scherm        alleen de server (scherm = laptop/tablet/tv via het netwerk)
#   bash install_pi.sh --geen-kiosk         wel een venster bij het opstarten, maar niet volledig scherm
#   bash install_pi.sh --lite               Raspberry Pi OS Lite (zonder bureaublad): lichtste en snelste,
#                                           alleen een kiosk-schil (cage) + browser, meer kracht voor Autodarts
#   bash install_pi.sh --autodarts off      zonder Autodarts (pijlen aanklikken)
#   bash install_pi.sh --geen-turbo         processor niet vast op volle snelheid zetten
#   bash install_pi.sh --geen-stem          natuurlijke stem (Piper) niet installeren
#   bash install_pi.sh --verwijder          dienst en autostart weer weghalen (je gegevens blijven)
#
# Draai dit in de map waar je Afgooien hebt uitgepakt. Je gegevens (spelers, scorebord) staan in
# ~/.local/share/afgooien en blijven bewaard als je later een nieuwe versie installeert.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ME="$(id -un)"
PORT=8080
AUTODARTS="http://localhost:3180"
SCREEN=1
KIOSK=1
REMOVE=0
LITE=0
TURBO=1
PIPER=1
DATA="${XDG_DATA_HOME:-$HOME/.local/share}/afgooien"
SUDO="${SUDO-sudo}"                 # SUDO="" voor testen zonder root
SYSTEMD_DIR="${SYSTEMD_DIR:-/etc/systemd/system}"
AUTOSTART_DIR="${AUTOSTART_DIR:-$HOME/.config/autostart}"
PAM_DIR="${PAM_DIR:-/etc/pam.d}"

while [ $# -gt 0 ]; do
  case "$1" in
    --geen-scherm) SCREEN=0 ;;
    --geen-kiosk) KIOSK=0 ;;
    --autodarts) AUTODARTS="$2"; shift ;;
    --port) PORT="$2"; shift ;;
    --verwijder) REMOVE=1 ;;
    --lite) LITE=1 ;;
    --geen-turbo) TURBO=0 ;;
    --geen-stem) PIPER=0 ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *) echo "Onbekende optie: $1"; exit 1 ;;
  esac
  shift
done

say() { printf '\n\033[1;35m▶ %s\033[0m\n' "$1"; }

if [ "$REMOVE" = 1 ]; then
  say "Afgooien verwijderen uit het opstarten"
  $SUDO systemctl disable --now afgooien.service afgooien-kiosk.service afgooien-snelheid.service 2>/dev/null || true
  $SUDO rm -f "$SYSTEMD_DIR/afgooien.service" "$SYSTEMD_DIR/afgooien-kiosk.service" "$SYSTEMD_DIR/afgooien-snelheid.service" "$PAM_DIR/afgooien-kiosk"
  $SUDO systemctl enable getty@tty1.service 2>/dev/null || true
  $SUDO rm -f /etc/sudoers.d/afgooien
  rm -f "$AUTOSTART_DIR/afgooien.desktop"
  $SUDO systemctl daemon-reload 2>/dev/null || true
  echo "Klaar. Je gegevens in ~/.local/share/afgooien zijn niet verwijderd."
  exit 0
fi

say "Python controleren"
if ! command -v python3 >/dev/null; then
  $SUDO apt-get update && $SUDO apt-get install -y python3
fi
python3 - <<'PY'
import sys
if sys.version_info < (3, 9):
    sys.exit("Afgooien heeft Python 3.9 of nieuwer nodig (gebruik een recente Raspberry Pi OS).")
print("Python", sys.version.split()[0], "OK")
PY

if [ "$SCREEN" = 1 ]; then
  say "Chromium en stem installeren"
  PKGS="speech-dispatcher espeak-ng"
  [ "$LITE" = 1 ] && PKGS="$PKGS cage pipewire pipewire-pulse wireplumber fonts-dejavu-core"
  PKGS="$PKGS fonts-noto-color-emoji"          # anders geen 🏆 🤖 enz. op het scherm
  if ! command -v chromium-browser >/dev/null && ! command -v chromium >/dev/null; then
    if apt-cache show chromium >/dev/null 2>&1; then PKGS="$PKGS chromium"; else PKGS="$PKGS chromium-browser"; fi
  fi
  $SUDO apt-get update
  # shellcheck disable=SC2086
  $SUDO apt-get install -y $PKGS
fi

if [ "$PIPER" = 1 ]; then
  say "Natuurlijke stem installeren (Piper: Nederlandse en Engelse mannenstem, werkt zonder internet)"
  mkdir -p "$DATA/stemmen"
  case "$(uname -m)" in
    aarch64|arm64) PARCH=aarch64 ;; armv7l) PARCH=armv7l ;; x86_64) PARCH=x86_64 ;; *) PARCH="" ;;
  esac
  if [ -n "$PARCH" ] && [ ! -x "$DATA/piper/piper" ]; then
    curl -fsSL "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_${PARCH}.tar.gz" \
      | tar xz -C "$DATA" || echo "Piper downloaden mislukt (geen internet?)"
  fi
  get_voice() {   # naam, map op huggingface, reserve-bestand op github
    local name="$1" hf="https://huggingface.co/rhasspy/piper-voices/resolve/main/$2/$1" gh="$3" dst="$DATA/stemmen"
    if [ -s "$dst/$name.onnx" ] && [ -s "$dst/$name.onnx.json" ]; then echo "Stem $name is er al."; return 0; fi
    echo "Stem $name downloaden (ongeveer 60 MB)..."
    if curl -fsSL -o "$dst/$name.onnx.tmp" "$hf.onnx" && curl -fsSL -o "$dst/$name.onnx.json" "$hf.onnx.json"; then
      mv "$dst/$name.onnx.tmp" "$dst/$name.onnx"; return 0
    fi
    rm -f "$dst/$name.onnx.tmp" "$dst/$name.onnx.json"
    local t; t="$(mktemp -d)"
    if curl -fsSL "https://github.com/rhasspy/piper/releases/download/v0.0.2/$gh.tar.gz" | tar xz -C "$t"; then
      local m; m="$(ls "$t"/*.onnx 2>/dev/null | head -1)"
      if [ -n "$m" ]; then mv "$m" "$dst/$name.onnx"; mv "$m.json" "$dst/$name.onnx.json"; fi
    else
      echo "Stem $name downloaden mislukt."
    fi
    rm -rf "$t"
  }
  get_voice nl_BE-rdh-medium nl/nl_BE/rdh/medium voice-nl-rdh-medium
  get_voice en_US-ryan-medium en/en_US/ryan/medium voice-en-us-ryan-medium
  rm -f /tmp/afgooien-stemtest.wav
  if [ -x "$DATA/piper/piper" ] && echo '{"text": "Honderd tachtig!", "output_file": "/tmp/afgooien-stemtest.wav"}' \
       | "$DATA/piper/piper" --model "$DATA/stemmen/nl_BE-rdh-medium.onnx" --json-input --quiet >/dev/null 2>&1 \
       && [ -s /tmp/afgooien-stemtest.wav ]; then
    echo "Natuurlijke stem werkt."
  else
    echo "Natuurlijke stem werkt (nog) niet; Afgooien gebruikt dan de browserstem."
  fi
fi

say "Aan/uit-knop in het spel toestaan (alleen uitzetten en herstarten)"
CTL="$(command -v systemctl || echo /usr/bin/systemctl)"
TMP="$(mktemp)"
printf '%s ALL=(root) NOPASSWD: %s poweroff, %s reboot\n' "$ME" "$CTL" "$CTL" > "$TMP"
if [ -n "$SUDO" ] && $SUDO visudo -cf "$TMP" >/dev/null 2>&1; then
  $SUDO install -m 440 "$TMP" /etc/sudoers.d/afgooien
else
  echo "Overgeslagen (geen sudo/visudo)."
fi
rm -f "$TMP"

say "Afgooien als dienst instellen (start automatisch, ook na een stroomstoring)"
TMP="$(mktemp)"
cat > "$TMP" <<EOF
[Unit]
Description=Afgooien dartspel
After=network-online.target autodarts.service
Wants=network-online.target

[Service]
User=$ME
WorkingDirectory=$DIR
ExecStart=$(command -v python3) $DIR/run.py --port $PORT --autodarts $AUTODARTS --power
Restart=on-failure
RestartSec=3
# iets voorrang boven andere programma's (Autodarts krijgt nog steeds ruim genoeg)
Nice=-2
CPUWeight=200

[Install]
WantedBy=multi-user.target
EOF
$SUDO install -m 644 "$TMP" "$SYSTEMD_DIR/afgooien.service"
rm -f "$TMP"
$SUDO systemctl daemon-reload
$SUDO systemctl enable --now afgooien.service
$SUDO systemctl restart afgooien.service      # nieuwe versie meteen actief (het scherm laadt dan vanzelf opnieuw)

if [ "$SCREEN" = 1 ] && [ "$LITE" = 1 ]; then
  say "Kiosk instellen: bij het opstarten direct het speelscherm, zonder bureaublad"
  $SUDO usermod -aG video,render,input,audio "$ME" || true
  TMP="$(mktemp)"
  printf 'auth required pam_unix.so nullok\naccount required pam_unix.so\nsession required pam_unix.so\nsession required pam_systemd.so\n' > "$TMP"
  $SUDO install -m 644 "$TMP" "$PAM_DIR/afgooien-kiosk"
  cat > "$TMP" <<EOF
[Unit]
Description=Afgooien speelscherm (kiosk)
After=systemd-user-sessions.service afgooien.service dbus.socket systemd-logind.service getty@tty1.service
Wants=dbus.socket systemd-logind.service
Conflicts=getty@tty1.service
ConditionPathExists=/dev/tty1

[Service]
User=$ME
WorkingDirectory=$DIR
ExecStart=$(command -v cage || echo /usr/bin/cage) -s -- $(command -v python3) $DIR/launcher.py --alleen-venster --kiosk --port $PORT
Restart=always
RestartSec=2
# het scherm krijgt voorrang, zodat het vloeiend blijft terwijl Autodarts de camera's verwerkt
Nice=-5
CPUWeight=400
UtmpIdentifier=tty1
UtmpMode=user
TTYPath=/dev/tty1
TTYReset=yes
TTYVHangup=yes
TTYVTDisallocate=yes
StandardInput=tty-fail
StandardOutput=journal
PAMName=afgooien-kiosk

[Install]
WantedBy=graphical.target
EOF
  $SUDO install -m 644 "$TMP" "$SYSTEMD_DIR/afgooien-kiosk.service"
  rm -f "$TMP"
  $SUDO systemctl daemon-reload
  $SUDO systemctl disable getty@tty1.service 2>/dev/null || true
  $SUDO systemctl set-default graphical.target
  $SUDO systemctl enable afgooien-kiosk.service
elif [ "$SCREEN" = 1 ]; then
  say "Speelscherm openen bij het opstarten"
  mkdir -p "$AUTOSTART_DIR"
  OPTS="--alleen-venster --port $PORT"
  [ "$KIOSK" = 1 ] && OPTS="$OPTS --kiosk"
  cat > "$AUTOSTART_DIR/afgooien.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Afgooien
Comment=Speelscherm van Afgooien
Exec=$(command -v python3) $DIR/launcher.py $OPTS
Icon=$DIR/web/icon.png
Terminal=false
X-GNOME-Autostart-enabled=true
EOF
  if command -v raspi-config >/dev/null; then
    say "Scherm niet laten uitgaan"
    $SUDO raspi-config nonint do_blanking 1 || true
  fi
fi

if [ "$TURBO" = 1 ] && ls /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor >/dev/null 2>&1; then
  say "Processor op volle snelheid houden (geen haperingen door op- en afschakelen)"
  TMP="$(mktemp)"
  cat > "$TMP" <<'EOF'
[Unit]
Description=Afgooien: processor op volle snelheid
After=multi-user.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/sh -c 'for g in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do echo performance > "$g"; done'

[Install]
WantedBy=multi-user.target
EOF
  $SUDO install -m 644 "$TMP" "$SYSTEMD_DIR/afgooien-snelheid.service"
  rm -f "$TMP"
  $SUDO systemctl daemon-reload
  $SUDO systemctl enable --now afgooien-snelheid.service || true
fi

# onthouden welke versie van dit script gedraaid heeft (de app meldt het als een update een nieuwe heeft)
mkdir -p "$DATA" && sha256sum "$DIR/install_pi.sh" > "$DATA/install_pi.sha256" || true

say "Controleren"
for _ in $(seq 1 40); do
  if python3 -c "import urllib.request,sys; urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://127.0.0.1:$PORT/api/state', timeout=1)" 2>/dev/null; then
    OK=1; break
  fi
  sleep 0.5
done
IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
if [ "${OK:-0}" = 1 ]; then
  echo "Afgooien draait!"
else
  echo "Afgooien reageert nog niet. Bekijk de melding met:  journalctl -u afgooien -f"
fi
echo
echo "  Op deze Pi:                 http://localhost:$PORT"
[ -n "$IP" ] && echo "  Op laptop/tablet/telefoon:  http://$IP:$PORT"
echo
echo "  Logboek bekijken:   journalctl -u afgooien -f"
echo "  Herstarten:         sudo systemctl restart afgooien"
[ "$SCREEN" = 1 ] && echo "  Bij de volgende herstart (sudo reboot) opent het speelscherm vanzelf."
if [ "$LITE" = 1 ]; then
  echo "  Naar een terminal: Ctrl+Alt+F2 (inloggen), terug naar het spel: Ctrl+Alt+F1."
elif [ "$SCREEN" = 1 ] && [ "$KIOSK" = 1 ]; then
  echo "  Volledig scherm sluiten: Alt+F4."
fi
exit 0
