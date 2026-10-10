"""Creazione appmanifest da appinfo + owner da loginusers."""
from core import install


def test_create_appmanifest(tmp_path):
    acf = install.create_appmanifest(str(tmp_path), 1671210, "DELTARUNE",
                                     "DELTARUNE", 24484059, "76561190000000001")
    import re
    txt = open(acf, encoding="utf-8").read()
    assert '"appid"\t\t"1671210"' in txt
    assert '"name"\t\t"DELTARUNE"' in txt
    assert '"installdir"\t\t"DELTARUNE"' in txt
    assert '"TargetBuildID"\t\t"24484059"' in txt
    assert '"LastOwner"\t\t"76561190000000001"' in txt
    assert '"StateFlags"\t\t"2"' in txt
    assert re.search(r'"InstalledDepots"\s*\{\s*\}', txt)


def test_create_appmanifest_idempotent_keeps_existing(tmp_path):
    acf = install.create_appmanifest(str(tmp_path), 10, "G", "G", 1, "2")
    with open(acf, "w", encoding="utf-8") as f:
        f.write("MODIFIED")
    assert install.create_appmanifest(str(tmp_path), 10, "G", "G", 1, "2") == acf
    assert open(acf).read() == "MODIFIED"


def test_last_owner_picks_newest(tmp_path):
    vdf = ('"users"\n{\n\t"76561190000000001"\n\t{\n\t\t"Timestamp"\t\t"100"\n\t}\n'
           '\t"76561190000000002"\n\t{\n\t\t"Timestamp"\t\t"200"\n\t}\n}\n')
    p = tmp_path / "loginusers.vdf"
    p.write_text(vdf)
    assert install.last_owner(str(p)) == "76561190000000002"


def test_last_owner_missing_file(tmp_path):
    assert install.last_owner(str(tmp_path / "nope.vdf")) == "0"
