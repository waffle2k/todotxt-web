use crate::api::{Task, TodoApi};
use anyhow::Result;
use regex::Regex;
use std::collections::HashSet;

#[derive(Debug, Clone, PartialEq)]
pub enum Mode {
    Normal,
    Filter,
    AddTask,
    EditTask,
    ConfirmDelete,
}

pub struct App {
    pub api: TodoApi,
    pub tasks: Vec<Task>,
    pub filtered: Vec<usize>,  // indices into tasks
    pub cursor: usize,
    pub selected: HashSet<usize>,  // task ids
    pub mode: Mode,
    pub input: String,
    pub input_cursor: usize,
    pub filter: String,
    pub show_completed: bool,
    pub status: String,
    pub should_quit: bool,
    pub show_banner: bool,
    #[allow(dead_code)]
    pub pick_mode: bool,
    editing_id: Option<usize>,
    pub completions: Vec<String>,
    pub completion_cursor: usize,
}

impl App {
    pub fn new(api: TodoApi, pick_mode: bool) -> Self {
        Self {
            api,
            tasks: vec![],
            filtered: vec![],
            cursor: 0,
            selected: HashSet::new(),
            mode: Mode::Normal,
            input: String::new(),
            input_cursor: 0,
            filter: String::new(),
            show_completed: false,
            status: String::from("Loading…"),
            should_quit: false,
            show_banner: true,
            pick_mode,
            editing_id: None,
            completions: vec![],
            completion_cursor: 0,
        }
    }

    pub fn refresh(&mut self) -> Result<()> {
        let completed = if self.show_completed { "all" } else { "incomplete" };
        self.tasks = self.api.list_tasks("", completed)?;
        self.apply_filter();
        self.status = format!("{} tasks", self.filtered.len());
        Ok(())
    }

    fn filter_by(&mut self, pattern: &str) {
        if pattern.is_empty() {
            self.filtered = (0..self.tasks.len()).collect();
        } else {
            match Regex::new(pattern) {
                Ok(re) => {
                    self.filtered = (0..self.tasks.len())
                        .filter(|&i| re.is_match(&self.tasks[i].raw_line))
                        .collect();
                }
                Err(_) => {
                    // fallback to literal substring match on regex error
                    let lower = pattern.to_lowercase();
                    self.filtered = (0..self.tasks.len())
                        .filter(|&i| self.tasks[i].raw_line.to_lowercase().contains(&lower))
                        .collect();
                }
            }
        }
        self.cursor = self.cursor.min(self.filtered.len().saturating_sub(1));
    }

    pub fn apply_filter(&mut self) {
        let pattern = self.filter.clone();
        self.filter_by(&pattern);
    }

    /// Filter live against the current input without committing self.filter.
    pub fn apply_live_filter(&mut self) {
        let pattern = self.input.clone();
        self.filter_by(&pattern);
    }

    pub fn current_task(&self) -> Option<&Task> {
        self.filtered.get(self.cursor).and_then(|&i| self.tasks.get(i))
    }

    pub fn move_up(&mut self) {
        if self.cursor > 0 {
            self.cursor -= 1;
        }
    }

    pub fn move_down(&mut self) {
        if self.cursor + 1 < self.filtered.len() {
            self.cursor += 1;
        }
    }

    pub fn go_top(&mut self) {
        self.cursor = 0;
    }

    pub fn go_bottom(&mut self) {
        self.cursor = self.filtered.len().saturating_sub(1);
    }

    pub fn toggle_select(&mut self) {
        if let Some(t) = self.current_task() {
            let id = t.id;
            if self.selected.contains(&id) {
                self.selected.remove(&id);
            } else {
                self.selected.insert(id);
            }
        }
    }

    pub fn select_all(&mut self) {
        for &i in &self.filtered {
            if let Some(t) = self.tasks.get(i) {
                self.selected.insert(t.id);
            }
        }
    }

    pub fn deselect_all(&mut self) {
        self.selected.clear();
    }

    pub fn toggle_complete_current(&mut self) -> Result<()> {
        if let Some(t) = self.current_task() {
            let id = t.id;
            self.api.toggle_complete(id)?;
        }
        self.refresh()
    }

    pub fn delete_current(&mut self) -> Result<()> {
        if let Some(t) = self.current_task() {
            let id = t.id;
            self.api.delete_task(id)?;
        }
        self.refresh()
    }

    pub fn delete_selected(&mut self) -> Result<()> {
        let ids: Vec<usize> = self.selected.iter().copied().collect();
        for id in ids {
            self.api.delete_task(id)?;
        }
        self.selected.clear();
        self.refresh()
    }

    pub fn start_add(&mut self) {
        self.mode = Mode::AddTask;
        self.input.clear();
        self.input_cursor = 0;
    }

    pub fn start_edit(&mut self) {
        if let Some(t) = self.current_task() {
            let id = t.id;
            let desc = t.description.clone();
            self.editing_id = Some(id);
            self.input_cursor = desc.len();
            self.input = desc;
            self.mode = Mode::EditTask;
        }
    }

