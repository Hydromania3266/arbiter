//! AI Trading Bot — Tauri desktop wrapper.
//!
//! Spawns the Python bot subprocess and loads the dashboard in the WebView.
//! - In dev mode: uses tauri.conf.json `devUrl` (http://localhost:8090)
//! - In release mode: uses bundled frontend (file://)
//!
//! The bot subprocess is started on setup and killed when the window closes.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::process::Command;
use std::sync::Mutex;
use tauri::{Manager, WindowEvent};

struct BotProcess(Mutex<Option<std::process::Child>>);

fn find_bot_dir(start: std::path::PathBuf) -> Option<std::path::PathBuf> {
    let mut current = start;
    for _ in 0..10 {
        if current.join("src").join("main.py").exists() {
            return Some(current);
        }
        current = current.parent()?.to_path_buf();
    }
    None
}

fn resolve_bot_dir() -> Option<std::path::PathBuf> {
    // 1. Explicit env var from the launcher script
    if let Ok(dir) = std::env::var("AITB_DIR") {
        if let Some(found) = find_bot_dir(std::path::PathBuf::from(&dir)) {
            return Some(found);
        }
    }

    // 2. Default install location
    if let Ok(home) = std::env::var("HOME") {
        let install = std::path::PathBuf::from(&home).join(".ai-trading-bot");
        if let Some(found) = find_bot_dir(install) {
            return Some(found);
        }
    }

    // 3. Walk up from the executable (works in dev / source tree)
    if let Ok(exe) = std::env::current_exe() {
        if let Some(parent) = exe.parent() {
            if let Some(found) = find_bot_dir(parent.to_path_buf()) {
                return Some(found);
            }
        }
    }

    // 4. Current working directory
    find_bot_dir(std::env::current_dir().ok()?)
}

fn dashboard_running(port: u16) -> bool {
    std::net::TcpStream::connect(("127.0.0.1", port)).is_ok()
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(BotProcess(Mutex::new(None)))
        .setup(|app| {
            let port: u16 = 8090;

            // Only spawn the bot if the dashboard isn't already running
            if !dashboard_running(port) {
                let bot_dir = resolve_bot_dir().unwrap_or_else(|| {
                    eprintln!("[Tauri] Could not find bot project. Run the bot manually first.");
                    std::env::current_dir().unwrap()
                });

                let venv_python = bot_dir.join(".venv").join("bin").join("python");
                let python = if venv_python.exists() {
                    venv_python.to_string_lossy().to_string()
                } else {
                    "python3".to_string()
                };

                match Command::new(&python)
                    .arg("-m")
                    .arg("src.main")
                    .arg("run")
                    .env("WEB_PORT", &port.to_string())
                    .current_dir(&bot_dir)
                    .spawn()
                {
                    Ok(child) => {
                        println!(
                            "[Tauri] Bot started: {} (port {})",
                            bot_dir.display(),
                            port
                        );
                        {
                            let state = app.state::<BotProcess>();
                            *state.0.lock().unwrap() = Some(child);
                        }
                    }
                    Err(e) => {
                        eprintln!("[Tauri] Failed to start bot: {}", e);
                    }
                }

                // Wait for dashboard to start
                std::thread::sleep(std::time::Duration::from_millis(4000));
            } else {
                println!("[Tauri] Dashboard already running on port {}, attaching", port);
            }

            Ok(())
        })
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { .. } = event {
                let state = window.state::<BotProcess>();
                if let Some(mut child) = state.0.lock().unwrap().take() {
                    let _ = child.kill();
                    println!("[Tauri] Bot subprocess killed");
                };
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
