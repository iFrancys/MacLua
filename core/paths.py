"""Percorsi macOS di Steam e dello stato MacLua.

Ogni funzione accetta ``home`` esplicito (default: ``~``) così resta
testabile senza toccare l'ambiente reale.
"""
import os


def _home(home=None):
    return home if home else os.path.expanduser("~")


def steam_root(home=None):
    return os.path.join(_home(home), "Library/Application Support/Steam")


def steamapps(home=None):
    return os.path.join(steam_root(home), "steamapps")


def appcache(home=None):
    return os.path.join(steam_root(home), "appcache")


def depotcache(home=None):
    return os.path.join(steam_root(home), "depotcache")


def steam_config(home=None):
    return os.path.join(steam_root(home), "config")


def stplug_in(home=None):
    return os.path.join(steam_config(home), "stplug-in")


def sls_dir(home=None):
    return os.path.join(_home(home), "Library/Application Support/SLSsteam")


def sls_cache(home=None):
    return os.path.join(sls_dir(home), "cache")


def sls_manifests(home=None):
    return os.path.join(sls_dir(home), "manifests")


def appmanifest(home, appid):
    return os.path.join(steamapps(home), f"appmanifest_{int(appid)}.acf")
