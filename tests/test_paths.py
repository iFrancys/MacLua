"""Percorsi macOS di Steam e dello stato MacLua. Tutti puri rispetto a HOME."""
import os

from core.paths import (
    steam_root,
    steamapps,
    appcache,
    depotcache,
    steam_config,
    stplug_in,
    sls_dir,
    sls_cache,
    sls_manifests,
    appmanifest,
)

HOME = "/Users/testuser"


def test_steam_root():
    assert steam_root(HOME) == (
        "/Users/testuser/Library/Application Support/Steam")


def test_steamapps():
    assert steamapps(HOME).endswith("Steam/steamapps")


def test_appcache():
    assert appcache(HOME).endswith("Steam/appcache")


def test_depotcache():
    assert depotcache(HOME).endswith("Steam/depotcache")


def test_steam_config():
    assert steam_config(HOME).endswith("Steam/config")


def test_stplug_in():
    assert stplug_in(HOME).endswith("Steam/config/stplug-in")


def test_sls_dir():
    assert sls_dir(HOME) == (
        "/Users/testuser/Library/Application Support/SLSsteam")


def test_sls_cache_and_manifests():
    assert sls_cache(HOME).endswith("SLSsteam/cache")
    assert sls_manifests(HOME).endswith("SLSsteam/manifests")


def test_appmanifest_name():
    assert appmanifest(HOME, 1332010).endswith(
        "steamapps/appmanifest_1332010.acf")


def test_default_home_is_expanded():
    assert steam_root().startswith(os.path.expanduser("~")[:4])
