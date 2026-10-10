"""update_check: installato (acf) vs pubblico (appinfo) -> update disponibile?"""
from core.install import update_check

ACF = ('"AppState"\n{\n\t"appid"\t\t"10"\n'
       '\t"InstalledDepots"\n\t{\n\t\t"11"\n\t\t{\n'
       '\t\t\t"manifest"\t\t"9001"\n\t\t\t"size"\t\t"5"\n\t\t}\n\t}\n}\n')


def live(gid):
    return [{"id": 11, "oslist": "macos", "gid": gid, "size": "5",
             "shared": False}]


def test_no_update_when_same():
    out = update_check(ACF, live("9001"))
    assert out == {"installed": {11: "9001"}, "live": {11: "9001"},
                   "available": False}


def test_update_when_live_newer():
    out = update_check(ACF, live("9002"))
    assert out["available"] is True
    assert out["live"] == {11: "9002"}


def test_update_when_no_acf_entry():
    out = update_check('"AppState"\n{\n}\n', live("9001"))
    assert out == {"installed": {}, "live": {11: "9001"}, "available": False}


def test_live_without_gid_ignored():
    out = update_check(ACF, [{"id": 11, "oslist": "macos", "gid": None,
                              "size": None, "shared": False}])
    assert out["available"] is False
