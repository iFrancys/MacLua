"""Login LaunchAgent: runs `maclua ensure` on every user login, before Steam.

Without client hooks, on-disk licenses are what make games appear in Steam.
Steam overwrites them on update; the agent reapplies them on every login.
Disabling 'Steam -> Open at Login' avoids race conditions.
"""
import os
import plistlib

from core.atomic import atomic_write

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
    """Writes the plist file. Returns the path. Does not load (requires logout/login)."""
    os.makedirs(launch_agents_dir, exist_ok=True)
    path = agent_path(launch_agents_dir)
    atomic_write(path, plist_bytes(python, maclua_py))
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
