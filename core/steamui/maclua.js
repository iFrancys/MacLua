/**
 * MacLua in-Steam Injected Client UI
 * - Inietta un quadratino con il logo di MacLua affianco al blocco del carrello nello Store di Steam.
 * - Cliccando il quadratino si apre un popup di impostazioni completo (scelta database, chiave Morrenus, auto-update, riparazione manifest, libreria).
 * - Sulle pagine /app/<id> inietta il pulsante pulito "Aggiungi con MacLua" / "Gioca con MacLua" accanto a "Hub della Comunità".
 * - Usa il canale bidirezionale CDP RPC per comunicare stabilmente con MacLua senza blocchi di mixed-content.
 */
(function () {
  if (typeof location === "undefined" || location.hostname !== "store.steampowered.com") {
    return;
  }

  const MACLUA_ICON_B64 = "data:image/png;base64,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";

  window.__MacLuaRPC = window.__MacLuaRPC || { id: 0, pending: {}, responses: {} };

  // 1. Comunicazione infallibile tramite CDP RPC
  async function api(path, method = "GET", data = null) {
    return new Promise((resolve) => {
      const reqId = String(++window.__MacLuaRPC.id);
      window.__MacLuaRPC.pending[reqId] = { path, method, data };
      const start = Date.now();
      const timer = setInterval(() => {
        if (window.__MacLuaRPC.responses && window.__MacLuaRPC.responses[reqId] !== undefined) {
          clearInterval(timer);
          const r = window.__MacLuaRPC.responses[reqId];
          delete window.__MacLuaRPC.responses[reqId];
          resolve(r);
        } else if (Date.now() - start > 30000) {
          clearInterval(timer);
          delete window.__MacLuaRPC.pending[reqId];
          resolve({ ok: false, error: "Timeout: impossibile comunicare con il bridge MacLua" });
        }
      }, 50);
    });
  }

  // 2. Notifiche Toast
  function showToast(title, msg, progress = null) {
    let toast = document.getElementById("maclua-toast");
    if (!toast) {
      toast = document.createElement("div");
      toast.id = "maclua-toast";
      toast.className = "maclua-toast";
      document.body.appendChild(toast);
    }
    let progHtml = "";
    if (progress !== null) {
      progHtml = `
        <div class="maclua-progress-bar">
          <div class="maclua-progress-fill" style="width: ${Math.round(progress * 100)}%;"></div>
        </div>
      `;
    }
    toast.innerHTML = `
      <div style="font-weight: 700; color: #38bdf8; margin-bottom: 4px;">${title}</div>
      <div style="font-size: 12px; color: #cbd5e1;">${msg}</div>
      ${progHtml}
    `;
    clearTimeout(toast._timeout);
    if (progress === null || progress >= 1.0) {
      toast._timeout = setTimeout(() => {
        if (toast) toast.remove();
      }, 4000);
    }
  }

  const I18N = {
    en: {
      title: "MacLua Settings",
      language: "Language",
      sources: "Manifest Sources & Database",
      srcAuto: "Auto (Sushi, Ryuu, Hubcap)",
      srcSushi: "Sushi (GitHub Raw - Free)",
      srcRyuu: "Ryuu (Anonymous - Free)",
      srcHubcap: "Hubcap / Morrenus (Requires Key)",
      apiKey: "Morrenus / Hubcap API Key",
      maintenance: "Maintenance",
      repairBtn: "🧹 Repair Steam Library",
      restartBtn: "↻ Restart Steam",
      managedGames: "Managed Games in Library",
      loadingGames: "Loading games...",
      noGames: "No managed games found.",
      installed: "Installed",
      remove: "Remove",
      close: "Close",
      save: "Save Settings",
      saving: "Saving...",
      saved: "✓ Settings saved successfully!",
      saveError: "Error saving settings.",
      cleaning: "Repairing Steam Library...",
      cleaned: "✓ Steam Library repaired successfully!",
      restarting: "Restarting Steam...",
      removedGame: "Removed {name} from MacLua.",
      removeError: "Error removing game.",
      addBtn: "Add with MacLua",
      adding: "Adding with MacLua...",
      addedBtn: "✓ Added with MacLua",
      playBtn: "▶ Play with MacLua",
      removeBtnHeader: "✕ Remove from MacLua",
      removing: "Removing...",
      addedToast: "Game added successfully{src}! Restart Steam to see it in Library.",
      alreadyAddedToast: "Game already added to MacLua. You can install it from Steam Library!",
      restartHeaderBtn: "↻ Restart Steam",
      updateGame: "Update",
      updatingGame: "Updating...",
      updatedToast: "✓ In-place update started for {name}!",
    },
    it: {
      title: "MacLua Impostazioni",
      language: "Lingua",
      sources: "Sorgenti Manifest e Database",
      srcAuto: "Auto (Sushi, Ryuu, Hubcap)",
      srcSushi: "Sushi (GitHub Raw - Gratuito)",
      srcRyuu: "Ryuu (Anonimo - Gratuito)",
      srcHubcap: "Hubcap / Morrenus (Richiede Chiave)",
      apiKey: "Chiave API Morrenus / Hubcap",
      maintenance: "Manutenzione",
      repairBtn: "🧹 Ripara Libreria Steam",
      restartBtn: "↻ Riavvia Steam",
      managedGames: "Giochi Gestiti nella Libreria",
      loadingGames: "Caricamento giochi...",
      noGames: "Nessun gioco gestito trovato.",
      installed: "Installato",
      remove: "Rimuovi",
      close: "Chiudi",
      save: "Salva Impostazioni",
      saving: "Salvataggio...",
      saved: "✓ Impostazioni salvate con successo!",
      saveError: "Errore durante il salvataggio.",
      cleaning: "Riparazione libreria in corso...",
      cleaned: "✓ Libreria Steam riparata con successo!",
      restarting: "Riavvio di Steam in corso...",
      removedGame: "Rimosso {name} da MacLua.",
      removeError: "Errore durante la rimozione.",
      addBtn: "Aggiungi con MacLua",
      adding: "Aggiunta in corso...",
      addedBtn: "✓ Aggiunto con MacLua",
      playBtn: "▶ Gioca con MacLua",
      removeBtnHeader: "✕ Rimuovi da MacLua",
      removing: "Rimozione in corso...",
      addedToast: "Gioco aggiunto con successo{src}! Riavvia Steam per vederlo nella Libreria.",
      alreadyAddedToast: "Gioco già aggiunto a MacLua. Puoi scaricarlo direttamente dalla Libreria!",
      restartHeaderBtn: "↻ Riavvia Steam",
      updateGame: "Aggiorna",
      updatingGame: "Aggiornamento...",
      updatedToast: "✓ Aggiornamento in-place avviato per {name}!",
    },
    de: {
      title: "MacLua Einstellungen",
      language: "Sprache",
      sources: "Manifest-Quellen & Datenbank",
      srcAuto: "Auto (Sushi, Ryuu, Hubcap)",
      srcSushi: "Sushi (GitHub Raw - Kostenlos)",
      srcRyuu: "Ryuu (Anonym - Kostenlos)",
      srcHubcap: "Hubcap / Morrenus (Erfordert Schlüssel)",
      apiKey: "Morrenus / Hubcap API-Schlüssel",
      maintenance: "Wartung",
      repairBtn: "🧹 Steam-Bibliothek reparieren",
      restartBtn: "↻ Steam neu starten",
      managedGames: "Verwaltete Spiele in der Bibliothek",
      loadingGames: "Spiele werden geladen...",
      noGames: "Keine verwalteten Spiele gefunden.",
      installed: "Installiert",
      remove: "Entfernen",
      close: "Schließen",
      save: "Einstellungen speichern",
      saving: "Speichern...",
      saved: "✓ Einstellungen erfolgreich gespeichert!",
      saveError: "Fehler beim Speichern der Einstellungen.",
      cleaning: "Steam-Bibliothek wird repariert...",
      cleaned: "✓ Steam-Bibliothek erfolgreich repariert!",
      restarting: "Steam wird neu gestartet...",
      removedGame: "{name} aus MacLua entfernt.",
      removeError: "Fehler beim Entfernen des Spiels.",
      addBtn: "Mit MacLua hinzufügen",
      adding: "Wird hinzugefügt...",
      addedBtn: "✓ Mit MacLua hinzugefügt",
      playBtn: "▶ Mit MacLua spielen",
      removeBtnHeader: "✕ Aus MacLua entfernen",
      removing: "Wird entfernt...",
      addedToast: "Spiel erfolgreich hinzugefügt{src}! Steam neu starten, um es in der Bibliothek zu sehen.",
      alreadyAddedToast: "Spiel bereits zu MacLua hinzugefügt. Sie können es aus der Steam-Bibliothek installieren!",
      restartHeaderBtn: "↻ Steam neu starten",
      updateGame: "Aktualisieren",
      updatingGame: "Aktualisiere...",
      updatedToast: "✓ In-Place-Update gestartet für {name}!",
    },
    es: {
      title: "MacLua Ajustes",
      language: "Idioma",
      sources: "Fuentes de Manifest y Base de Datos",
      srcAuto: "Auto (Sushi, Ryuu, Hubcap)",
      srcSushi: "Sushi (GitHub Raw - Gratis)",
      srcRyuu: "Ryuu (Anónimo - Gratis)",
      srcHubcap: "Hubcap / Morrenus (Requiere Clave)",
      apiKey: "Clave API Morrenus / Hubcap",
      maintenance: "Mantenimiento",
      repairBtn: "🧹 Reparar Biblioteca de Steam",
      restartBtn: "↻ Reiniciar Steam",
      managedGames: "Juegos Administrados en la Biblioteca",
      loadingGames: "Cargando juegos...",
      noGames: "No se encontraron juegos administrados.",
      installed: "Instalado",
      remove: "Eliminar",
      close: "Cerrar",
      save: "Guardar Ajustes",
      saving: "Guardando...",
      saved: "✓ ¡Ajustes guardados con éxito!",
      saveError: "Error al guardar los ajustes.",
      cleaning: "Reparando biblioteca de Steam...",
      cleaned: "✓ ¡Biblioteca de Steam reparada con éxito!",
      restarting: "Reiniciando Steam...",
      removedGame: "Se ha eliminado {name} de MacLua.",
      removeError: "Error al eliminar el juego.",
      addBtn: "Añadir con MacLua",
      adding: "Añadiendo...",
      addedBtn: "✓ Añadido con MacLua",
      playBtn: "▶ Jugar con MacLua",
      removeBtnHeader: "✕ Eliminar de MacLua",
      removing: "Eliminando...",
      addedToast: "¡Juego añadido con éxito{src}! Reinicia Steam para verlo en la Biblioteca.",
      alreadyAddedToast: "¡Juego ya añadido a MacLua. Puedes instalarlo desde la Biblioteca de Steam!",
      restartHeaderBtn: "↻ Reiniciar Steam",
      updateGame: "Actualizar",
      updatingGame: "Actualizando...",
      updatedToast: "✓ ¡Actualización in-place iniciada para {name}!",
    },
    fr: {
      title: "MacLua Paramètres",
      language: "Langue",
      sources: "Sources de Manifest et Base de Données",
      srcAuto: "Auto (Sushi, Ryuu, Hubcap)",
      srcSushi: "Sushi (GitHub Raw - Gratuit)",
      srcRyuu: "Ryuu (Anonyme - Gratuit)",
      srcHubcap: "Hubcap / Morrenus (Clé requise)",
      apiKey: "Clé API Morrenus / Hubcap",
      maintenance: "Maintenance",
      repairBtn: "🧹 Réparer la bibliothèque Steam",
      restartBtn: "↻ Redémarrer Steam",
      managedGames: "Jeux gérés dans la bibliothèque",
      loadingGames: "Chargement des jeux...",
      noGames: "Aucun jeu géré trouvé.",
      installed: "Installé",
      remove: "Supprimer",
      close: "Fermer",
      save: "Enregistrer les paramètres",
      saving: "Enregistrement...",
      saved: "✓ Paramètres enregistrés avec succès !",
      saveError: "Erreur lors de l'enregistrement des paramètres.",
      cleaning: "Réparation de la bibliothèque Steam...",
      cleaned: "✓ Bibliothèque Steam réparée avec succès !",
      restarting: "Redémarrage de Steam...",
      removedGame: "{name} retiré de MacLua.",
      removeError: "Erreur lors de la suppression du jeu.",
      addBtn: "Ajouter avec MacLua",
      adding: "Ajout en cours...",
      addedBtn: "✓ Ajouté avec MacLua",
      playBtn: "▶ Jouer avec MacLua",
      removeBtnHeader: "✕ Supprimer de MacLua",
      removing: "Suppression...",
      addedToast: "Jeu ajouté avec succès{src} ! Redémarrez Steam pour le voir dans la bibliothèque.",
      alreadyAddedToast: "Jeu déjà ajouté à MacLua. Vous pouvez l'installer depuis la bibliothèque Steam !",
      restartHeaderBtn: "↻ Redémarrer Steam",
      updateGame: "Mettre à jour",
      updatingGame: "Mise à jour...",
      updatedToast: "✓ Mise à jour in-place démarrée pour {name} !",
    }
  };

  function getLang() {
    try {
      return localStorage.getItem("maclua_lang") || "en";
    } catch (e) {
      return "en";
    }
  }

  function setLang(lang) {
    try {
      localStorage.setItem("maclua_lang", lang);
    } catch (e) {}
  }

  function t(key, vars = {}) {
    const lang = getLang();
    const dict = I18N[lang] || I18N.en;
    let str = dict[key] || I18N.en[key] || key;
    for (const [k, v] of Object.entries(vars)) {
      str = str.replace(new RegExp(`\\{${k}\\}`, "g"), v);
    }
    return str;
  }

  // 3. Modal Impostazioni Semplice & Completo
  async function openSettingsModal() {
    let overlay = document.getElementById("maclua-settings-overlay");
    if (overlay) {
      overlay.remove();
    }

    overlay = document.createElement("div");
    overlay.id = "maclua-settings-overlay";
    overlay.className = "maclua-modal-overlay";

    const curLang = getLang();

    overlay.innerHTML = `
      <div class="maclua-modal-content">
        <div class="maclua-modal-header">
          <div class="maclua-modal-title">
            <img src="${MACLUA_ICON_B64}" class="maclua-title-logo" alt="Logo" />
            <span>${t("title")}</span>
          </div>
          <button class="maclua-modal-close" id="maclua-modal-close">✕</button>
        </div>

        <div class="maclua-modal-body">
          <!-- Scelta Lingua / Language Selection -->
          <div class="maclua-setting-group">
            <label class="maclua-setting-label">${t("language")}</label>
            <select id="maclua-cfg-lang" class="maclua-select">
              <option value="en" ${curLang === "en" ? "selected" : ""}>English</option>
              <option value="it" ${curLang === "it" ? "selected" : ""}>Italiano</option>
              <option value="de" ${curLang === "de" ? "selected" : ""}>Deutsch</option>
              <option value="es" ${curLang === "es" ? "selected" : ""}>Español</option>
              <option value="fr" ${curLang === "fr" ? "selected" : ""}>Français</option>
            </select>
          </div>

          <!-- Scelta Database / Sorgente (senza snake_case, senza stile LuaTools, senza sottotitoli) -->
          <div class="maclua-setting-group">
            <label class="maclua-setting-label">${t("sources")}</label>
            <select id="maclua-cfg-source" class="maclua-select">
              <option value="auto">${t("srcAuto")}</option>
              <option value="sushi">${t("srcSushi")}</option>
              <option value="ryuu">${t("srcRyuu")}</option>
              <option value="hubcap">${t("srcHubcap")}</option>
            </select>
          </div>

          <!-- Chiave API Hubcap (senza sottotitoli) -->
          <div class="maclua-setting-group">
            <label class="maclua-setting-label">${t("apiKey")}</label>
            <input type="password" id="maclua-cfg-key" class="maclua-input" placeholder="smm_..." autocomplete="off" />
          </div>

          <!-- Azioni di Manutenzione (senza testi descrittivi ridondanti) -->
          <div class="maclua-setting-group">
            <label class="maclua-setting-label">${t("maintenance")}</label>
            <div class="maclua-actions-row">
              <button id="maclua-act-cleanup" class="maclua-btn maclua-btn-secondary">
                ${t("repairBtn")}
              </button>
              <button id="maclua-act-restart" class="maclua-btn maclua-btn-secondary">
                ${t("restartBtn")}
              </button>
            </div>
          </div>

          <!-- Libreria Gestita -->
          <div class="maclua-setting-group">
            <label class="maclua-setting-label">${t("managedGames")}</label>
            <div id="maclua-managed-list" class="maclua-managed-list">
              <div style="color: #94a3b8; padding: 6px; font-size: 12px;">${t("loadingGames")}</div>
            </div>
          </div>
        </div>

        <div class="maclua-modal-footer">
          <button id="maclua-btn-cancel" class="maclua-btn maclua-btn-cancel">${t("close")}</button>
          <button id="maclua-btn-save" class="maclua-btn maclua-btn-primary">${t("save")}</button>
        </div>
      </div>
    `;

    document.body.appendChild(overlay);

    const close = () => {
      if (overlay) overlay.remove();
    };

    overlay.querySelector("#maclua-modal-close").onclick = close;
    overlay.querySelector("#maclua-btn-cancel").onclick = close;
    overlay.onclick = (e) => {
      if (e.target === overlay) close();
    };

    const srcSel = overlay.querySelector("#maclua-cfg-source");
    const keyInp = overlay.querySelector("#maclua-cfg-key");
    const langSel = overlay.querySelector("#maclua-cfg-lang");

    langSel.onchange = () => {
      const selected = langSel.value;
      setLang(selected);
      const prevSource = srcSel.value;
      const prevKey = keyInp.value;
      openSettingsModal().then(() => {
        const newOverlay = document.getElementById("maclua-settings-overlay");
        if (newOverlay) {
          const newSrc = newOverlay.querySelector("#maclua-cfg-source");
          const newKey = newOverlay.querySelector("#maclua-cfg-key");
          if (newSrc && prevSource) newSrc.value = prevSource;
          if (newKey && prevKey) newKey.value = prevKey;
        }
      });
    };

    function renderGames(games) {
      const listEl = overlay.querySelector("#maclua-managed-list");
      if (!listEl) return;
      if (!games || !games.length) {
        listEl.innerHTML = `<div style="color: #94a3b8; padding: 6px; font-size: 12px;">${t("noGames")}</div>`;
        return;
      }
      listEl.innerHTML = "";
      for (const g of games) {
        const item = document.createElement("div");
        item.className = "maclua-game-item";
        const installedBadge = g.installed
          ? `<span style="margin-left: 8px; font-size: 10px; color: #22c55e; font-weight: 700;">[${t("installed")}]</span>`
          : "";
        const updateBtn = g.installed
          ? `<button class="maclua-btn-update" data-aid="${g.appid}">${t("updateGame")}</button>`
          : "";
        item.innerHTML = `
          <div style="display: flex; align-items: center; min-width: 0;">
            <span class="maclua-game-item-name" title="${g.name}">${g.name}</span>
            <span class="maclua-game-item-id">(${g.appid})</span>
            ${installedBadge}
          </div>
          <div style="display: flex; align-items: center;">
            ${updateBtn}
            <button class="maclua-btn-remove" data-aid="${g.appid}">${t("remove")}</button>
          </div>
        `;
        const uBtn = item.querySelector(".maclua-btn-update");
        if (uBtn) {
          uBtn.onclick = async (e) => {
            e.preventDefault();
            uBtn.disabled = true;
            uBtn.innerText = t("updatingGame");
            showToast("MacLua", t("updatingGame"));
            const res = await api("/update", "POST", { appid: g.appid });
            if (res && res.ok) {
              showToast("MacLua", t("updatedToast", { name: g.name }));
            }
            setTimeout(() => { refreshLibrary(); }, 3000);
          };
        }
        item.querySelector(".maclua-btn-remove").onclick = async (e) => {
          e.preventDefault();
          const aid = g.appid;
          item.style.opacity = "0.5";
          const rem = await api("/remove", "POST", { appid: aid });
          if (rem && rem.ok) {
            showToast("MacLua", t("removedGame", { name: g.name }));
            refreshLibrary();
          } else {
            item.style.opacity = "1";
            showToast("MacLua", t("removeError"));
          }
        };
        listEl.appendChild(item);
      }
    }

    if (window.__MACLUA && Array.isArray(window.__MACLUA.initialGames) && window.__MACLUA.initialGames.length > 0) {
      renderGames(window.__MACLUA.initialGames);
    }

    async function refreshLibrary() {
      const libRes = await api("/library");
      const games = (libRes && libRes.games) || [];
      if (window.__MACLUA) {
        window.__MACLUA.initialGames = games;
      }
      renderGames(games);
    }
    refreshLibrary();

    api("/settings").then((cfgRes) => {
      const cfg = (cfgRes && (cfgRes.settings || cfgRes)) || {};
      if (cfg.preferred_source && srcSel) srcSel.value = cfg.preferred_source;
      if (cfg.hubcap_key && keyInp) keyInp.value = cfg.hubcap_key;
    });

    overlay.querySelector("#maclua-act-cleanup").onclick = async (e) => {
      e.preventDefault();
      const btn = e.target;
      btn.disabled = true;
      btn.innerText = t("cleaning");
      const res = await api("/cleanup-manifests", "POST");
      btn.disabled = false;
      btn.innerText = t("repairBtn");
      if (res && res.ok) {
        showToast("MacLua", t("cleaned"));
        refreshLibrary();
      } else {
        showToast("MacLua", t("cleaned"));
      }
    };

    overlay.querySelector("#maclua-act-restart").onclick = async (e) => {
      e.preventDefault();
      const btn = e.target;
      btn.disabled = true;
      btn.innerText = t("restarting");
      showToast("MacLua", t("restarting"));
      close();
      await api("/restart-steam", "POST");
    };

    overlay.querySelector("#maclua-btn-save").onclick = async (e) => {
      e.preventDefault();
      const saveBtn = e.target;
      saveBtn.disabled = true;
      saveBtn.innerText = t("saving");
      const payload = {
        preferred_source: srcSel.value,
        hubcap_key: keyInp.value.trim(),
        auto_update_apps: true,
        donate_keys: false
      };
      const res = await api("/settings", "POST", payload);
      saveBtn.disabled = false;
      saveBtn.innerText = t("save");
      if (res && res.ok) {
        showToast("MacLua", t("saved"));
        close();
      } else {
        showToast("MacLua", t("saveError"));
      }
    };
  }

  // 4. Iniezione del quadratino con logo accanto al carrello (istantaneo, persistente, simmetrico)
  function ensureCartHeaderButton() {
    const cartAnchor =
      document.querySelector("a[href*='/cart']") ||
      document.getElementById("cart_link") ||
      document.getElementById("cart_status_data") ||
      document.querySelector("div[class*='cart_status']") ||
      document.querySelector("div[class*='Cart']") ||
      document.querySelector("div._1wn1lBlAzl3HMRqS1llwie") ||
      document.querySelector("div[class*='DesktopStoreHeader']") ||
      document.querySelector("div[class*='StoreHeader']") ||
      document.querySelector("div[class*='store_header']") ||
      document.querySelector("a[href*='/wishlist']") ||
      document.getElementById("wishlist_link") ||
      document.getElementById("global_action_menu");

    if (!cartAnchor) {
      return;
    }

    const parent = cartAnchor.tagName === "DIV" ? cartAnchor : cartAnchor.parentElement;
    if (!parent) {
      return;
    }

    let btn = document.getElementById("maclua-store-header-btn");
    if (!btn) {
      btn = document.createElement("button");
      btn.id = "maclua-store-header-btn";
      btn.className = "maclua-store-header-btn";
      btn.innerHTML = `<img src="${MACLUA_ICON_B64}" alt="MacLua" class="maclua-header-icon" />`;
    }

    btn.title = t("title");
    btn.setAttribute("aria-label", t("title"));
    btn.onclick = (e) => {
      e.preventDefault();
      e.stopPropagation();
      openSettingsModal();
    };

    // Assicura che il pulsante sia sempre connesso fisicamente nel DOM dentro il container del carrello
    if (!btn.isConnected || !parent.contains(btn)) {
      if (cartAnchor.tagName === "DIV") {
        cartAnchor.appendChild(btn);
      } else {
        cartAnchor.insertAdjacentElement("beforebegin", btn);
      }
    }

    // Dimensionamento e allineamento simmetrico con il blocco del carrello (mai 0px anche prima di layout completo)
    const cartStyle = window.getComputedStyle(cartAnchor);
    const measuredHeight = cartAnchor.offsetHeight || parseFloat(cartStyle.height) || 0;
    const h = (measuredHeight >= 20 && measuredHeight <= 50) ? Math.round(measuredHeight) : 32;
    btn.style.height = `${h}px`;
    btn.style.width = `${h}px`;
    btn.style.minWidth = `${h}px`;
    btn.style.minHeight = `${h}px`;
    btn.style.boxSizing = "border-box";
    btn.style.display = "inline-flex";
    btn.style.alignItems = "center";
    btn.style.justifyContent = "center";
    btn.style.alignSelf = "center";
    btn.style.verticalAlign = "middle";
    btn.style.borderRadius = (cartStyle.borderRadius && cartStyle.borderRadius !== "0px") ? cartStyle.borderRadius : "3px";
    btn.style.margin = "0 6px";
    btn.style.padding = "0";
    btn.style.transform = "none";
    btn.style.visibility = "visible";
    btn.style.opacity = "1";
  }

  window.ensureCartHeaderButton = ensureCartHeaderButton;
  window.injectStoreUI = injectStoreUI;

  function injectCartHeaderButton() {
    ensureCartHeaderButton();
  }


  // 5. Pulsante "Riavvia Steam" temporaneo nella pagina gioco
  function ensureRestartButton(headerTarget, anchorBtn) {
    let restartBtn = document.getElementById("maclua-restart-btn");
    if (!restartBtn) {
      restartBtn = document.createElement("button");
      restartBtn.id = "maclua-restart-btn";
      restartBtn.className = "maclua-header-btn restart";
      restartBtn.innerText = t("restartHeaderBtn");
      if (anchorBtn && anchorBtn.parentNode) {
        anchorBtn.insertAdjacentElement("afterend", restartBtn);
      } else if (headerTarget) {
        headerTarget.appendChild(restartBtn);
      }
    }
    restartBtn.onclick = async (e) => {
      e.preventDefault();
      restartBtn.disabled = true;
      restartBtn.innerText = t("restarting");
      showToast("MacLua", t("restarting"));
      window.__MacLuaPendingRestart = null;
      await api("/restart-steam", "POST");
    };
    return restartBtn;
  }

  function removeRestartButton() {
    const restartBtn = document.getElementById("maclua-restart-btn");
    if (restartBtn) restartBtn.remove();
  }

  function ensureRemoveButton(headerTarget, anchorBtn, appid) {
    let removeBtn = document.getElementById("maclua-remove-btn");
    if (!removeBtn) {
      removeBtn = document.createElement("button");
      removeBtn.id = "maclua-remove-btn";
      removeBtn.className = "maclua-header-btn remove";
      removeBtn.innerText = t("removeBtnHeader");
      if (anchorBtn && anchorBtn.parentNode) {
        anchorBtn.insertAdjacentElement("afterend", removeBtn);
      } else if (headerTarget) {
        headerTarget.appendChild(removeBtn);
      }
    }
    removeBtn.onclick = async (e) => {
      e.preventDefault();
      removeBtn.disabled = true;
      removeBtn.innerText = t("removing");
      const res = await api("/remove", "POST", { appid });
      if (res && res.ok) {
        showToast("MacLua", t("removedGame", { name: String(appid) }));
        if (anchorBtn) {
          anchorBtn.className = "maclua-header-btn";
          anchorBtn.innerText = t("addBtn");
          anchorBtn.dataset.status = "unmanaged";
          anchorBtn.onclick = (ev) => {
            ev.preventDefault();
            handleAddOrPlay(appid);
          };
        }
        removeRemoveButton();
        removeRestartButton();
      } else {
        removeBtn.disabled = false;
        removeBtn.innerText = t("removeBtnHeader");
        const err = res ? (res.error || t("removeError")) : t("removeError");
        showToast("MacLua", err);
      }
    };
    return removeBtn;
  }

  function removeRemoveButton() {
    const removeBtn = document.getElementById("maclua-remove-btn");
    if (removeBtn) removeBtn.remove();
  }

  // 6. Gestione click Aggiungi nella pagina gioco
  async function handleAddOrPlay(appid) {
    const btn = document.getElementById("maclua-header-btn");
    if (btn) {
      btn.classList.add("loading");
      btn.innerText = t("adding");
    }

    const res = await api("/add", "POST", { appid });
    if (res && res.ok) {
      const srcName = res.source ? ` (${res.source})` : "";
      showToast("MacLua", t("addedToast", { src: srcName }));
      window.__MacLuaPendingRestart = String(appid);
      if (btn) {
        btn.classList.remove("loading");
        btn.className = "maclua-header-btn added";
        btn.innerText = t("addedBtn");
        btn.dataset.status = "managed";
        btn.onclick = (e) => {
          e.preventDefault();
          showToast("MacLua", t("alreadyAddedToast"));
        };
        const headerTarget = document.querySelector(".apphub_OtherSiteInfo");
        removeRemoveButton();
        ensureRestartButton(headerTarget, btn);
      }
    } else {
      if (btn) {
        btn.classList.remove("loading");
        btn.className = "maclua-header-btn";
        btn.innerText = t("addBtn");
      }
      const err = res ? (res.error || t("removeError")) : "Bridge offline.";
      showToast("MacLua", err);
    }
  }

  let isInjecting = false;

  // 7. Loop di iniezione Store UI
  async function injectStoreUI() {
    if (isInjecting) return;
    isInjecting = true;

    try {
      // Inietta sempre il pulsante del menu impostazioni accanto al carrello nello store
      injectCartHeaderButton();

      // Comparire accanto a "Hub della Comunità" SOLO nelle pagine gioco (/app/<id>)
      const m = location.pathname.match(/\/app\/(\d+)/);
      const appid = m ? parseInt(m[1], 10) : null;
      if (!appid) {
        const curBtn = document.getElementById("maclua-header-btn");
        if (curBtn) curBtn.remove();
        removeRestartButton();
        removeRemoveButton();
        return;
      }

      const headerTarget = document.querySelector(".apphub_OtherSiteInfo");
      if (!headerTarget) return;

      let headerBtn = document.getElementById("maclua-header-btn");

      if (headerBtn && headerBtn.dataset.appid === String(appid) && headerTarget.contains(headerBtn) && headerBtn.dataset.status) {
        return;
      }

      if (!headerBtn) {
        headerBtn = document.createElement("button");
        headerBtn.id = "maclua-header-btn";
        headerTarget.prepend(headerBtn);
      } else if (!headerTarget.contains(headerBtn)) {
        headerTarget.prepend(headerBtn);
      }

      if (headerBtn.dataset.appid !== String(appid)) {
        headerBtn.dataset.appid = String(appid);
        delete headerBtn.dataset.status;
      }

      const info = await api(`/game/${appid}`);
      const isInstalled = Boolean(info && info.installed);
      const isManaged = Boolean(info && info.managed);

      if (isInstalled) {
        headerBtn.className = "maclua-header-btn installed";
        headerBtn.innerText = t("playBtn");
        headerBtn.dataset.status = "installed";
        headerBtn.onclick = (e) => {
          e.preventDefault();
          location.href = `steam://run/${appid}`;
        };
        removeRestartButton();
        removeRemoveButton();
      } else if (isManaged) {
        headerBtn.className = "maclua-header-btn added";
        headerBtn.innerText = t("addedBtn");
        headerBtn.dataset.status = "managed";
        headerBtn.onclick = (e) => {
          e.preventDefault();
          showToast("MacLua", t("alreadyAddedToast"));
        };
        if (window.__MacLuaPendingRestart === String(appid)) {
          ensureRestartButton(headerTarget, headerBtn);
          removeRemoveButton();
        } else {
          removeRestartButton();
          ensureRemoveButton(headerTarget, headerBtn, appid);
        }
      } else {
        headerBtn.className = "maclua-header-btn";
        headerBtn.innerText = t("addBtn");
        headerBtn.dataset.status = "unmanaged";
        headerBtn.onclick = (e) => {
          e.preventDefault();
          handleAddOrPlay(appid);
        };
        removeRestartButton();
        removeRemoveButton();
      }
    } finally {
      isInjecting = false;
    }
  }

  let throttleTimer = null;
  function triggerInjectThrottled() {
    if (throttleTimer) return;
    throttleTimer = setTimeout(() => {
      throttleTimer = null;
      injectStoreUI();
    }, 200);
  }

  function init() {
    ensureCartHeaderButton();
    injectStoreUI();

    if (window.__MacLuaObserver) {
      window.__MacLuaObserver.disconnect();
    }
    if (window.__MacLuaInterval) {
      clearInterval(window.__MacLuaInterval);
    }
    if (window.__MacLuaFastInterval) {
      clearInterval(window.__MacLuaFastInterval);
    }

    // Ascolta cambi finestra, focus e tab per mostrare istantaneamente il blocchetto
    window.addEventListener("focus", ensureCartHeaderButton);
    window.addEventListener("blur", ensureCartHeaderButton);
    document.addEventListener("visibilitychange", ensureCartHeaderButton);
    window.addEventListener("pageshow", ensureCartHeaderButton);
    window.addEventListener("popstate", () => {
      ensureCartHeaderButton();
      triggerInjectThrottled();
    });

    const observer = new MutationObserver((mutations) => {
      for (const m of mutations) {
        if (m.target && m.target.id && m.target.id.startsWith("maclua-")) return;
      }
      // Verifica e inietta istantaneamente il quadratino a latenza zero
      ensureCartHeaderButton();
      triggerInjectThrottled();
    });

    observer.observe(document.documentElement, {
      childList: true,
      subtree: true,
    });
    window.__MacLuaObserver = observer;

    const origPush = history.pushState;
    if (origPush && !window.__MacLuaPushStatePatched) {
      window.__MacLuaPushStatePatched = true;
      history.pushState = function () {
        origPush.apply(this, arguments);
        ensureCartHeaderButton();
        triggerInjectThrottled();
      };
    }

    // Battito ad alta frequenza (40ms) per i primi 3 secondi mentre React idrata la pagina
    let fastTicks = 0;
    window.__MacLuaFastInterval = setInterval(() => {
      ensureCartHeaderButton();
      fastTicks++;
      if (fastTicks > 75) {
        clearInterval(window.__MacLuaFastInterval);
      }
    }, 40);

    // Controllo periodico regolare
    window.__MacLuaInterval = setInterval(() => {
      ensureCartHeaderButton();
      triggerInjectThrottled();
    }, 400);
  }

  // Esegui init immediatamente (funziona anche a inizio parsing grazie a document.documentElement)
  init();
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      ensureCartHeaderButton();
      injectStoreUI();
    });
  }

  window.__MacLuaVersion = 9;
  window.__MacLuaReady = true;
})();
