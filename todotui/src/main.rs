mod api;
mod app;
mod ui;

use anyhow::{bail, Result};
use app::{App, Mode};
use api::TodoApi;
use sha2::{Sha256, Digest};
use crossterm::{
    event::{self, Event, KeyCode, KeyModifiers},
    execute,
    terminal::{EnterAlternateScreen, LeaveAlternateScreen, disable_raw_mode, enable_raw_mode},
};
use ratatui::{Terminal, backend::CrosstermBackend};
use std::collections::HashMap;
use std::io;

/// Load config from ~/.config/todotui/config (KEY=VALUE, # comments, blank lines ok).
fn load_config() -> HashMap<String, String> {
    let mut map = HashMap::new();
    let path = dirs::home_dir()
        .map(|h| h.join(".config/todotui/config"));
    if let Some(path) = path {
        if let Ok(contents) = std::fs::read_to_string(&path) {
            for line in contents.lines() {
                let line = line.trim();
                if line.is_empty() || line.starts_with('#') { continue; }
                if let Some((k, v)) = line.split_once('=') {
                    map.insert(k.trim().to_string(), v.trim().to_string());
                }
            }
        }
    }
    map
}

fn get_cfg(key: &str, config: &HashMap<String, String>) -> Option<String> {
    std::env::var(key).ok().or_else(|| config.get(key).cloned())
}

/// Check if the server has a newer binary; if so, download it, replace self, and re-exec.
/// All errors are silently ignored — update is best-effort.
fn try_self_update(url: &str) {
    let _ = do_self_update(url);
}

fn do_self_update(url: &str) -> Result<()> {
    let os   = std::env::consts::OS;   // "linux", "macos"
    let arch = std::env::consts::ARCH; // "aarch64", "x86_64"
    let binary_name = format!("todotui-{}-{}", os, arch);

    let exe = std::env::current_exe()?;
    let current_bytes = std::fs::read(&exe)?;
    let mut hasher = Sha256::new();
    hasher.update(&current_bytes);
    let current_hash = hex::encode(hasher.finalize());

    let client = reqwest::blocking::Client::builder()
        .timeout(std::time::Duration::from_secs(8))
        .build()?;

    let remote_hash = client
        .get(format!("{}/download/{}.sha256", url, binary_name))
        .send()?
        .text()?
        .trim()
        .to_string();

    if remote_hash == current_hash {
        return Ok(());
    }

    eprintln!("todotui: update available, downloading...");
    let bytes = client
        .get(format!("{}/download/{}", url, binary_name))
        .send()?
        .bytes()?;

    let tmp = exe.with_extension("tmp");
    std::fs::write(&tmp, &bytes)?;

    use std::os::unix::fs::PermissionsExt;
    std::fs::set_permissions(&tmp, std::fs::Permissions::from_mode(0o755))?;
    std::fs::rename(&tmp, &exe)?;

    // Replace this process with the new binary
    use std::os::unix::process::CommandExt;
    Err(std::process::Command::new(&exe)
        .args(std::env::args().skip(1))
        .exec()
        .into())
}

fn main() -> Result<()> {
    let config = load_config();

    let url  = get_cfg("TODO_URL",  &config).unwrap_or_else(|| "http://localhost:5000".to_string());
    let user = get_cfg("TODO_USER", &config)
        .ok_or(()).or_else(|_| bail!("TODO_USER not set (env var or ~/.config/todotui/config)"))?;
    let pass = get_cfg("TODO_PASS", &config)
        .ok_or(()).or_else(|_| bail!("TODO_PASS not set (env var or ~/.config/todotui/config)"))?;

    try_self_update(&url);

    let pick_mode = std::env::args().any(|a| a == "--pick" || a == "-p");
    let list_mode = std::env::args().any(|a| a == "--list" || a == "-l");

    let mut api = TodoApi::new(&url, &user, &pass)?;

    if list_mode {
        let tasks = api.list_tasks("", "incomplete")?;
        for t in tasks {
            println!("{}\t{}", t.id, t.raw_line);
        }
        return Ok(());
    }

    let mut app = App::new(api, pick_mode);

    enable_raw_mode()?;
    let mut stdout = io::stdout();
    execute!(stdout, EnterAlternateScreen)?;
    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;

    app.refresh().unwrap_or_else(|e| {
        app.status = format!("Error: {e}");
    });

    loop {
        terminal.draw(|f| ui::draw(f, &app))?;

        if let Event::Key(key) = event::read()? {
            app.show_banner = false;
            match app.mode {
                Mode::Normal | Mode::ConfirmDelete => handle_normal(&mut app, key.code, key.modifiers)?,
                Mode::Filter => handle_input_mode(&mut app, key.code, InputAction::Filter)?,
                Mode::AddTask => handle_input_mode(&mut app, key.code, InputAction::Add)?,
                Mode::EditTask => handle_input_mode(&mut app, key.code, InputAction::Edit)?,
            }
        }

        if app.should_quit {
            break;
        }
    }

    disable_raw_mode()?;
    execute!(terminal.backend_mut(), LeaveAlternateScreen)?;
    terminal.show_cursor()?;

    // Output selected tasks to stdout after restoring terminal
    let tasks = app.get_selected_tasks();
    for t in tasks {
        println!("{}", t.raw_line);
    }

    Ok(())
}

