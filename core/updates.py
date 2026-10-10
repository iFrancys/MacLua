"""Controllo e applicazione aggiornamenti per giochi base e nuovi DLC.
Confronta la build installata con quella pubblica e verifica se sono usciti nuovi DLC.
"""
import os
import re
from core import paths, appinfo as ai, install


def get_installed_buildid(steamapps_dir, appid):
    """Legge il buildid correntemente registrato nell'appmanifest."""
    acf_path = os.path.join(steamapps_dir, f"appmanifest_{appid}.acf")
    if not os.path.exists(acf_path):
        return None
    try:
        with open(acf_path, "r", encoding="utf-8", errors="replace") as f:
            txt = f.read()
        m = re.search(r'"buildid"\s+"(\d+)"', txt)
        return int(m.group(1)) if m else None
    except Exception:
        return None


def check_updates(appid, home=None):
    """Verifica se per un appid è disponibile un aggiornamento di gioco o nuovi DLC."""
    home = home or os.path.expanduser("~")
    steamapps = paths.steamapps(home)

    current_b = get_installed_buildid(steamapps, appid)
    public_b = ai.public_buildid(appid)

    has_game_update = False
    if current_b is not None and public_b is not None and public_b > current_b:
        has_game_update = True

    # Verifica nuovi DLC analizzando il lua installato vs appinfo
    lua_path = os.path.join(paths.stplug_in(home), f"{appid}.lua")
    new_dlcs = []
    if os.path.exists(lua_path):
        try:
            with open(lua_path, "r", encoding="utf-8", errors="replace") as f:
                lua_txt = f.read()
            # DLC noti dall'appinfo
            info = ai.appinfo_of(appid)
            if info and "extended" in info and "listofdlc" in info["extended"]:
                dlc_str = str(info["extended"]["listofdlc"])
                for d in dlc_str.split(","):
                    d = d.strip()
                    if d.isdigit():
                        d_id = int(d)
                        if f"addappid({d_id}" not in lua_txt:
                            new_dlcs.append(d_id)
        except Exception:
            pass

    return {
        "appid": appid,
        "current_buildid": current_b,
        "latest_buildid": public_b,
        "has_update": has_game_update or bool(new_dlcs),
        "game_update": has_game_update,
        "new_dlcs": new_dlcs
    }
