//! Persistent Chrome DevTools Protocol (CDP) WebSocket client for Steam CEF on port 8080.
//!
//! Replaces tab polling with persistent WebSocket connections and `Runtime.addBinding`
//! ("sendToMacLua"), providing event-driven push communication without polling overhead.

use futures_util::{SinkExt, StreamExt};
use serde::{Deserialize, Serialize};
use tokio_tungstenite::connect_async;
use tokio_tungstenite::tungstenite::Message;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CdpTab {
    pub id: String,
    pub title: String,
    pub url: String,
    #[serde(rename = "webSocketDebuggerUrl")]
    pub ws_url: Option<String>,
}

#[derive(Debug, thiserror::Error)]
pub enum CdpError {
    #[error("HTTP error fetching tab list: {0}")]
    Http(#[from] reqwest::Error),
    #[error("WebSocket error: {0}")]
    Ws(#[from] tokio_tungstenite::tungstenite::Error),
    #[error("no store or library tabs found on port 8080")]
    NoMatchingTabs,
}

/// Fetches list of open CEF browser tabs from `http://127.0.0.1:8080/json`.
pub async fn fetch_tabs(client: &reqwest::Client) -> Result<Vec<CdpTab>, CdpError> {
    let url = "http://127.0.0.1:8080/json";
    let res = client.get(url).send().await?;
    let tabs: Vec<CdpTab> = res.json().await?;
    Ok(tabs)
}

/// Connects persistent WebSocket to a CEF tab, registers `Runtime.addBinding("sendToMacLua")`,
/// and injects the MacLua UI assets into Steam Store tabs.
pub async fn attach_tab(ws_url: &str, injected_script: &str) -> Result<(), CdpError> {
    let (mut ws_stream, _) = connect_async(ws_url).await?;

    // 1. Enable Runtime
    let enable_cmd = serde_json::json!({
        "id": 1,
        "method": "Runtime.enable"
    });
    ws_stream.send(Message::Text(enable_cmd.to_string())).await?;

    // 2. Add native binding `sendToMacLua` so JS can call `window.sendToMacLua(data)`
    let add_binding_cmd = serde_json::json!({
        "id": 2,
        "method": "Runtime.addBinding",
        "params": {
            "name": "sendToMacLua"
        }
    });
    ws_stream.send(Message::Text(add_binding_cmd.to_string())).await?;

    // 3. Inject MacLua JS into current document
    let eval_cmd = serde_json::json!({
        "id": 3,
        "method": "Runtime.evaluate",
        "params": {
            "expression": injected_script,
            "userGesture": true
        }
    });
    ws_stream.send(Message::Text(eval_cmd.to_string())).await?;

    // 4. Register Page.addScriptToEvaluateOnNewDocument so CEF automatically executes MacLua JS on every new document/navigation
    let page_enable = serde_json::json!({
        "id": 4,
        "method": "Page.enable"
    });
    let _ = ws_stream.send(Message::Text(page_enable.to_string())).await;

    let new_doc_cmd = serde_json::json!({
        "id": 5,
        "method": "Page.addScriptToEvaluateOnNewDocument",
        "params": {
            "source": injected_script
        }
    });
    let _ = ws_stream.send(Message::Text(new_doc_cmd.to_string())).await;

    // Listen for incoming events asynchronously in background task
    tokio::spawn(async move {
        while let Some(msg) = ws_stream.next().await {
            if let Ok(Message::Text(text)) = msg {
                if let Ok(v) = serde_json::from_str::<serde_json::Value>(&text) {
                    if v.get("method").and_then(|m| m.as_str()) == Some("Runtime.bindingCalled") {
                        if let Some(params) = v.get("params") {
                            if params.get("name").and_then(|n| n.as_str()) == Some("sendToMacLua") {
                                if let Some(payload_str) = params.get("payload").and_then(|p| p.as_str()) {
                                    tracing::info!("Received push event from Steam Store tab: {}", payload_str);
                                }
                            }
                        }
                    }
                }
            }
        }
    });

    Ok(())
}
