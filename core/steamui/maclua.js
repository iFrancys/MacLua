/**
 * MacLua in-Steam Injected Client UI
 * Inietta un singolo pulsante pulito accanto a "Hub della Comunità" esclusivamente sulle pagine dello Store dei giochi.
 * Non interferisce MAI con la Libreria di Steam.
 * Usa il canale bidirezionale CDP RPC per comunicare stabilmente con MacLua senza blocchi di mixed-content.
 */
(function () {
  // Ignora qualsiasi pagina che non sia lo Store di Steam (inclusa la Libreria steamloopback.host)
  if (typeof location !== "undefined" && location.hostname !== "store.steampowered.com") {
    return;
  }

  window.__MacLuaRPC = window.__MacLuaRPC || { id: 0, pending: {}, responses: {} };

  // 1. Rimozione immediata di vecchi overlay non desiderati
  function cleanupOldOverlays() {
    const floatBar = document.getElementById("maclua-floating-bar");
    if (floatBar) floatBar.remove();
    const storeAction = document.getElementById("maclua-store-action");
    if (storeAction) storeAction.remove();
    const modal = document.getElementById("maclua-modal");
    if (modal) modal.remove();
  }
  cleanupOldOverlays();

  // 2. Comunicazione infallibile tramite CDP RPC
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

  // 3. Notifiche Toast
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

  // 4. Gestione pulsanti Riavvia Steam e Rimuovi da MacLua
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

  // 5. Gestione click Aggiungi
  async function handleAddOrPlay(appid) {
    const btn = document.getElementById("maclua-header-btn");
    if (btn) {
      btn.classList.add("loading");
      btn.innerText = "Aggiunta in corso...";
    }

    const res = await api("/add", "POST", { appid });
    if (res && res.ok) {
      showToast("MacLua", "Gioco aggiunto con successo! Clicca 'Riavvia Steam' a fianco per vederlo nella Libreria.");
      window.__MacLuaPendingRestart = String(appid);
      if (btn) {
        btn.classList.remove("loading");
        btn.className = "maclua-header-btn added";
        btn.innerText = "✓ Aggiunto con MacLua";
        btn.dataset.status = "managed";
        btn.onclick = (e) => {
          e.preventDefault();
          showToast("MacLua", "Gioco già aggiunto! Riavvia Steam per vederlo nella Libreria.");
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

  // 6. Iniezione del singolo bottone pulito accanto a "Hub della Comunità"
  async function injectStoreUI() {
    if (isInjecting) return;
    isInjecting = true;

    try {
      cleanupOldOverlays();

      // Comparire SOLO ed esclusivamente nelle pagine dello Store di un gioco (/app/<id>)
      const m = location.pathname.match(/\/app\/(\d+)/);
      const appid = m ? parseInt(m[1], 10) : null;
      if (!appid) {
        // Fuori dalle pagine dei giochi, pulisci qualsiasi pulsante
        const curBtn = document.getElementById("maclua-header-btn");
        if (curBtn) curBtn.remove();
        removeRestartButton();
        removeRemoveButton();
        return;
      }

      // Bersaglio: ESCLUSIVAMENTE accanto a "Hub della Comunità" (.apphub_OtherSiteInfo)
      const headerTarget = document.querySelector(".apphub_OtherSiteInfo");
      if (!headerTarget) return;

      let headerBtn = document.getElementById("maclua-header-btn");

      // Se il bottone esiste già per questo appid e ha già uno stato assegnato, non spammare richieste
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

      // Interroga lo stato del gioco nel bridge
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

  function init() {
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

  window.__MacLuaVersion = 3;
  window.__MacLuaReady = true;
})();
