//! Arbiter — Tauri desktop wrapper.
//!
//! Spawns the Python bot subprocess and lets Tauri load the dashboard
//! from devUrl. Checks for updates on startup via tauri-plugin-updater.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::process::Command;
use std::sync::Mutex;
use tauri::{Manager, WindowEvent};
use tauri_plugin_updater::UpdaterExt;

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
    if let Ok(dir) = std::env::var("ARBITER_DIR") {
        if let Some(found) = find_bot_dir(std::path::PathBuf::from(&dir)) {
            return Some(found);
        }
    }

    // 2. Default install location
    if let Ok(home) = std::env::var("HOME") {
        let install = std::path::PathBuf::from(&home).join(".arbiter");
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

#[tauri::command]
async fn check_for_updates(app: tauri::AppHandle) -> serde_json::Value {
    let updater = match app.updater() {
        Ok(u) => u,
        Err(e) => return serde_json::json!({ "has_update": false, "error": e.to_string() }),
    };

    match updater.check().await {
        Ok(Some(update)) => {
            serde_json::json!({
                "has_update": true,
                "version": update.version,
                "date": update.date.map(|d| d.to_string()).unwrap_or_default(),
                "body": update.body.as_deref().unwrap_or(""),
            })
        }
        Ok(None) => {
            serde_json::json!({ "has_update": false, "current_version": "" })
        }
        Err(e) => {
            serde_json::json!({ "has_update": false, "error": e.to_string() })
        }
    }
}

#[tauri::command]
async fn install_update(app: tauri::AppHandle) -> Result<(), String> {
    let updater = app.updater().map_err(|e| e.to_string())?;
    let update = updater.check().await.map_err(|e| e.to_string())?;

    if let Some(update) = update {
        update.download_and_install(|_, _| {}, || {}).await.map_err(|e| e.to_string())?;
        // App needs to be relaunched manually on Linux
        app.restart();
    }

    Ok(())
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .manage(BotProcess(Mutex::new(None)))
        .setup(|app| {
            let port: u16 = 8090;

            // Only spawn the bot if the dashboard isn't already running
            if !dashboard_running(port) {
                let bot_dir = resolve_bot_dir().unwrap_or_else(|| {
                    eprintln!("[Arbiter] Could not find bot project. Run the bot manually first.");
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
                            "[Arbiter] Bot started: {} (port {})",
                            bot_dir.display(),
                            port
                        );
                        {
                            let state = app.state::<BotProcess>();
                            *state.0.lock().unwrap() = Some(child);
                        }
                    }
                    Err(e) => {
                        eprintln!("[Arbiter] Failed to start bot: {}", e);
                    }
                }

                // Wait for dashboard to start
                std::thread::sleep(std::time::Duration::from_millis(4000));
            } else {
                println!("[Arbiter] Dashboard already running on port {}, attaching", port);
            }

            // Check for updates in the background
            let app_handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                let result = check_for_updates(app_handle.clone()).await;
                if let Some(window) = app_handle.get_webview_window("main") {
                    let version = result.get("version")
                        .and_then(|v| v.as_str())
                        .unwrap_or("");
                    let body = result.get("body")
                        .and_then(|b| b.as_str())
                        .unwrap_or("");
                    let has_update = result.get("has_update")
                        .and_then(|h| h.as_bool())
                        .unwrap_or(false);
                    let _ = window.eval(&format!(
                        r#"if(window.dispatchEvent) window.dispatchEvent(new CustomEvent('update-available', {{ detail: {{ hasUpdate: {}, version: "{}", body: "{}" }} }}))"#,
                        has_update,
                        version.replace('"', "\\\""),
                        body.replace('"', "\\\"").replace('\n', " ")
                    ));
                }
            });

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![check_for_updates, install_update])
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { .. } = event {
                let state = window.state::<BotProcess>();
                if let Some(mut child) = state.0.lock().unwrap().take() {
                    let _ = child.kill();
                    println!("[Arbiter] Bot subprocess killed");
                };
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
