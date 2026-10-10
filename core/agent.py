"""LaunchAgent di login: `maclua ensure` a ogni avvio, prima di Steam.

Senza hook nel client, le licenze su disco sono l'unica cosa che fa
apparire i giochi. Steam le sovrascrive a ogni update: l'agent le
riapplica a ogni login. Disattivare "Steam → apri al login" evita la race.
"""
import os
import plistlib

LABEL = "com.maclua.ensure"


def plist_bytes(python, maclua_py):
    return plistlib.dumps({
        "Label": LABEL,
        "ProgramArguments": [python, maclua_py, "ensure"],
        "RunAtLoad": True,
        "StandardOutPath": "/tmp/maclua-ensure.log",
        "StandardErrorPath": "/tmp/maclua-ensure.log",
    })


def agent_path(launch_agents_dir):
    return os.path.join(launch_agents_dir, LABEL + ".plist")


def install(python, maclua_py, launch_agents_dir):
    """Scrive il plist. Ritorna il path. Non carica (serve logout/login)."""
    os.makedirs(launch_agents_dir, exist_ok=True)
    path = agent_path(launch_agents_dir)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(plist_bytes(python, maclua_py))
    os.rename(tmp, path)
    return path


def remove(launch_agents_dir):
    path = agent_path(launch_agents_dir)
    try:
        os.remove(path)
        return True
    except OSError:
        return False


def installed(launch_agents_dir):
    return os.path.exists(agent_path(launch_agents_dir))
