"""WiFi / hotspot handling: what `iw dev` says -> port 80 on or off, one slip per change."""

import subprocess

import pytest

import printerd


def iw_fake(out: bytes):
    def run(cmd, **kw):
        assert cmd == ["iw", "dev"]
        return subprocess.CompletedProcess(cmd, 0, out, b"")
    return run


def iw(ssid: bytes, typ: str) -> bytes:
    return (b"phy#0\n\tUnnamed/non-netdev interface\n\t\twdev 0x2\n\t\ttype P2P-device\n"
            b"\tInterface wlan0\n\t\tifindex 3\n\t\twdev 0x1\n\t\taddr b8:27:eb:00:00:01\n"
            + (b"\t\tssid " + ssid + b"\n" if ssid else b"")
            + b"\t\ttype " + typ.encode() + b"\n\t\twiphy 0\n\t\ttxpower 31.00 dBm\n")


HOME = iw(b"Home Caf\\xc3\\xa9", "managed")       # iw escapes non-ASCII bytes
HOTSPOT = iw(b"printer-9be6", "AP")
NOTHING = iw(b"", "managed")


@pytest.fixture
def slips(monkeypatch, tmp_path):
    monkeypatch.setattr(printerd, "STATE", tmp_path)
    printed = []
    monkeypatch.setattr(printerd, "network_slip", lambda net: printed.append(net))
    return printed


def use(monkeypatch, out):
    monkeypatch.setattr(printerd.subprocess, "run", iw_fake(out))


def test_network_parses_wifi_and_hotspot(monkeypatch):
    use(monkeypatch, HOME)
    assert printerd.network() == {"mode": "wifi", "ssid": "Home Café"}
    use(monkeypatch, HOTSPOT)
    assert printerd.network() == {"mode": "hotspot", "ssid": "printer-9be6"}
    use(monkeypatch, NOTHING)
    assert printerd.network() == {"mode": "offline"}


