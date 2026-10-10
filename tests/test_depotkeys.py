"""Cache chiavi depot in formato SLSsteam (yaml leggibile, 0600)."""
import os
import re

from core.depotkeys import collect_keys, write_cache, load_key, key_path

K = "b0288825cade4cf4aceb6bf5a2e523e0c94028b45fe8095fea1f7e04e26f5728"
LUA = (f'addappid(1332010)\naddappid(1332012, 1, "{K}")\n'
       f'--addappid(99,1,"{"c" * 64}")\n')


def _stplug(tmp):
    d = tmp / "stplug-in"
    d.mkdir()
    (d / "1332010.lua").write_text(LUA)
    return str(d)


def test_collect_skips_comments(tmp_path):
    found = collect_keys(_stplug(tmp_path))
    assert found == {1332012: (1332010, K)}


def test_write_and_load_round_trip(tmp_path):
    cache = str(tmp_path / "cache")
    write_cache(cache, 1332010, 1332012, K)
    assert load_key(cache, 1332012) == bytes.fromhex(K)
    st = os.stat(key_path(cache, 1332012))
    assert st.st_mode & 0o777 == 0o600


def test_load_missing_raises(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        load_key(str(tmp_path / "cache"), 123)


def test_write_is_idempotent(tmp_path):
    cache = str(tmp_path / "cache")
    write_cache(cache, 1332010, 1332012, K)
    before = open(key_path(cache, 1332012)).read()
    write_cache(cache, 1332010, 1332012, K)
    assert open(key_path(cache, 1332012)).read() == before


def test_rejects_bad_hex(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        write_cache(str(tmp_path / "cache"), 1, 2, "xyz")


def test_sync_config_vdf_no_nesting_and_idempotent(tmp_path):
    from core.depotkeys import sync_config_vdf
    cfg = tmp_path / "config.vdf"
    cfg.write_text('''"InstallConfigStore"
{
	"Software"
	{
		"Valve"
		{
			"Steam"
			{
				"depots"
				{
					"100"
					{
						"DecryptionKey"		"0000000000000000000000000000000000000000000000000000000000000000"
					}
				}
			}
		}
	}
}
''')
    keys = {
        200: (999, "1111111111111111111111111111111111111111111111111111111111111111"),
        300: (999, "2222222222222222222222222222222222222222222222222222222222222222"),
    }
    # Prima sincronizzazione
    sync_config_vdf(str(cfg), keys)
    content = cfg.read_text()
    assert '"100"' in content
    assert '"200"' in content
    assert '"300"' in content
    # Assicura che le parentesi graffe siano perfettamente bilanciate
    assert content.count('{') == content.count('}')
    # Verifica che '200' non sia nidificato dentro '100'
    m_100 = re.search(r'"100"\s*\{[^}]*\}', content)
    assert m_100 is not None
    assert '"200"' not in m_100.group(0)

    # Seconda sincronizzazione idempotente
    sync_config_vdf(str(cfg), keys)
    content2 = cfg.read_text()
    assert content2 == content

