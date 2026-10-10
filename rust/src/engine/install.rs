//! Game installation, appmanifest (.acf) generation, and executable permissions.

use std::fs::File;
use std::io::Write;
use std::path::{Path, PathBuf};

use super::keyvalues::KeyValues;

/// Checks if an app is installed on disk.
pub fn is_game_installed<P: AsRef<Path>>(steamapps_dir: P, appid: u32) -> bool {
    let acf_path = steamapps_dir.as_ref().join(format!("appmanifest_{}.acf", appid));
    if !acf_path.is_file() {
        return false;
    }
    if let Ok(content) = std::fs::read_to_string(&acf_path) {
        if let Ok(kv) = KeyValues::parse(&content) {
            if let Some((_, root)) = kv.root.iter().find(|(k, _)| k.eq_ignore_ascii_case("AppState")) {
                let flags = root.get_str("StateFlags").unwrap_or("0");
                if flags == "4" {
                    if let Some(installdir) = root.get_str("installdir") {
                        let g_dir = steamapps_dir.as_ref().join("common").join(installdir);
                        return g_dir.is_dir();
                    }
                    return true;
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

                                    // Firma ad-hoc il bundle .app per evitare SIGKILL da parte di taskgated su Apple Silicon
                                    #[cfg(target_os = "macos")]
                                    if let Some(app_bundle) = dir.parent().and_then(|p| p.parent()) {
                                        let _ = std::process::Command::new("codesign")
                                            .args(["--force", "--deep", "--sign", "-", app_bundle.to_str().unwrap_or("")])
                                            .status();
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

