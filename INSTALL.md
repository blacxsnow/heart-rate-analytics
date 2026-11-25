# Installation

This guide installs the acquisition daemon, the local dashboard, and the
read-only analysis CLI on Linux. The recommended path is a single user-level
script; no root privileges are required after the system packages are present.

## Requirements

- Linux with BlueZ and a working Bluetooth adapter.
- Python **3.11+** with `venv`/`pip`.
- `systemd --user` and `loginctl` for the boot-persistent services.
- A Huawei Band 9 with **Settings → HR Data Broadcasts** available.
- No Huawei account, phone, pairing, or bonding is required for the standard
  heart-rate path.

Install system packages first:

```bash
# Fedora
sudo dnf install bluez bluez-tools python3-pip

# Debian / Ubuntu
sudo apt install bluez python3-venv python3-pip

# Arch
sudo pacman -S bluez bluez-utils python-pip
```

Check the adapter:

```bash
bluetoothctl show
rfkill list bluetooth
```

`Powered: yes` and `Soft blocked: no` are required.

## One-command install

```bash
git clone git@github.com:blacxsnow/heart-rate-analytics.git
cd heart-rate-analytics
./install.sh
```

The installer:

1. checks Linux, Python 3.11+, `bluetoothctl`, and `systemd --user`;
2. creates `.venv` in the repository (unless `--no-venv`);
3. installs the `api` and `analysis` extras;
4. creates `~/.local/share/band9`;
5. installs and enables the two user units;
6. restarts them so a re-run picks up new code;
7. enables lingering so both services start at boot without a login.

It does **not** use `sudo`, flash firmware, pair/bond the band, or modify raw
data.

## Check first / options

```bash
./install.sh --check          # prerequisites and planned actions only
./install.sh --no-services    # Python environment only, no systemd units
./install.sh --no-start       # install/enable units but do not start them now
./install.sh --no-venv        # install into the selected interpreter
./install.sh --python /usr/bin/python3.12
./install.sh --venv /path/to/venv
```

Environment equivalents: `PYTHON`, `BAND9_VENV`, `BAND9_DATA_DIR`.

## Start the band

On the band:

1. Open **Settings → HR Data Broadcasts**.
2. Start the broadcast and keep the screen awake for the first connection.
3. Keep the band within range of the PC.
4. Do not connect the phone to the band at the same time (the Band 9 normally
   accepts one active BLE link on the normal endpoint).

Open the dashboard:

<http://127.0.0.1:8787>

The connection card should become `connected`, with a live BPM and a sampling
interval near 1 s. If the band is on but broadcast is off, the dashboard shows
that explicitly.

## Services

```bash
systemctl --user status huawei-acquisition.service huawei-web.service
systemctl --user restart huawei-acquisition.service
systemctl --user restart huawei-web.service
journalctl --user -u huawei-acquisition.service -f
journalctl --user -u huawei-web.service -f
```

The two services are independent: restarting or stopping the web unit does not
stop acquisition. Acquisition has `Restart=always` and survives crashes/BLE
losses; see `docs/17_acquisition_system.md`.

Lingering is enabled by the installer. Check it with:

```bash
loginctl show-user "$USER" -p Linger
```

If lingering failed, ask an administrator for:

```bash
sudo loginctl enable-linger "$USER"
```

## Analysis

```bash
source .venv/bin/activate
band9-analyze --db ~/.local/share/band9/acquisition.sqlite3 --out reports/analysis
```

Or directly:

```bash
.venv/bin/python -m fitness_band.analysis \
  --db ~/.local/share/band9/acquisition.sqlite3 \
  --out reports/analysis
```

The analysis CLI is read-only with respect to acquisition records.

The dashboard includes the same read-only analytics as sections below the live
monitor: summary, hourly/daily tables, distribution, HR bands, sleep statistics,
circadian heatmap and provisional rolling baselines. See
`docs/21_statistical_analytics.md`.

## Manual install (equivalent)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[api,analysis]'
PYTHON="$(command -v python)" bash services/install-user-services.sh
```

For a CLI-only install:

```bash
pip install -e '.[analysis]'
band9 doctor
band9 endpoints
band9 hr --duration 60
```

## Updating

```bash
git pull
./install.sh
```

The installer reinstalls the editable package and restarts the user services.
The database is preserved at `~/.local/share/band9`.

## Uninstall

```bash
systemctl --user disable --now huawei-acquisition.service huawei-web.service
rm -f ~/.config/systemd/user/huawei-acquisition.service
rm -f ~/.config/systemd/user/huawei-web.service
systemctl --user daemon-reload
```

Optionally remove `.venv` and the data directory. The data directory contains
your only copy of the collected heart-rate history, so back it up first:

```bash
ls -lh ~/.local/share/band9
```

## Troubleshooting

### `HR broadcast endpoint not found`

- Start **Settings → HR Data Broadcasts** on the band.
- Wake the band and check its battery.
- Keep the band within range; disconnect the phone from it.
- The daemon releases stale BlueZ links and retries automatically.
- Use **Reconnect now** on the dashboard; if the adapter is wedged, use **Reset
  Bluetooth adapter** (it skips the reset if another Bluetooth device is
  connected).

### `adapter unavailable` / `adapter powered off`

- Check `bluetoothctl show` and `rfkill list bluetooth`.
- Power the adapter on; the daemon retries without restarting.

### Dashboard is not reachable

```bash
systemctl --user status huawei-web.service
journalctl --user -u huawei-web.service -n 80 --no-pager
curl -sS http://127.0.0.1:8787/healthz
```

The dashboard binds to `127.0.0.1:8787` only. To change it, edit the web unit
and add `--port <port>`; exposing it beyond loopback requires a firewall and
authentication in front, because the API has no authentication.

### First run has no data

The dashboard shows available data only. Start HR Data Broadcast, wait for a
few samples, then refresh. Statistics warn about small samples and low coverage
rather than inventing values.

## Privacy and data

- The database is local: `~/.local/share/band9/acquisition.sqlite3`.
- `data/`, `reports/`, `captures/raw/`, `captures/live/`, `captures/android/`,
  and databases are gitignored.
- Never commit MAC addresses, device IDs, serial numbers, keys, tokens, raw
  health data, or unredacted captures. See `SECURITY.md`.

## License

MIT. See `LICENSE`.