enum InputAction {
    Filter,
    Add,
    Edit,
}

fn handle_normal(app: &mut App, code: KeyCode, _mods: KeyModifiers) -> Result<()> {
    if app.mode == Mode::ConfirmDelete {
        match code {
            KeyCode::Char('y') | KeyCode::Char('Y') => {
                if app.selected.is_empty() {
                    app.delete_current().unwrap_or_else(|e| app.status = format!("Error: {e}"));
                } else {
                    app.delete_selected().unwrap_or_else(|e| app.status = format!("Error: {e}"));
                }
                app.mode = Mode::Normal;
            }
            _ => {
                app.mode = Mode::Normal;
                app.status = "Delete cancelled.".into();
            }
        }
        return Ok(());
    }

    match code {
        KeyCode::Char('q') | KeyCode::Esc => app.should_quit = true,
        KeyCode::Char('j') | KeyCode::Down  => app.move_down(),
        KeyCode::Char('k') | KeyCode::Up    => app.move_up(),
        KeyCode::Char('g') | KeyCode::Home  => app.go_top(),
        KeyCode::Char('G') | KeyCode::End   => app.go_bottom(),
        KeyCode::Char(' ')                  => app.toggle_select(),
        KeyCode::Char('*')                  => app.select_all(),
        KeyCode::Char('\\')                 => app.deselect_all(),

        KeyCode::Char('a')  => app.start_add(),
        KeyCode::Char('e')  => app.start_edit(),
        KeyCode::Char('/')  => app.start_filter(),
        KeyCode::Char('c')  => app.clear_filter(),

        KeyCode::Char('d') | KeyCode::Enter => {
            app.toggle_complete_current().unwrap_or_else(|e| app.status = format!("Error: {e}"));
        }

        KeyCode::Char('D') => {
            if app.current_task().is_some() || !app.selected.is_empty() {
                app.mode = Mode::ConfirmDelete;
                let n = if app.selected.is_empty() { 1 } else { app.selected.len() };
                app.status = format!("Delete {n} task(s)? y/n");
            }
        }

        KeyCode::Char('X') => {
            app.delete_selected().unwrap_or_else(|e| app.status = format!("Error: {e}"));
        }

        KeyCode::Char('A') => {
            app.toggle_show_completed().unwrap_or_else(|e| app.status = format!("Error: {e}"));
        }

        KeyCode::Char('r') => {
            app.refresh().unwrap_or_else(|e| app.status = format!("Error: {e}"));
        }

        KeyCode::Char('o') | KeyCode::Char('O') => {
            app.should_quit = true;
        }

        _ => {}
    }
    Ok(())
}

fn handle_input_mode(app: &mut App, code: KeyCode, action: InputAction) -> Result<()> {
    let is_task = matches!(action, InputAction::Add | InputAction::Edit);

    match code {
        KeyCode::Esc => {
            if is_task && !app.completions.is_empty() {
                app.completions.clear();
                app.completion_cursor = 0;
            } else {
                app.mode = Mode::Normal;
                app.input.clear();
                app.input_cursor = 0;
                app.completions.clear();
                if matches!(action, InputAction::Filter) {
                    app.apply_filter();
                }
            }
        }
        KeyCode::Tab => {
            if is_task && !app.completions.is_empty() {
                app.apply_completion();
            }
        }
        KeyCode::Down => {
            if is_task && !app.completions.is_empty() {
                app.completion_next();
            }
        }
        KeyCode::Up => {
            if is_task && !app.completions.is_empty() {
                app.completion_prev();
            }
        }
        KeyCode::Enter => match action {
            InputAction::Filter => app.confirm_filter(),
            InputAction::Add    => app.confirm_add().unwrap_or_else(|e| app.status = format!("Error: {e}")),
            InputAction::Edit   => app.confirm_edit().unwrap_or_else(|e| app.status = format!("Error: {e}")),
        },
        KeyCode::Backspace => {
            app.input_backspace();
            if is_task { app.update_completions(); }
            else       { app.apply_live_filter(); }
        }
        KeyCode::Char(c) => {
            app.input_char(c);
            if is_task { app.update_completions(); }
            else       { app.apply_live_filter(); }
        }
        _ => {}
    }
    Ok(())
}
