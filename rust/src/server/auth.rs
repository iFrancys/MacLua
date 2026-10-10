//! Bridge server token authentication and CORS protection.

use std::fs::File;
use std::io::Write;
use std::path::PathBuf;
use axum::{
    extract::Request,
    http::{HeaderValue, Method, StatusCode},
    middleware::Next,
    response::{IntoResponse, Response},
    Json,
};
use tower_http::cors::{AllowOrigin, CorsLayer};
use crate::util::paths;

pub const TOKEN_LEN: usize = 64; // 32 bytes in hex = 64 characters

/// Reads or generates the 32-byte hex token in `~/Library/Application Support/MacLua/bridge_token` (0600).
pub fn get_or_create_token() -> String {
    let path: PathBuf = paths::token_path();
    if let Ok(content) = std::fs::read_to_string(&path) {
        let trimmed = content.trim();
        if trimmed.len() >= TOKEN_LEN {
            return trimmed.to_string();
        }
    }

    let _ = std::fs::create_dir_all(paths::maclua_support_dir());

    // Generate 32 cryptographically secure random bytes
    let mut bytes = [0u8; 32];
    getrandom::getrandom(&mut bytes).unwrap_or_else(|_| {
        for b in &mut bytes {
            *b = rand_fallback();
        }
    });

    let token = hex::encode(bytes);
    if let Ok(mut f) = File::create(&path) {
        let _ = f.write_all(token.as_bytes());
        let _ = f.flush();
    }

    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let _ = std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600));
    }

    token
}

fn rand_fallback() -> u8 {
    use std::time::SystemTime;
    let nanos = SystemTime::now()
        .duration_since(SystemTime::UNIX_EPOCH)
        .unwrap_or_default()
        .subsec_nanos();
    (nanos & 0xFF) as u8
}

/// Creates a CORS layer restricted to Steam Store and local origins.
pub fn cors_layer() -> CorsLayer {
    let allowed_origins = [
        "https://store.steampowered.com".parse::<HeaderValue>().unwrap(),
        "https://steamloopback.host".parse::<HeaderValue>().unwrap(),
        "http://127.0.0.1:6767".parse::<HeaderValue>().unwrap(),
        "http://localhost:6767".parse::<HeaderValue>().unwrap(),
    ];

    CorsLayer::new()
        .allow_origin(AllowOrigin::list(allowed_origins))
        .allow_methods([Method::GET, Method::POST, Method::OPTIONS])
        .allow_headers([
            axum::http::header::CONTENT_TYPE,
            axum::http::header::AUTHORIZATION,
            axum::http::HeaderName::from_static("x-maclua-token"),
        ])
}

/// Axum middleware checking `X-MacLua-Token` header.
pub async fn auth_middleware(req: Request, next: Next) -> Response {
    let path = req.uri().path();
    // /health is public
    if path == "/health" || path == "/icon" {
        return next.run(req).await;
    }

    let expected = get_or_create_token();

    // Check header
    if let Some(token_header) = req.headers().get("X-MacLua-Token") {
        if let Ok(token_str) = token_header.to_str() {
            if token_str == expected {
                return next.run(req).await;
            }
        }
    }

    // Check query parameter ?token=...
    if let Some(query) = req.uri().query() {
        for pair in query.split('&') {
            if let Some((k, v)) = pair.split_once('=') {
                if k == "token" && v == expected {
                    return next.run(req).await;
                }
            }
        }
    }

    (
        StatusCode::UNAUTHORIZED,
        Json(serde_json::json!({"error": "Non autorizzato: token mancante o errato"})),
    )
        .into_response()
}
