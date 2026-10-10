/**
 * MacLua in-Steam Injected Client UI
 * - Inietta un quadratino con il logo di MacLua affianco al blocco del carrello nello Store di Steam.
 * - Cliccando il quadratino si apre un popup di impostazioni completo (scelta database, chiave Morrenus, auto-update, riparazione manifest, libreria).
 * - Sulle pagine /app/<id> inietta il pulsante pulito "Aggiungi con MacLua" / "Gioca con MacLua" accanto a "Hub della Comunità".
 * - Usa il canale bidirezionale CDP RPC per comunicare stabilmente con MacLua senza blocchi di mixed-content.
 */
(function () {
  const isStore = typeof location !== "undefined" && location.hostname === "store.steampowered.com";
  const isLibrary = typeof location !== "undefined" && (location.hostname === "steamloopback.host" || location.hostname === "localhost");

  if (!isStore && !isLibrary) {
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

  // 3. Modal Impostazioni Semplice & Completo (Stile LuaTools)
  async function openSettingsModal() {
    let overlay = document.getElementById("maclua-settings-overlay");
    if (overlay) {
      overlay.remove();
    }

    overlay = document.createElement("div");
    overlay.id = "maclua-settings-overlay";
    overlay.className = "maclua-modal-overlay";

    overlay.innerHTML = `
      <div class="maclua-modal-content">
        <div class="maclua-modal-header">
          <div class="maclua-modal-title">
            <img src="${MACLUA_ICON_B64}" class="maclua-title-logo" alt="Logo" />
            <span>MacLua — Impostazioni</span>
          </div>
          <button class="maclua-modal-close" id="maclua-modal-close">✕</button>
        </div>

        <div class="maclua-modal-body">
          <!-- Scelta Database / Sorgente -->
          <div class="maclua-setting-group">
            <label class="maclua-setting-label">Database & Sorgenti Manifest (stile LuaTools)</label>
            <div class="maclua-setting-desc">Seleziona la sorgente per scaricare file Lua e manifest:</div>
            <select id="maclua-cfg-source" class="maclua-select">
              <option value="auto">Auto (Sushi ➔ Ryuu ➔ Hubcap) [Consigliato]</option>
              <option value="sushi">Sushi (GitHub Raw — 100% Gratuito, nessuna chiave)</option>
              <option value="ryuu">Ryuu (Anonimo — Gratuito, nessuna chiave)</option>
              <option value="hubcap">Hubcap / Morrenus (Richiede chiave API)</option>
            </select>
          </div>

          <!-- Chiave API Hubcap -->
          <div class="maclua-setting-group">
            <label class="maclua-setting-label">Chiave API Morrenus / Hubcap (Opzionale)</label>
            <div class="maclua-setting-desc">Necessaria solo se usi Hubcap. Non è richiesta per Sushi o Ryuu.</div>
            <input type="password" id="maclua-cfg-key" class="maclua-input" placeholder="smm_..." autocomplete="off" />
          </div>

          <!-- Opzioni Switch -->
          <div class="maclua-setting-group maclua-toggles">
            <label class="maclua-toggle-item">
              <input type="checkbox" id="maclua-cfg-autoupdate" checked />
              <span class="maclua-toggle-text">
                <strong>Auto-Update Giochi (Aggiorna automaticamente i manifest)</strong>
                <small>Sblocca i manifest bloccati nei file Lua per consentire a Steam di scaricare sempre l'ultima build disponibile.</small>
              </span>
            </label>
            <label class="maclua-toggle-item">
              <input type="checkbox" id="maclua-cfg-donate" />
              <span class="maclua-toggle-text">
                <strong>Dona manifest e chiavi</strong>
                <small>Condividi anonimamente i manifest con la community.</small>
              </span>
            </label>
          </div>

          <!-- Azioni di Manutenzione -->
          <div class="maclua-setting-group">
            <label class="maclua-setting-label">Manutenzione & Riparazione Libreria</label>
            <div class="maclua-actions-row">
              <button id="maclua-act-cleanup" class="maclua-btn maclua-btn-secondary">
                🧹 Ripara Visualizzazione Steam
              </button>
              <button id="maclua-act-restart" class="maclua-btn maclua-btn-secondary">
                ↻ Riavvia Steam
              </button>
            </div>
            <small style="color: #94a3b8; display: block; margin-top: 4px;">
              Rimuove gli appmanifest fantasma a 0 byte che causano la scritta 'DOWNLOAD RICHIESTO' e ripristina il classico tasto 'INSTALLA'.
            </small>
          </div>

          <!-- Libreria Gestita -->
          <div class="maclua-setting-group">
            <label class="maclua-setting-label">Giochi Gestiti nella Libreria</label>
            <div id="maclua-managed-list" class="maclua-managed-list">
              <div style="color: #94a3b8; padding: 6px; font-size: 12px;">Caricamento giochi...</div>
            </div>
          </div>
        </div>

        <div class="maclua-modal-footer">
          <button id="maclua-btn-cancel" class="maclua-btn maclua-btn-cancel">Chiudi</button>
          <button id="maclua-btn-save" class="maclua-btn maclua-btn-primary">Salva Impostazioni</button>
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

    // Carica impostazioni attuali dal bridge
    const cfgRes = await api("/settings");
    const cfg = (cfgRes && (cfgRes.settings || cfgRes)) || {};

    const srcSel = overlay.querySelector("#maclua-cfg-source");
    if (cfg.preferred_source) srcSel.value = cfg.preferred_source;

    const keyInp = overlay.querySelector("#maclua-cfg-key");
    if (cfg.hubcap_key) keyInp.value = cfg.hubcap_key;

    const autoUpChk = overlay.querySelector("#maclua-cfg-autoupdate");
    autoUpChk.checked = cfg.auto_update_apps !== false;

    const donateChk = overlay.querySelector("#maclua-cfg-donate");
    donateChk.checked = Boolean(cfg.donate_keys);

    // Carica lista giochi gestiti
    async function refreshLibrary() {
      const listEl = overlay.querySelector("#maclua-managed-list");
      const libRes = await api("/library");
      const games = (libRes && libRes.games) || [];
      if (!games.length) {
        listEl.innerHTML = `<div style="color: #94a3b8; padding: 6px; font-size: 12px;">Nessun gioco gestito in stplug-in.</div>`;
        return;
      }
      listEl.innerHTML = "";
      for (const g of games) {
        const item = document.createElement("div");
        item.className = "maclua-game-item";
        item.innerHTML = `
          <div style="display: flex; align-items: center; min-width: 0;">
            <span class="maclua-game-item-name" title="${g.name}">${g.name}</span>
            <span class="maclua-game-item-id">(${g.appid})</span>
            ${g.installed ? '<span style="margin-left: 8px; font-size: 10px; color: #22c55e; font-weight: 700;">[Installato]</span>' : ''}
          </div>
          <button class="maclua-btn-remove" data-aid="${g.appid}">Rimuovi</button>
        `;
        item.querySelector(".maclua-btn-remove").onclick = async (e) => {
          e.preventDefault();
          const aid = g.appid;
          item.style.opacity = "0.5";
          const rem = await api("/remove", "POST", { appid: aid });
          if (rem && rem.ok) {
            showToast("MacLua", `Rimosso ${g.name} da MacLua.`);
            refreshLibrary();
          } else {
            item.style.opacity = "1";
            showToast("MacLua", "Errore durante la rimozione.");
          }
        };
        listEl.appendChild(item);
      }
    }
    refreshLibrary();

    // Bottone Ripara Manifest
    overlay.querySelector("#maclua-act-cleanup").onclick = async (e) => {
      e.preventDefault();
      const btn = e.target;
      btn.disabled = true;
      btn.innerText = "Pulizia in corso...";
      const res = await api("/cleanup-manifests", "POST");
      btn.disabled = false;
      btn.innerText = "🧹 Ripara Visualizzazione Steam";
      if (res && res.ok) {
        const count = res.count !== undefined ? res.count : (res.cleaned || []).length;
        showToast("MacLua", `✓ Rimossi ${count} manifest fantasma! Visualizzazione classica ripristinata.`);
        refreshLibrary();
      } else {
        showToast("MacLua", "Pulizia completata.");
      }
    };

    // Bottone Riavvia Steam
    overlay.querySelector("#maclua-act-restart").onclick = async (e) => {
      e.preventDefault();
      const btn = e.target;
      btn.disabled = true;
      btn.innerText = "Riavvio...";
      showToast("MacLua", "Riavvio di Steam in corso...");
      close();
      await api("/restart-steam", "POST");
    };

    // Bottone Salva Impostazioni
    overlay.querySelector("#maclua-btn-save").onclick = async (e) => {
      e.preventDefault();
      const saveBtn = e.target;
      saveBtn.disabled = true;
      saveBtn.innerText = "Salvataggio...";
      const payload = {
        preferred_source: srcSel.value,
        hubcap_key: keyInp.value.trim(),
        auto_update_apps: autoUpChk.checked,
        donate_keys: donateChk.checked
      };
      const res = await api("/settings", "POST", payload);
      saveBtn.disabled = false;
      saveBtn.innerText = "Salva Impostazioni";
      if (res && res.ok) {
        showToast("MacLua", "✓ Impostazioni salvate con successo!");
        close();
      } else {
        showToast("MacLua", "Errore durante il salvataggio.");
      }
    };
  }

  // 4. Iniezione del quadratino con logo accanto al carrello
  function injectCartHeaderButton() {
    // Cerca il blocco carrello o elementi limitrofi nello Store di Steam
    const cartLink =
      document.getElementById("cart_link") ||
      document.querySelector("a[href*='/cart']") ||
      document.getElementById("cart_status_data") ||
      document.querySelector("div[class*='cart_status']") ||
      document.querySelector("div[class*='Cart']") ||
      document.querySelector("div._1wn1lBlAzl3HMRqS1llwie");

    const cartAnchor =
      cartLink ||
      document.getElementById("wishlist_link") ||
      document.querySelector("a[href*='/wishlist']");

    if (!cartAnchor) {
      return;
    }

    let btn = document.getElementById("maclua-store-header-btn");

    function alignBtn() {
      if (!btn || !cartAnchor) return;
      const cartStyle = window.getComputedStyle(cartAnchor);
      const h = Math.round(cartAnchor.offsetHeight || parseFloat(cartStyle.height) || 32);
      btn.style.height = `${h}px`;
      btn.style.width = `${h}px`;
      btn.style.minWidth = `${h}px`;
      btn.style.minHeight = `${h}px`;
      btn.style.maxHeight = `${h}px`;
      btn.style.boxSizing = "border-box";
      btn.style.display = "inline-flex";
      btn.style.alignItems = "center";
      btn.style.justifyContent = "center";
      btn.style.alignSelf = cartStyle.alignSelf || "center";
      btn.style.verticalAlign = cartStyle.verticalAlign || "middle";
      btn.style.borderRadius = cartStyle.borderRadius || "3px";
      btn.style.margin = "0 8px";
      btn.style.padding = "0";

      // Allineamento verticale perfetto: confronta i bounding client rect
      const cartRect = cartAnchor.getBoundingClientRect();
      const btnRect = btn.getBoundingClientRect();
      if (cartRect.height > 0 && btnRect.height > 0) {
        const diff = Math.round(cartRect.top - btnRect.top);
        if (Math.abs(diff) >= 1) {
          btn.style.transform = `translateY(${diff}px)`;
        } else {
          btn.style.transform = "";
        }
      }
    }

    if (btn) {
      alignBtn();
      return;
    }

    btn = document.createElement("button");
    btn.id = "maclua-store-header-btn";
    btn.className = "maclua-store-header-btn";
    btn.title = "Impostazioni MacLua (Database, Chiavi, Auto-Update)";
    btn.setAttribute("aria-label", "Impostazioni MacLua");
    btn.innerHTML = `<img src="${MACLUA_ICON_B64}" alt="MacLua" class="maclua-header-icon" />`;

    btn.onclick = (e) => {
      e.preventDefault();
      e.stopPropagation();
      openSettingsModal();
    };

    // Inserimento prima del link/blocco carrello come elemento gemello diretto
    if (cartAnchor.parentElement) {
      cartAnchor.insertAdjacentElement("beforebegin", btn);
    }

    alignBtn();
    requestAnimationFrame(alignBtn);
    setTimeout(alignBtn, 150);
  }

  // 5. Pulsante "Riavvia Steam" temporaneo nella pagina gioco
  function ensureRestartButton(headerTarget, anchorBtn) {
    let restartBtn = document.getElementById("maclua-restart-btn");
    if (!restartBtn) {
      restartBtn = document.createElement("button");
      restartBtn.id = "maclua-restart-btn";
      restartBtn.className = "maclua-header-btn restart";
      restartBtn.innerText = "↻ Riavvia Steam";
      if (anchorBtn && anchorBtn.parentNode) {
        anchorBtn.insertAdjacentElement("afterend", restartBtn);
      } else if (headerTarget) {
        headerTarget.appendChild(restartBtn);
      }
    }
    restartBtn.onclick = async (e) => {
      e.preventDefault();
      restartBtn.disabled = true;
      restartBtn.innerText = "Riavvio in corso...";
      showToast("MacLua", "Riavvio di Steam in corso... Riapertura a breve.");
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
      removeBtn.innerText = "✕ Rimuovi da MacLua";
      if (anchorBtn && anchorBtn.parentNode) {
        anchorBtn.insertAdjacentElement("afterend", removeBtn);
      } else if (headerTarget) {
        headerTarget.appendChild(removeBtn);
      }
    }
    removeBtn.onclick = async (e) => {
      e.preventDefault();
      removeBtn.disabled = true;
      removeBtn.innerText = "Rimozione...";
      const res = await api("/remove", "POST", { appid });
      if (res && res.ok) {
        showToast("MacLua", "Gioco rimosso con successo da MacLua.");
        if (anchorBtn) {
          anchorBtn.className = "maclua-header-btn";
          anchorBtn.innerText = "Aggiungi con MacLua";
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
        removeBtn.innerText = "✕ Rimuovi da MacLua";
        const err = res ? (res.error || "Errore durante la rimozione") : "Errore.";
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
      btn.innerText = "Aggiunta in corso...";
    }

    const res = await api("/add", "POST", { appid });
    if (res && res.ok) {
      const srcName = res.source ? ` (${res.source})` : "";
      showToast("MacLua", `Gioco aggiunto con successo${srcName}! Riavvia Steam per vederlo nella Libreria con il tasto 'INSTALLA'.`);
      window.__MacLuaPendingRestart = String(appid);
      if (btn) {
        btn.classList.remove("loading");
        btn.className = "maclua-header-btn added";
        btn.innerText = "✓ Aggiunto con MacLua";
        btn.dataset.status = "managed";
        btn.onclick = (e) => {
          e.preventDefault();
          showToast("MacLua", "Gioco già aggiunto! Riavvia Steam per vederlo nella Libreria con il tasto 'INSTALLA'.");
        };
        const headerTarget = document.querySelector(".apphub_OtherSiteInfo");
        removeRemoveButton();
        ensureRestartButton(headerTarget, btn);
      }
    } else {
      if (btn) {
        btn.classList.remove("loading");
        btn.className = "maclua-header-btn";
        btn.innerText = "Aggiungi con MacLua";
      }
      const err = res ? (res.error || "Errore durante l'aggiunta") : "Bridge offline.";
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
        headerBtn.innerText = "▶ Gioca con MacLua";
        headerBtn.dataset.status = "installed";
        headerBtn.onclick = (e) => {
          e.preventDefault();
          location.href = `steam://run/${appid}`;
        };
        removeRestartButton();
        removeRemoveButton();
      } else if (isManaged) {
        headerBtn.className = "maclua-header-btn added";
        headerBtn.innerText = "✓ Aggiunto con MacLua";
        headerBtn.dataset.status = "managed";
        headerBtn.onclick = (e) => {
          e.preventDefault();
          showToast("MacLua", "Gioco già aggiunto a MacLua. Puoi scaricarlo direttamente dalla Libreria di Steam!");
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
        headerBtn.innerText = "Aggiungi con MacLua";
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

  // 7. Sincronizzazione Libreria Steam (steamloopback.host / SharedJSContext)
  async function syncManagedLibrary(gamesList = null) {
    try {
      let games = gamesList;
      if (!games) {
        const res = await api("/library");
        if (res && res.ok && Array.isArray(res.games)) {
          games = res.games;
        }
      }
      if (!Array.isArray(games)) return;

      const managedAppIds = new Set(games.map((g) => Number(g.appid)).filter(Boolean));

      // 1. Aggiorna appStore.m_mapApps
      if (typeof appStore !== "undefined" && appStore.m_mapApps) {
        for (const aid of managedAppIds) {
          const appObj = appStore.m_mapApps.get(aid);
          if (appObj) {
            appObj.visible_in_game_list = true;
          }
        }
      }

      // 2. Aggiorna collectionStore.uncategorizedCollection
      if (typeof collectionStore !== "undefined" && collectionStore.uncategorizedCollection) {
        const unc = collectionStore.uncategorizedCollection;
        if (unc && unc.m_rgApps && typeof unc.SetApps === "function") {
          let updated = false;
          const currentList = Array.from(unc.m_rgApps);
          for (const aid of managedAppIds) {
            if (!currentList.includes(aid)) {
              currentList.push(aid);
              updated = true;
            }
          }
          if (updated) {
            unc.SetApps(currentList);
          }
        }
      }
    } catch (e) {
      console.warn("[MacLua] Errore sync libreria:", e);
    }
  }

  window.__MacLuaSyncLibrary = syncManagedLibrary;

  function initLibrarySync() {
    if (!isLibrary) return;
    syncManagedLibrary();
    if (window.__MacLuaLibraryInterval) {
      clearInterval(window.__MacLuaLibraryInterval);
    }
    window.__MacLuaLibraryInterval = setInterval(() => syncManagedLibrary(), 4000);
  }

  function init() {
    if (isLibrary) {
      initLibrarySync();
      return;
    }

    injectStoreUI();

    if (window.__MacLuaObserver) {
      window.__MacLuaObserver.disconnect();
    }
    if (window.__MacLuaInterval) {
      clearInterval(window.__MacLuaInterval);
    }

    const observer = new MutationObserver((mutations) => {
      for (const m of mutations) {
        if (m.target && m.target.id && m.target.id.startsWith("maclua-")) return;
      }
      triggerInjectThrottled();
    });

    observer.observe(document.body || document.documentElement, {
      childList: true,
      subtree: true,
    });
    window.__MacLuaObserver = observer;

    window.addEventListener("popstate", triggerInjectThrottled);

    const origPush = history.pushState;
    if (origPush && !window.__MacLuaPushStatePatched) {
      window.__MacLuaPushStatePatched = true;
      history.pushState = function () {
        origPush.apply(this, arguments);
        triggerInjectThrottled();
      };
    }

    window.__MacLuaInterval = setInterval(triggerInjectThrottled, 2000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  window.__MacLuaVersion = 4;
  window.__MacLuaReady = true;
})();
