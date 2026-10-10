"""Staging manifest SLS -> depotcache di Steam (manca solo copia)."""
import os

from core.manifests import stage_all


def test_stage_copies_missing(tmp_path):
    src = tmp_path / "sls"
    src.mkdir()
    (src / "1332012_103.manifest").write_bytes(b"manifest-bytes")
    (src / ".preferred_1332012").write_text("103\n")
    (src / "notes.txt").write_text("skip me")
    dst = tmp_path / "depotcache"
    copied, present = stage_all(str(src), str(dst))
    assert copied == ["1332012_103.manifest"]
    assert (dst / "1332012_103.manifest").read_bytes() == b"manifest-bytes"
    copied2, present2 = stage_all(str(src), str(dst))
    assert copied2 == [] and present2 == ["1332012_103.manifest"]


def test_stage_replaces_different_size(tmp_path):
    src = tmp_path / "sls"
    src.mkdir()
    (src / "1_2.manifest").write_bytes(b"new-content!")
    dst = tmp_path / "depotcache"
    dst.mkdir()
    (dst / "1_2.manifest").write_bytes(b"old")
    copied, _ = stage_all(str(src), str(dst))
    assert copied == ["1_2.manifest"]
    assert (dst / "1_2.manifest").read_bytes() == b"new-content!"


def test_stage_rejects_bad_names(tmp_path):
    src = tmp_path / "sls"
    src.mkdir()
    (src / "evil_.._x.manifest").write_bytes(b"x")
    (src / "nodotmanifest").write_bytes(b"x")
    dst = tmp_path / "depotcache"
    copied, present = stage_all(str(src), str(dst))
    assert copied == [] and present == []
    assert list(dst.iterdir()) == []


def test_stage_missing_src_ok(tmp_path):
    copied, present = stage_all(str(tmp_path / "nope"),
                                str(tmp_path / "dst"))
    assert copied == [] and present == []
