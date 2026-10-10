//! Offline license management in Steam's packageinfo.vdf:
//! - package0 poisoning (injects managed AppIDs and DepotIDs into free/owned group)
//! - forged package 4000001 (allows non-zero packages to register)
//! - exact SHA-1 recomputation of group1 payload at header offset 0x0C.

use std::collections::HashSet;
use std::fs::File;
use std::io::Write;
use std::path::Path;
use sha1::{Digest, Sha1};

use super::bkv::{BkvError, BkvNode, BkvReader, ser_node};

pub const HEADER_LEN: usize = 0x2C;
pub const FORGE_ID: i32 = 4000001;

#[derive(Debug, thiserror::Error)]
pub enum LicenseError {
    #[error("packageinfo.vdf file too short (expected >= 0x2C bytes)")]
    FileTooShort,
    #[error("package 0 section not found in packageinfo.vdf")]
    Package0NotFound,
    #[error("binary VDF error: {0}")]
    Bkv(#[from] BkvError),
    #[error("I/O error: {0}")]
    Io(#[from] std::io::Error),
}

pub struct PackageInfoFile {
    pub header: Vec<u8>,
    pub packages: Vec<BkvNode>,
    pub rest: Vec<u8>,
}

/// Loads groups from packageinfo.vdf.
pub fn load_groups(data: &[u8]) -> Result<PackageInfoFile, LicenseError> {
    if data.len() < HEADER_LEN {
        return Err(LicenseError::FileTooShort);
    }

    let header = data[..HEADER_LEN].to_vec();
    let mut reader = BkvReader::new(&data[HEADER_LEN..]);
    let mut packages = Vec::new();

    while let Some(node) = reader.parse_node()? {
        packages.push(node);
    }

    let parsed_len = reader.offset();
    let rest = data[HEADER_LEN + parsed_len..].to_vec();

    Ok(PackageInfoFile {
        header,
        packages,
        rest,
    })
}

/// Injects missing `appids` and `depotids` into `package0`, recalculates SHA-1, and atomically writes back.
pub fn poison_packageinfo<P: AsRef<Path>>(
    path: P,
    appids: &HashSet<u32>,
    depotids: &HashSet<u32>,
) -> Result<(usize, usize), LicenseError> {
    let data = std::fs::read(path.as_ref())?;
    let mut pkg_file = load_groups(&data)?;

    let mut added_app = 0;
    let mut added_dep = 0;

    // Locate package 0
    let p0 = pkg_file
        .packages
        .iter_mut()
        .find(|n| match n {
            BkvNode::Section(k, _) => k == "0",
            _ => false,
        })
        .ok_or(LicenseError::Package0NotFound)?;

    if let BkvNode::Section(_, children) = p0 {
        // AppIDs section
        if let Some(app_sec) = children.iter_mut().find(|c| c.key() == "appids") {
            if let BkvNode::Section(_, existing_apps) = app_sec {
                let existing_set: HashSet<u32> = existing_apps
                    .iter()
                    .filter_map(|c| match c {
                        BkvNode::Int32(_, val) => Some(*val as u32),
                        _ => None,
                    })
                    .collect();

                let mut to_add: Vec<u32> = appids.difference(&existing_set).copied().collect();
                to_add.sort_unstable();
                for aid in to_add {
                    let idx_str = existing_apps.len().to_string();
                    existing_apps.push(BkvNode::Int32(idx_str, aid as i32));
                    added_app += 1;
                }
            }
        }

        // DepotIDs section
        if let Some(dep_sec) = children.iter_mut().find(|c| c.key() == "depotids") {
            if let BkvNode::Section(_, existing_deps) = dep_sec {
                let existing_set: HashSet<u32> = existing_deps
                    .iter()
                    .filter_map(|c| match c {
                        BkvNode::Int32(_, val) => Some(*val as u32),
                        _ => None,
                    })
                    .collect();

                let mut to_add: Vec<u32> = depotids.difference(&existing_set).copied().collect();
                to_add.sort_unstable();
                for did in to_add {
                    let idx_str = existing_deps.len().to_string();
                    existing_deps.push(BkvNode::Int32(idx_str, did as i32));
                    added_dep += 1;
                }
            }
        }
    }

    // Serialize updated packages
    let mut body = Vec::new();
    for pkg in &pkg_file.packages {
        ser_node(pkg, &mut body)?;
    }
    body.push(0x08); // trailing terminator for group 1

    let mut new_file = Vec::with_capacity(HEADER_LEN + body.len() + pkg_file.rest.len());
    new_file.extend_from_slice(&pkg_file.header);
    new_file.extend_from_slice(&body);
    new_file.extend_from_slice(&pkg_file.rest);

    // Recalculate SHA-1 of group 1 payload: new_file[HEADER_LEN .. HEADER_LEN + body.len()]
    let mut hasher = Sha1::new();
    hasher.update(&new_file[HEADER_LEN..HEADER_LEN + body.len()]);
    let sha1_digest = hasher.finalize();

    // Replace SHA-1 in header at [0x0C .. 0x20] (20 bytes)
    new_file[0x0C..0x20].copy_from_slice(&sha1_digest);

    // Atomic write
    let tmp_path = format!("{}.tmp.maclua", path.as_ref().display());
    {
        let mut f = File::create(&tmp_path)?;
        f.write_all(&new_file)?;
        f.flush()?;
    }
    std::fs::rename(&tmp_path, path.as_ref())?;

    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let _ = std::fs::set_permissions(path.as_ref(), std::fs::Permissions::from_mode(0o755));
    }

    Ok((added_app, added_dep))
}
