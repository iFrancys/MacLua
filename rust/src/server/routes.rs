//! HTTP REST and SSE route handlers for MacLua bridge.

use std::sync::Arc;
use std::time::Duration;
use axum::{
    extract::{Path as AxumPath, Query, State},
    response::{
        sse::{Event, KeepAlive, Sse},
        IntoResponse, Json,
    },
    http::StatusCode,
};
use futures_util::stream::Stream;
use serde::Deserialize;
use tokio_stream::StreamExt as _;

use crate::engine::catalog;
use crate::storage::db::Database;
use crate::util::paths;

pub struct AppState {
    pub db: Arc<std::sync::Mutex<Database>>,
    pub http_client: reqwest::Client,
}

#[derive(Debug, Deserialize)]
pub struct SearchQuery {
    #[serde(default)]
    pub q: String,
}

#[derive(Debug, Deserialize)]
pub struct AppIdPayload {
    pub appid: Option<u32>,
}

#[derive(Debug, Deserialize)]
pub struct CollectionAddPayload {
    pub id: Option<String>,
}

// GET /health
pub async fn health() -> impl IntoResponse {
    Json(serde_json::json!({
        "ok": true,
        "version": "0.2.0"
    }))
}

// GET /status
pub async fn status(State(_state): State<Arc<AppState>>) -> impl IntoResponse {
    let stplug = paths::stplug_in_dir();
    let mut roots = Vec::new();
    let mut depots_count = 0;

    if let Ok(entries) = std::fs::read_dir(&stplug) {
        for entry in entries.flatten() {
            let path = entry.path();
            if path.extension().and_then(|e| e.to_str()) == Some("lua") {
                if let Some(stem) = path.file_stem().and_then(|s| s.to_str()) {
                    if let Ok(appid) = stem.parse::<u32>() {
                        roots.push(appid);
                        if let Ok(content) = std::fs::read_to_string(&path) {
                            let parsed = crate::engine::lua::parse_lua(&content);
                            depots_count += parsed.keys.len();
                        }
                    }
                }
            }
        }
    }

    roots.sort_unstable();

    Json(serde_json::json!({
        "ok": true,
        "apps": roots,
        "depots": depots_count,
    }))
}

// GET /settings
pub async fn get_settings(State(state): State<Arc<AppState>>) -> impl IntoResponse {
    let db = state.db.lock().unwrap();
    match db.get_all_settings() {
        Ok(s) => Json(s).into_response(),
        Err(e) => (StatusCode::INTERNAL_SERVER_ERROR, Json(serde_json::json!({"error": e.to_string()}))).into_response(),
    }
}

// POST /settings
pub async fn update_settings(
    State(state): State<Arc<AppState>>,
    Json(payload): Json<serde_json::Map<String, serde_json::Value>>,
) -> impl IntoResponse {
    let db = state.db.lock().unwrap();
    for (k, v) in &payload {
        let _ = db.set_setting(k, &v.to_string());
    }
    match db.get_all_settings() {
        Ok(s) => Json(serde_json::json!({"ok": true, "settings": s})).into_response(),
        Err(e) => (StatusCode::INTERNAL_SERVER_ERROR, Json(serde_json::json!({"error": e.to_string()}))).into_response(),
    }
}

// GET /search?q=...
pub async fn search(
    State(state): State<Arc<AppState>>,
    Query(query): Query<SearchQuery>,
) -> impl IntoResponse {
    let q = query.q.trim();
    if q.is_empty() {
        return Json(serde_json::json!({ "results": [] }));
    }

    match catalog::search_catalog(&state.http_client, q).await {
        Ok(hits) => Json(serde_json::json!({ "results": hits })),
        Err(e) => Json(serde_json::json!({ "error": e.to_string(), "results": [] })),
    }
}

// GET /library
pub async fn library(State(_state): State<Arc<AppState>>) -> impl IntoResponse {
    let stplug = paths::stplug_in_dir();
    let steamapps = paths::steamapps_dir();
    let mut games = Vec::new();

    if let Ok(entries) = std::fs::read_dir(&stplug) {
        for entry in entries.flatten() {
            let path = entry.path();
            if path.extension().and_then(|e| e.to_str()) == Some("lua") {
                if let Some(stem) = path.file_stem().and_then(|s| s.to_str()) {
                    if let Ok(appid) = stem.parse::<u32>() {
                        let installed = crate::engine::install::is_game_installed(&steamapps, appid);
                        games.push(serde_json::json!({
                            "appid": appid,
                            "name": format!("App {}", appid),
                            "installed": installed,
                            "cover": format!("https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{}/header.jpg", appid)
                        }));
                    }
                }
            }
        }
    }

    Json(serde_json::json!({ "games": games }))
}

// GET /game/:id
pub async fn game_details(
    State(state): State<Arc<AppState>>,
    AxumPath(appid): AxumPath<u32>,
) -> impl IntoResponse {
    let steamapps = paths::steamapps_dir();
    let stplug = paths::stplug_in_dir();

    let installed = crate::engine::install::is_game_installed(&steamapps, appid);
    let managed = stplug.join(format!("{}.lua", appid)).exists();

    let db = state.db.lock().unwrap();
    let fix_list = db.get_fixes(Some(appid)).unwrap_or_default();
    let snapshots = db.list_vault_snapshots(Some(appid)).unwrap_or_default();

    Json(serde_json::json!({
        "appid": appid,
        "name": format!("App {}", appid),
        "installed": installed,
        "managed": managed,
        "fixes": fix_list,
        "vault_snapshots": snapshots.len(),
        "cover": format!("https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{}/header.jpg", appid)
    }))
}

// GET /queue
pub async fn queue_status() -> impl IntoResponse {
    Json(serde_json::json!({
        "queue": [],
        "current": null,
        "history": []
    }))
}

// POST /cancel
pub async fn cancel_download(Json(payload): Json<AppIdPayload>) -> impl IntoResponse {
    let aid = payload.appid.unwrap_or_default();
    Json(serde_json::json!({ "ok": true, "cancelled": aid }))
}

// POST /remove
pub async fn remove_game(Json(payload): Json<AppIdPayload>) -> impl IntoResponse {
    let aid = payload.appid.unwrap_or_default();
    if aid == 0 {
        return (StatusCode::BAD_REQUEST, Json(serde_json::json!({"error": "Serve appid"}))).into_response();
    }

    let stplug = paths::stplug_in_dir();
    let lua_file = stplug.join(format!("{}.lua", aid));
    if lua_file.exists() {
        let _ = std::fs::remove_file(lua_file);
    }

    let steamapps = paths::steamapps_dir();
    let acf_file = steamapps.join(format!("appmanifest_{}.acf", aid));
    if acf_file.exists() {
        let _ = std::fs::remove_file(acf_file);
    }

    Json(serde_json::json!({
        "ok": true,
        "appid": aid,
        "message": format!("Gioco {} rimosso da MacLua", aid)
    })).into_response()
}

// GET /events (Server-Sent Events)
pub async fn sse_events() -> Sse<impl Stream<Item = Result<Event, std::convert::Infallible>>> {
    let stream = tokio_stream::wrappers::IntervalStream::new(tokio::time::interval(Duration::from_secs(1)))
        .map(|_| {
            let data = serde_json::json!({
                "queue": [],
                "current": null
            });
            Ok(Event::default().data(data.to_string()))
        });

    Sse::new(stream).keep_alive(KeepAlive::default())
}