    pub fn start_filter(&mut self) {
        self.mode = Mode::Filter;
        self.input = self.filter.clone();
        self.input_cursor = self.input.len();
    }

    /// Rebuild completions based on `@` / `+` token immediately before the cursor.
    pub fn update_completions(&mut self) {
        let before = &self.input[..self.input_cursor];
        // find the last @ or + that isn't preceded by a non-space (i.e. it starts a token)
        let trigger_pos = before.rfind(|c| c == '@' || c == '+');
        if let Some(pos) = trigger_pos {
            let partial = &before[pos + 1..];
            // dismiss if the partial contains a space — we've moved past this token
            if partial.contains(' ') {
                self.completions.clear();
                return;
            }
            let trigger = before.chars().nth(pos).unwrap();
            let partial_lower = partial.to_lowercase();
            let mut candidates: Vec<String> = if trigger == '@' {
                let mut set = HashSet::new();
                for t in &self.tasks { for c in &t.contexts { set.insert(c.clone()); } }
                set.into_iter().collect()
            } else {
                let mut set = HashSet::new();
                for t in &self.tasks { for p in &t.projects { set.insert(p.clone()); } }
                set.into_iter().collect()
            };
            candidates.retain(|c| c.to_lowercase().starts_with(&partial_lower));
            candidates.sort();
            self.completions = candidates;
            self.completion_cursor = 0;
        } else {
            self.completions.clear();
        }
    }

    /// Insert the highlighted completion into the input, replacing the partial token.
    pub fn apply_completion(&mut self) {
        if self.completions.is_empty() { return; }
        let selected = self.completions[self.completion_cursor].clone();
        let before = self.input[..self.input_cursor].to_string();
        if let Some(pos) = before.rfind(|c: char| c == '@' || c == '+') {
            let after = &self.input[self.input_cursor..];
            let space = if after.starts_with(' ') { "" } else { " " };
            self.input = format!("{}{}{}{}", &self.input[..=pos], selected, space, after);
            self.input_cursor = pos + 1 + selected.len() + space.len();
        }
        self.completions.clear();
        self.completion_cursor = 0;
    }

    pub fn completion_next(&mut self) {
        if !self.completions.is_empty() {
            self.completion_cursor = (self.completion_cursor + 1) % self.completions.len();
        }
    }

    pub fn completion_prev(&mut self) {
        if !self.completions.is_empty() {
            self.completion_cursor = self.completion_cursor
                .checked_sub(1)
                .unwrap_or(self.completions.len() - 1);
        }
    }

    pub fn confirm_add(&mut self) -> Result<()> {
        let raw = self.input.trim().to_string();
        if !raw.is_empty() {
            self.api.add_task(&raw, "", "", "")?;
        }
        self.mode = Mode::Normal;
        self.input.clear();
        self.input_cursor = 0;
        self.completions.clear();
        self.refresh()
    }

    pub fn confirm_edit(&mut self) -> Result<()> {
        if let Some(id) = self.editing_id {
            let raw = self.input.trim().to_string();
            if !raw.is_empty() {
                // find priority/projects/contexts from original task for preservation
                if let Some(t) = self.tasks.iter().find(|t| t.id == id) {
                    let pri = t.priority.as_deref().unwrap_or("");
                    let projs = t.projects.join(",");
                    let ctxs = t.contexts.join(",");
                    self.api.edit_task(id, &raw, pri, &projs, &ctxs)?;
                }
            }
        }
        self.mode = Mode::Normal;
        self.editing_id = None;
        self.input.clear();
        self.input_cursor = 0;
        self.completions.clear();
        self.refresh()
    }

    pub fn confirm_filter(&mut self) {
        self.filter = self.input.clone();
        self.mode = Mode::Normal;
        self.apply_filter();
        self.status = format!("{} tasks (filter: {})", self.filtered.len(), self.filter);
    }

    pub fn clear_filter(&mut self) {
        self.filter.clear();
        self.apply_filter();
        self.status = format!("{} tasks", self.filtered.len());
    }

    pub fn input_char(&mut self, c: char) {
        self.input.insert(self.input_cursor, c);
        self.input_cursor += c.len_utf8();
    }

    pub fn input_backspace(&mut self) {
        if self.input_cursor > 0 {
            let prev = self.input[..self.input_cursor]
                .char_indices()
                .last()
                .map(|(i, _)| i)
                .unwrap_or(0);
            self.input.remove(prev);
            self.input_cursor = prev;
        }
    }

    pub fn get_selected_tasks(&self) -> Vec<&Task> {
        self.tasks.iter().filter(|t| self.selected.contains(&t.id)).collect()
    }

    pub fn toggle_show_completed(&mut self) -> Result<()> {
        self.show_completed = !self.show_completed;
        self.refresh()
    }
}
