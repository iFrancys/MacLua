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
