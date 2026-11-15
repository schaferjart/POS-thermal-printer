# CLAUDE.md

Thermal printer appliance: a Raspberry Pi with an 80 mm ESC/POS printer that is a
normal AirPrint printer on its WiFi, has a print page, and pulls print jobs from
a Supabase project. Python, no build step.

## Layout

- `device/` — everything that runs on the Pi
  - `printerd.py` — the one service: print page + local API on :9100, cloud job
    loop (claim_jobs every `poll_seconds`), font sync. Never opens USB: renders
    ESC/POS bytes with python-escpos and hands them to CUPS (`lp -d Thermal80 -o raw`).
  - `jobs.py` — templates: `markdown`, `image`, `slices`, `showmemo`. Each returns
    a Plan (images, one cut each, pause between). Cloud jobs and the page share it.
  - `md_renderer.py`, `image_printer.py`, `image_slicer.py`, `helpers.py` — rendering
  - `showmemo.py` — the ShowMeMo card (moved from schaferjart/showmemo-printer)
  - `index.html` — the print page; `config.yaml` — styles and defaults
  - `install.sh` (fresh Pi OS Lite -> printer), `update.sh` + `systemd/` units
- `renderer/` — cloud portrait renderer (FastAPI, Docker on Coolify). `POST /portrait`:
  photo + `X-Device-Token` -> wax transform (OpenRouter) -> MediaPipe face ->
  4 shared-height crops -> 1-bit 576 px PNGs. Checks the token with
  `printer.check_device` using the publishable key only. Settings in
  `renderer/config.yaml`; model failure is an error, never the plain photo.
  Test: `cd renderer && python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt && .venv/bin/python -m pytest -q tests`
- `supabase/migrations/` — schema `printer` (devices, jobs, fonts) + its functions
- `supabase/tests/printer_smoke.sql` — run in the SQL editor, rolls itself back

## Rules that bite

- **Cloud details never go in the repo.** URL + publishable key live in
  `/etc/printer/printer.env` on the device (`PRINTER_CLOUD_URL`, `PRINTER_CLOUD_KEY`).
- **Devices hold no Supabase secret key**, only the publishable key and their own token.
- **anon may only call functions.** No table grants; RLS on with no policies.
  Postgres grants EXECUTE to PUBLIC on new functions, and exposing a schema in the
  dashboard grants table rights: every migration that adds a function or table must
  revoke and re-grant explicitly (see the last block of `*_printer_fonts.sql`).
- Function params named like columns (`source`, `name`, `template`) need
  `#variable_conflict use_variable` and table-qualified columns.
- Migration file names must match the version Supabase recorded (`list_migrations`).
- PostgREST calls: `apikey` header only (sb_ keys are not JWTs), plus
  `Content-Profile: printer`.

## Run and test on a Mac

```bash
python3 -m venv .venv && .venv/bin/pip install pillow flask pyyaml qrcode python-escpos pytest
cd device && ../.venv/bin/python -m pytest -q tests
PRINTER_STATE_DIR=/tmp/p PRINTER_DRY_RUN=1 ../.venv/bin/python printerd.py   # PNGs in /tmp/p/out
```

## On the Pi

```bash
sudo systemctl status printerd        # the service
journalctl -u printerd -f             # its log
lpstat -t                             # CUPS queue Thermal80
sudo /opt/printer/device/update.sh    # pull + restart now
```
