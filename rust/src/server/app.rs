//! Axum web application setup for MacLua daemon.

use std::sync::Arc;
use axum::{
    middleware,
    routing::{get, post},
    Router,
};
use tokio::net::TcpListener;

use crate::storage::db::Database;
use super::auth::{auth_middleware, cors_layer};
use super::routes::{self, AppState};

pub fn build_app(state: Arc<AppState>) -> Router {
    Router::new()
        .route("/health", get(routes::health))
        .route("/status", get(routes::status))
        .route("/settings", get(routes::get_settings).post(routes::update_settings))
        .route("/search", get(routes::search))
        .route("/library", get(routes::library))
        .route("/game/:id", get(routes::game_details))
        .route("/queue", get(routes::queue_status))
        .route("/cancel", post(routes::cancel_download))
        .route("/remove", post(routes::remove_game))
        .route("/events", get(routes::sse_events))
        .layer(middleware::from_fn(auth_middleware))
        .layer(cors_layer())
        .with_state(state)
}

pub async fn run_server(port: u16) -> Result<(), Box<dyn std::error::Error>> {
    let db = Arc::new(std::sync::Mutex::new(Database::open_default()?));
    let http_client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(15))
        .build()?;

    let state = Arc::new(AppState { db, http_client });
    let app = build_app(state);

    let addr = format!("127.0.0.1:{}", port);
    let listener = TcpListener::bind(&addr).await?;
    println!("MacLua daemon listening on http://{}", addr);

    axum::serve(listener, app).await?;
    Ok(())
}