def test_network_without_iw(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError("iw")
    monkeypatch.setattr(printerd.subprocess, "run", boom)
    assert printerd.network() == {"mode": "offline"}


def test_one_slip_per_change_and_port_80_handover(monkeypatch, slips):
    clock = [1_000_000.0]
    monkeypatch.setattr(printerd.time, "time", lambda: clock[0])
    monkeypatch.setattr(printerd, "_hotspot_since", None)
    scheduled = []
    monkeypatch.setattr(printerd, "_schedule", lambda delay, fn: scheduled.append(delay))

    use(monkeypatch, HOME)
    printerd.network_sync()
    printerd.network_sync()                       # same WiFi again (e.g. reboot): nothing
    assert slips == [{"mode": "wifi", "ssid": "Home Café"}]
    assert printerd._page_wanted.is_set()

    use(monkeypatch, HOTSPOT)                     # lost the WiFi: wait before helping
    printerd.network_sync()
    assert len(slips) == 1 and scheduled == [printerd.HOTSPOT_GRACE + 5]
    assert not printerd._page_wanted.is_set()     # port 80 is comitup-web's now
    clock[0] += 300
    printerd.network_sync()                       # still within the grace period
    assert len(slips) == 1
    clock[0] += 400
    printerd.network_sync()                       # gone for >10 min: setup slip
    printerd.network_sync()                       # comitup re-raises the hotspot: nothing
    assert slips[1:] == [{"mode": "hotspot", "ssid": "printer-9be6"}]

    use(monkeypatch, NOTHING)                     # between the two (connecting): no slip
    printerd.network_sync()
    assert len(slips) == 2

    use(monkeypatch, HOME)
    printerd.network_sync()
    assert slips[2:] == [{"mode": "wifi", "ssid": "Home Café"}]
    assert printerd._page_wanted.is_set()

    use(monkeypatch, HOTSPOT)                     # a phone hotspot that comes and goes:
    printerd.network_sync()                       # at most one setup slip a day
    clock[0] += 700
    printerd.network_sync()
    assert len(slips) == 3
    use(monkeypatch, HOME)                        # back before a slip: no "Connected" either
    printerd.network_sync()
    assert len(slips) == 3


def test_fresh_printer_gets_setup_slip_at_once(monkeypatch, slips):
    monkeypatch.setattr(printerd, "_hotspot_since", None)
    use(monkeypatch, HOTSPOT)
    printerd.network_sync()
    assert slips == [{"mode": "hotspot", "ssid": "printer-9be6"}]


def test_cloud_connection_is_kept_open(monkeypatch):
    made = []

    class Conn:
        def __init__(self, host, port, timeout):
            made.append(host)
            self.n = 0
        def request(self, method, path, body, headers):
            self.n += 1
            if len(made) == 1 and self.n == 3:
                raise ConnectionResetError("server closed the idle connection")
            self.path = path
        def getresponse(self):
            class R:
                status = 200
                def read(self):
                    return b'{"ok": true}'
            return R()
        def close(self):
            pass

    monkeypatch.setattr(printerd, "CLOUD_URL", "https://example.supabase.co")
    monkeypatch.setattr(printerd, "_conn", None)
    monkeypatch.setattr(printerd.http.client, "HTTPSConnection", Conn)
    assert printerd.rpc("claim_jobs", device_token="t") == {"ok": True}
    assert printerd.rpc("claim_jobs", device_token="t") == {"ok": True}
    assert made == ["example.supabase.co"]        # two calls, one connection
    assert printerd.rpc("claim_jobs", device_token="t") == {"ok": True}
    assert len(made) == 2                         # closed by the server: reconnected once


def test_failed_slip_is_retried(monkeypatch, tmp_path):
    monkeypatch.setattr(printerd, "STATE", tmp_path)
    use(monkeypatch, HOME)
    calls = []

    def flaky(net):
        calls.append(net)
        if len(calls) == 1:
            raise RuntimeError("lp failed")
    monkeypatch.setattr(printerd, "network_slip", flaky)
    printerd.network_sync()
    printerd.network_sync()
    printerd.network_sync()
    assert len(calls) == 2


def test_network_trigger_is_local_only(monkeypatch):
    ran = []
    monkeypatch.setattr(printerd, "network_sync", lambda: ran.append(1))
    c = printerd.app.test_client()
    assert c.post("/network", environ_base={"REMOTE_ADDR": "192.168.1.50"}).status_code == 403
    assert c.post("/network").status_code == 200          # test client is 127.0.0.1
    for t in printerd.threading.enumerate():
        if t is not printerd.threading.current_thread() and t.daemon:
            t.join(timeout=1)
    assert ran == [1]


def test_slips_render(monkeypatch, tmp_path):
    monkeypatch.setattr(printerd, "STATE", tmp_path)
    monkeypatch.setattr(printerd, "DRY", True)
    monkeypatch.setattr(printerd, "local_ip", lambda: "10.41.0.1")
    printerd.network_slip({"mode": "hotspot", "ssid": "printer-9be6"})
    printerd.network_slip({"mode": "wifi", "ssid": "Home"})
    pngs = sorted((tmp_path / "out").glob("*.png"))
    assert len(pngs) == 2


def test_hotspot_slip_carries_password(monkeypatch):
    import printerd
    sent = {}
    monkeypatch.setattr(printerd, "slip", lambda text, title, qr_data="", caption="": sent.update(text=text, qr=qr_data))
    monkeypatch.setattr(printerd, "hotspot_password", lambda: "k7m2pq9x")
    printerd.network_slip({"mode": "hotspot", "ssid": "printer-9be6"})
    assert sent["qr"] == "WIFI:T:WPA;S:printer-9be6;P:k7m2pq9x;;"
    assert "k7m2pq9x" in sent["text"]
    monkeypatch.setattr(printerd, "hotspot_password", lambda: "")
    printerd.network_slip({"mode": "hotspot", "ssid": "printer-9be6"})
    assert sent["qr"] == "WIFI:T:nopass;S:printer-9be6;;"


def test_moved_printer_gets_setup_slip_soon_after_power_on(monkeypatch, slips):
    clock = [1_000_000.0]
    monkeypatch.setattr(printerd.time, "time", lambda: clock[0])
    monkeypatch.setattr(printerd, "_hotspot_since", None)
    monkeypatch.setattr(printerd, "_schedule", lambda delay, fn: None)
    use(monkeypatch, HOME)
    printerd.network_sync()                       # it knew a WiFi at home
    monkeypatch.setattr(printerd, "_hotspot_since", None)   # power off, carried away
    monkeypatch.setattr(printerd, "uptime", lambda: 40.0)   # switched on 40 s ago
    use(monkeypatch, HOTSPOT)
    printerd.network_sync()
    clock[0] += 60
    printerd.network_sync()                       # comitup's start-up blip: still nothing
    assert len(slips) == 1
    clock[0] += 70
    printerd.network_sync()                       # 2 min without WiFi: help now, not in 10
    assert slips[1:] == [{"mode": "hotspot", "ssid": "printer-9be6"}]
