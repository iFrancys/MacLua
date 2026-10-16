//! Game installation, appmanifest (.acf) generation, and executable permissions.

use std::fs::File;
use std::io::Write;
use std::path::{Path, PathBuf};

use super::keyvalues::KeyValues;

/// Checks if an app is installed on disk (including when an update is pending with StateFlags 6).
pub fn is_game_installed<P: AsRef<Path>>(steamapps_dir: P, appid: u32) -> bool {
    let acf_path = steamapps_dir.as_ref().join(format!("appmanifest_{}.acf", appid));
    if !acf_path.is_file() {
        return false;
    }
    if let Ok(content) = std::fs::read_to_string(&acf_path) {
        if let Ok(kv) = KeyValues::parse(&content) {
            if let Some((_, root)) = kv.root.iter().find(|(k, _)| k.eq_ignore_ascii_case("AppState")) {
                let flags = root.get_str("StateFlags").and_then(|s| s.parse::<u32>().ok()).unwrap_or(0);
                let size = root.get_str("SizeOnDisk").and_then(|s| s.parse::<u64>().ok()).unwrap_or(0);
                if (flags & 4) != 0 || size > 0 {
                    if let Some(installdir) = root.get_str("installdir") {
                        let g_dir = steamapps_dir.as_ref().join("common").join(installdir);
                        return g_dir.is_dir()
                            && std::fs::read_dir(&g_dir).map(|mut it| it.next().is_some()).unwrap_or(false);
                    }
                    return (flags & 4) != 0;
                }
            }
        }
    }
    false
}

/// Creates a default appmanifest_{appid}.acf if not present.
pub fn create_appmanifest<P: AsRef<Path>>(
    steamapps_dir: P,
    appid: u32,
    name: &str,
    installdir: &str,
    buildid: u32,
    owner: &str,
) -> Result<PathBuf, std::io::Error> {
    let acf_path = steamapps_dir.as_ref().join(format!("appmanifest_{}.acf", appid));
    if acf_path.is_file() {
        return Ok(acf_path);
    }

    let body = format!(
        "\"AppState\"\n{{\n\t\"appid\"\t\t\"{}\"\n\t\"Universe\"\t\t\"1\"\n\t\"name\"\t\t\"{}\"\n\t\"StateFlags\"\t\t\"4\"\n\t\"installdir\"\t\t\"{}\"\n\t\"LastOwner\"\t\t\"{}\"\n\t\"buildid\"\t\t\"{}\"\n\t\"UpdateResult\"\t\t\"0\"\n}}\n",
        appid, name, installdir, owner, buildid
    );

    let tmp = format!("{}.tmp.maclua", acf_path.display());
    {
        let mut f = File::create(&tmp)?;
        f.write_all(body.as_bytes())?;
        f.flush()?;
    }
    std::fs::rename(&tmp, &acf_path)?;
    Ok(acf_path)
}

