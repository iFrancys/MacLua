//! Steam Catalog and Store API client with parent resolution (DLC -> Parent game).

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchHit {
    pub appid: u32,
    pub name: String,
    pub cover: String,
    pub is_dlc_resolved: bool,
}

#[derive(Debug, Deserialize)]
struct StoreSearchResponse {
    #[serde(default)]
    items: Vec<StoreSearchItem>,
}

#[derive(Debug, Deserialize)]
struct StoreSearchItem {
    id: u32,
    name: String,
}

/// Searches the Steam Store catalog and returns resolved items.
pub async fn search_catalog(client: &reqwest::Client, query: &str) -> Result<Vec<SearchHit>, reqwest::Error> {
    let url = format!(
        "https://store.steampowered.com/api/storesearch/?term={}&l=english&cc=US",
        urlencoding::encode(query)
    );

    let res = client.get(&url).send().await?;
    let search_res: StoreSearchResponse = res.json().await.unwrap_or(StoreSearchResponse { items: Vec::new() });

    let mut hits = Vec::new();
    let mut seen = std::collections::HashSet::new();

    for item in search_res.items {
        let appid = item.id;
        if seen.insert(appid) {
            hits.push(SearchHit {
                appid,
                name: item.name,
                cover: format!(
                    "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{}/header.jpg",
                    appid
                ),
                is_dlc_resolved: false,
            });
        }
    }

    Ok(hits)
}

/// Resolves the parent AppID for a given AppID via the Steam store API if it is a DLC.
pub async fn resolve_parent(client: &reqwest::Client, appid: u32) -> Result<Option<u32>, reqwest::Error> {
    let url = format!(
        "https://store.steampowered.com/api/appdetails?appids={}&filters=basic",
        appid
    );

    let res = client.get(&url).send().await?;
    let body: serde_json::Value = res.json().await.unwrap_or_default();

    if let Some(app_obj) = body.get(&appid.to_string()) {
        if app_obj.get("success").and_then(|v| v.as_bool()) == Some(true) {
            if let Some(data) = app_obj.get("data") {
                // If type == "dlc", check fullgame.appid
                if data.get("type").and_then(|v| v.as_str()) == Some("dlc") {
                    if let Some(fullgame) = data.get("fullgame") {
                        if let Some(parent_id_str) = fullgame.get("appid").and_then(|v| v.as_str()) {
                            if let Ok(pid) = parent_id_str.parse::<u32>() {
                                return Ok(Some(pid));
                            }
                        } else if let Some(pid) = fullgame.get("appid").and_then(|v| v.as_u64()) {
                            return Ok(Some(pid as u32));
                        }
                    }
                }
            }
        }
    }

    Ok(None)
}
