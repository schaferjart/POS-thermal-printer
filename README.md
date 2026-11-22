# Thermal printer appliance

A Raspberry Pi and an 80 mm receipt printer that you can give to someone. They plug
it in, set up the WiFi from a phone, and from then on it is:

- **a normal printer** on their WiFi: AirPrint from an iPhone, iPad or Mac, no driver;
- **a print page** at `http://print.local` (or its IP address): Markdown, images,
  image slices, uploaded fonts;
- **an inbox for apps**, if you run a cloud: anything that can call one function
  (`printer.send_print`) can print on it from anywhere. The printer only ever
  connects outward, so it needs no port forwarding and no VPN.

Built for an 80 mm USB ESC/POS printer (sold as Xprinter XP-V330M / BORN4SHIP V330M,
USB id `1fc9:2016`) on a Raspberry Pi Zero 2 W. Other 80 mm ESC/POS printers should
work; the CUPS settings in `device/install.sh` are tuned for this one.

## What you need

- Raspberry Pi Zero 2 W (512 MB is enough) or any newer Pi, with a microSD card
- an 80 mm USB ESC/POS printer and its power supply, a USB OTG cable
- optional: a [Supabase](https://supabase.com) project, for printing from apps

## Install

1. Flash **Raspberry Pi OS Lite (64-bit)** with Raspberry Pi Imager. In its settings,
   set a user, turn on SSH, and enter your WiFi (2.4 GHz: the Zero 2 W has no 5 GHz).
2. Boot the Pi, plug in the printer, and log in: `ssh <user>@<the Pi's IP>`.
3. Run:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/schaferjart/POS-thermal-printer/stable/device/install.sh | sudo bash
   ```

   With a cloud (see [Printing from apps](#printing-from-apps)):

   ```bash
   curl -fsSL https://raw.githubusercontent.com/schaferjart/POS-thermal-printer/stable/device/install.sh \
     | sudo PRINTER_CLOUD_URL=https://<project-ref>.supabase.co PRINTER_CLOUD_KEY=sb_publishable_... bash
   ```

It takes 10-20 minutes on a Zero 2 W. It names the Pi `print`, sets up the CUPS
queue `Thermal80` with AirPrint, the print service, the WiFi setup hotspot and a
daily updater. Running it again is safe.

## Setting it up in a new place

When the printer is switched on and finds no WiFi it knows, it opens its own WiFi
(`printer-xxxx`, with a password made for this printer) and, after about 2 minutes,
prints a **setup slip**:

1. Copy the password of the WiFi you want it on (the slip says where to find it).
2. Scan the first QR code: the phone joins the printer's WiFi.
3. Scan the second QR code: the setup page opens (`http://10.41.0.1`). Pick the
   WiFi and paste its password.
4. The printer joins it and prints **Connected**, with a QR code to its print page.

If the WiFi it knows goes away while it runs (a phone hotspot switched off), it waits
10 minutes before printing a setup slip, and prints at most one a day.

It can join: home WiFi and phone hotspots on 2.4 GHz (iPhone: turn on *Maximize
Compatibility*; Android: choose the 2.4 GHz band). It can't join: 5 GHz-only
networks, WiFi with a login page (hotels, trains), or WiFi with a user name
(eduroam, most offices).

**Test it at home** without touching your router:

```bash
sudo /opt/printer/device/setup-test.sh          # forget the saved WiFis, reboot
sudo /opt/printer/device/setup-test.sh restore  # or wait: they come back 15 min after boot
```

## Printing

**AirPrint.** On a Mac: System Settings > Printers > Add Printer, pick
*Thermal printer 80mm*. If macOS offers *Generic PostScript*, add it by IP address
with the AirPrint protocol instead. Paper is a continuous roll: a print is as long as
its content, then cut.

**The print page.** `http://print.local` or the IP address on the *Connected* slip.
Browsers that use secure DNS (Brave, sometimes Chrome) can't open `.local` names:
use the IP address or turn secure DNS off.

**Local API** (same network, no key):

```bash
curl -F body='# Hello' -F style=helvetica http://print.local/print/markdown
curl -F file=@photo.jpg -F dither=floyd   http://print.local/print/image
curl -F file=@poster.png -F count=4       http://print.local/print/slices
curl -F file=@ready.png http://print.local:9100/print     # a finished 576 px image
curl http://print.local/health
```

| template   | fields |
|------------|--------|
| `markdown` | `body`, `style` (`dictionary`, `helvetica`, `acidic` or an uploaded font), `heading_font`, `size`, `show_date` |
| `image`    | `file` or `image_url`, `dither` (`floyd`, `bayer`, `halftone`), `dot_size`, `contrast`, `brightness`, `sharpness`, `blur` |
| `slices`   | `file`, `count`, `direction`, `mode` (`separate`, `single`), `gap`, `padding`, `pause`, `caption`, `caption_position`, `caption_size` |
| `showmemo` | `object_id`, `title`, `artist`, `date`, `image_url` |

**Fonts.** Upload `.ttf`/`.otf` on the print page. With a cloud, every printer of
the same cloud gets them.

## Printing from apps

The cloud is a Supabase project with one schema, `printer`. Apps and printers only
call its functions with the project's **publishable** key; no printer holds a secret.

1. Create the schema `printer` and add it to *Exposed schemas* in the API settings
   **first**: exposing a schema grants table rights, which the migrations then take
   back. Apply `supabase/migrations/*_printer*.sql` in order (SQL editor or
   `supabase db push`), then run `supabase/tests/printer_smoke.sql`: it checks that
   only the functions are reachable, and rolls back.
2. Install the printer with `PRINTER_CLOUD_URL` and `PRINTER_CLOUD_KEY` (above), or
   write them to `/etc/printer/printer.env` later (see `device/printer.env.example`).
3. The printer registers itself and prints a **pairing slip** with a code. Activate
   it in the SQL editor:

   ```sql
   update printer.devices
      set active = true, subscriptions = '{showmemo}'   -- sources it prints unaddressed
    where pairing_code = 'XXXXXX';
   ```

4. Send a print from anywhere:

   ```bash
   curl https://<project-ref>.supabase.co/rest/v1/rpc/send_print \
     -H "apikey: sb_publishable_..." -H "Content-Profile: printer" \
     -H "Content-Type: application/json" \
     -d '{"source":"my-app","template":"markdown","payload":{"body":"# Hi"},"device":"printer-xxxx"}'
   ```

   Without `device`, one job goes to every active printer subscribed to `source`.
   Each printer takes at most 30 jobs an hour (`hourly_limit`). Printers ask for jobs
   every 10 s after a print and back off to every 60 s when idle.

The publishable key is public by design. Anyone who has it can send to a source your
printers subscribe to, within the hourly limits.

## Portrait renderer (optional)

`renderer/` is a small web service (Docker, port 8000) that turns a photo into four
dithered, ever closer crops of the face. It needs an OpenRouter key and checks every
caller's device token with `printer.check_device`. See `renderer/.env.example` and
`renderer/config.yaml`. The printer side (a *Portrait* section on the page) is not
built yet.

## Updates

Every night at about 04:00 the printer pulls the branch it was installed from
(`stable`) and restarts. Run `sudo /opt/printer/device/update.sh` to update now.
There is no automatic rollback yet: a broken `stable` reaches every printer, so
work on other branches and move `stable` only when a change is tested.

## On the Pi

```bash
sudo systemctl status printerd   # the service
journalctl -u printerd -f        # its log (kept in RAM only, to spare the SD card)
lpstat -t                        # the CUPS queue
```

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install pillow flask pyyaml qrcode python-escpos pytest
cd device && ../.venv/bin/python -m pytest -q tests
PRINTER_STATE_DIR=/tmp/p PRINTER_DRY_RUN=1 ../.venv/bin/python printerd.py   # prints become PNGs in /tmp/p/out
```

`CLAUDE.md` has the rules that bite (database grants, keys, migrations).

## License

MIT, see `LICENSE`.