/// Cleans up fake / broken appmanifest files with StateFlags 2 or 18 (Download requested / Update queued)
/// when the game has no actual files on disk in common/. This restores Steam's clean, native
/// interface showing normal "Install" button with proper MB/GB calculation.
pub fn cleanup_broken_appmanifests<P: AsRef<Path>>(steamapps_dir: P) -> Vec<u32> {
    let mut cleaned = Vec::new();
    let dir = steamapps_dir.as_ref();
    if let Ok(entries) = std::fs::read_dir(dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            if let Some(file_name) = path.file_name().and_then(|n| n.to_str()) {
                if file_name.starts_with("appmanifest_") && file_name.ends_with(".acf") {
                    if let Ok(content) = std::fs::read_to_string(&path) {
                        if let Ok(kv) = KeyValues::parse(&content) {
                            if let Some((_, root)) = kv.root.iter().find(|(k, _)| k.eq_ignore_ascii_case("AppState")) {
                                let flags = root.get_str("StateFlags").unwrap_or("0");
                                let size = root.get_str("SizeOnDisk").unwrap_or("0");
                                if (flags == "2" || flags == "18") && size == "0" {
                                    let installdir = root.get_str("installdir").unwrap_or("");
                                    let has_files = if !installdir.is_empty() {
                                        let common_dir = dir.join("common").join(installdir);
                                        common_dir.is_dir() && std::fs::read_dir(&common_dir).map(|mut it| it.next().is_some()).unwrap_or(false)
                                    } else {
                                        false
                                    };
                                    if !has_files {
                                        let appid = root.get_str("appid").and_then(|a| a.parse::<u32>().ok()).unwrap_or(0);
                                        let _ = std::fs::remove_file(&path);
                                        cleaned.push(appid);
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    cleaned
}

const LAUNCHER_HELPER: &[u8] = include_bytes!("../../../assets/launcher_helper");

/// Recursively sets executable (+x) permissions on Mach-O and Unix executable files in game directory.
/// For macOS .app bundles with a Resources/ folder, replaces the main binary with the pre-compiled
/// static launcher helper that fixes the working directory for Steam.
#[cfg(unix)]
pub fn fix_executables<P: AsRef<Path>>(root: P) -> usize {
    use std::os::unix::fs::PermissionsExt;
    let mut fixed = 0;

    fn is_macho_or_script(path: &Path) -> (bool, bool) {
        if let Ok(mut f) = File::open(path) {
            use std::io::Read;
            let mut magic = [0u8; 4];
            if f.read_exact(&mut magic).is_ok() {
                let is_macho = matches!(
                    magic,
                    [0xCF, 0xFA, 0xED, 0xFE] // MH_MAGIC_64
                    | [0xCE, 0xFA, 0xED, 0xFE] // MH_MAGIC
                    | [0xCA, 0xFE, 0xBA, 0xBE] // FAT_MAGIC
                );
                let is_script = magic.starts_with(b"#!");
                return (is_macho, is_script);
            }
        }
        (false, false)
    }

    fn visit_dir(dir: &Path, fixed: &mut usize) {
        let is_macos_bundle_bin = dir.ends_with("Contents/MacOS")
            && dir.parent().map(|p| p.join("Resources").is_dir()).unwrap_or(false);

        if let Ok(entries) = std::fs::read_dir(dir) {
            for entry in entries.flatten() {
                let path = entry.path();
                if path.is_dir() {
                    visit_dir(&path, fixed);
                } else if path.is_file() {
                    let file_name = path.file_name().and_then(|n| n.to_str()).unwrap_or("");
                    let (is_macho, is_script) = is_macho_or_script(&path);

                    if is_macho || is_script {
                        if let Ok(meta) = path.metadata() {
                            let mut perms = meta.permissions();
                            let mode = perms.mode();
                            if mode & 0o111 != 0o111 {
                                perms.set_mode(mode | 0o755);
                                let _ = std::fs::set_permissions(&path, perms);
                                *fixed += 1;
                            }
                        }
                    }

                    // Bundle launcher helper replacement
                    if is_macos_bundle_bin && (is_macho || is_script) && !file_name.ends_with(".real") {
                        let real_path = path.with_file_name(format!("{}.real", file_name));
                        if !real_path.exists() {
                            if std::fs::rename(&path, &real_path).is_ok() {
                                if std::fs::write(&path, LAUNCHER_HELPER).is_ok() {
                                    if let Ok(meta) = std::fs::metadata(&path) {
                                        let mut p = meta.permissions();
                                        p.set_mode(0o755);
                                        let _ = std::fs::set_permissions(&path, p);
                                    }
                                    if let Ok(rmeta) = std::fs::metadata(&real_path) {
                                        let mut rp = rmeta.permissions();
                                        rp.set_mode(0o755);
                                        let _ = std::fs::set_permissions(&real_path, rp);
                                    }
                                    *fixed += 1;

                                    // Firma ad-hoc sia il binario .real sia il bundle .app per evitare SIGKILL da parte di taskgated su Apple Silicon
                                    #[cfg(target_os = "macos")]
                                    {
                                        if let Some(real_str) = real_path.to_str() {
                                            let _ = std::process::Command::new("/usr/bin/codesign")
                                                .args(["--force", "--sign", "-", real_str])
                                                .status();
                                        }
                                        if let Some(app_bundle) = dir.parent().and_then(|p| p.parent()) {
                                            if app_bundle.extension().and_then(|e| e.to_str()) == Some("app") {
                                                if let Some(bundle_str) = app_bundle.to_str() {
                                                    let _ = std::process::Command::new("/usr/bin/codesign")
                                                        .args(["--force", "--deep", "--sign", "-", bundle_str])
                                                        .status();
                                                }
                                            }
                                        }
                                    }
                                } else {
                                    // Ripristino atomico in caso di errore di scrittura
                                    let _ = std::fs::rename(&real_path, &path);
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    visit_dir(root.as_ref(), &mut fixed);
    fixed
}

#[cfg(not(unix))]
pub fn fix_executables<P: AsRef<Path>>(_root: P) -> usize {
    0
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_launcher_helper_is_valid() {
        assert!(!LAUNCHER_HELPER.is_empty());
        assert_eq!(&LAUNCHER_HELPER[0..4], &[0xCA, 0xFE, 0xBA, 0xBE]); // Fat Mach-O
    }
}

