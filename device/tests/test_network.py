"""WiFi / hotspot handling: what nmcli says -> port 80 on or off, one slip per change."""

import subprocess

import pytest

import printerd


def nmcli_fake(active, settings):
    """active: lines of `nmcli -g UUID,TYPE,STATE con show --active`;
    settings: uuid -> (mode, ssid)."""
    def run(cmd, **kw):
        assert cmd[0] == "nmcli"
        if "--active" in cmd:
            out = "\n".join(active)
        else:
            mode, ssid = settings[cmd[-1]]
            out = f"{mode}\n{ssid}"
        return subprocess.CompletedProcess(cmd, 0, out + "\n", "")
    return run


HOME = ["5eeb:802-11-wireless:activated", "75a1:802-3-ethernet:activated"]
HOTSPOT = ["c0ff:802-11-wireless:activated"]
SETTINGS = {"5eeb": ("infrastructure", "Home\\:Net"), "c0ff": ("ap", "printer-9be6")}


@pytest.fixture
def slips(monkeypatch, tmp_path):
    monkeypatch.setattr(printerd, "STATE", tmp_path)
    printed = []
    monkeypatch.setattr(printerd, "network_slip", lambda net: printed.append(net))
    return printed


def use(monkeypatch, active):
    monkeypatch.setattr(printerd.subprocess, "run", nmcli_fake(active, SETTINGS))


def test_network_parses_wifi_and_hotspot(monkeypatch):
    use(monkeypatch, HOME)
    assert printerd.network() == {"mode": "wifi", "ssid": "Home:Net"}
    use(monkeypatch, HOTSPOT)
    assert printerd.network() == {"mode": "hotspot", "ssid": "printer-9be6"}
    use(monkeypatch, ["c0ff:802-11-wireless:activating"])
    assert printerd.network() == {"mode": "offline"}


def test_network_without_nmcli(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError("nmcli")
    monkeypatch.setattr(printerd.subprocess, "run", boom)
    assert printerd.network() == {"mode": "offline"}


def test_one_slip_per_change_and_port_80_handover(monkeypatch, slips):
    use(monkeypatch, HOME)
    printerd.network_sync()
    printerd.network_sync()                       # same WiFi again (e.g. reboot): nothing
    assert slips == [{"mode": "wifi", "ssid": "Home:Net"}]
    assert printerd._page_wanted.is_set()

    use(monkeypatch, HOTSPOT)
    printerd.network_sync()
    printerd.network_sync()                       # comitup re-raises the hotspot: nothing
    assert slips[1:] == [{"mode": "hotspot", "ssid": "printer-9be6"}]
    assert not printerd._page_wanted.is_set()     # port 80 is comitup-web's now

    use(monkeypatch, [])                          # between the two: no slip, page stays as is
    printerd.network_sync()
    assert len(slips) == 2

    use(monkeypatch, HOME)
    printerd.network_sync()
    assert slips[2:] == [{"mode": "wifi", "ssid": "Home:Net"}]
    assert printerd._page_wanted.is_set()


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
