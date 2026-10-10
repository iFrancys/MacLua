use clap::Parser;
use maclua::cli::{Cli, run_cli};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let cli = Cli::parse();
    if let Err(e) = run_cli(cli).await {
        eprintln!("errore: {}", e);
        std::process::exit(1);
    }
    Ok(())
}
