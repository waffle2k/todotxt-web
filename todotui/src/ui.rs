use crate::app::{App, Mode};
use ratatui::{
    Frame,
    layout::{Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Clear, List, ListItem, ListState, Paragraph},
};

const GREEN: Color = Color::Green;
const BRIGHT: Color = Color::LightGreen;
const DIM: Color = Color::Rgb(0, 100, 0);
const BLACK: Color = Color::Black;
const YELLOW: Color = Color::Yellow;

fn base_style() -> Style {
    Style::default().fg(GREEN).bg(BLACK)
}

fn bright_style() -> Style {
    Style::default().fg(BRIGHT).bg(BLACK).add_modifier(Modifier::BOLD)
}

fn dim_style() -> Style {
    Style::default().fg(DIM).bg(BLACK)
}

const HEADER: &str = r#"
 ████████╗ ██████╗ ██████╗  ██████╗     ████████╗██╗   ██╗██╗
    ╚══██╔╝██╔═══██╗██╔══██╗██╔═══██╗      ██╔══╝██║   ██║██║
       ██║ ██║   ██║██║  ██║██║   ██║      ██║   ██║   ██║██║
       ██║ ██║   ██║██║  ██║██║   ██║      ██║   ██║   ██║██║
       ██║ ╚██████╔╝██████╔╝╚██████╔╝      ██║   ╚██████╔╝██║
       ╚═╝  ╚═════╝ ╚═════╝  ╚═════╝       ╚═╝    ╚═════╝ ╚═╝
"#;

pub fn draw(f: &mut Frame, app: &App) {
    let area = f.area();
    f.render_widget(Block::default().style(base_style()), area);

    if app.show_banner {
        let header_height = HEADER.lines().count() as u16;
        let chunks = Layout::default()
            .direction(Direction::Vertical)
            .constraints([
                Constraint::Length(header_height),
                Constraint::Min(3),
                Constraint::Length(1),
                Constraint::Length(1),
            ])
            .split(area);
        draw_header(f, chunks[0]);
        draw_list(f, app, chunks[1]);
        draw_filter_bar(f, app, chunks[2]);
        draw_status(f, app, chunks[3]);
    } else {
        let chunks = Layout::default()
            .direction(Direction::Vertical)
            .constraints([
                Constraint::Min(3),
                Constraint::Length(1),
                Constraint::Length(1),
            ])
            .split(area);
        draw_list(f, app, chunks[0]);
        draw_filter_bar(f, app, chunks[1]);
        draw_status(f, app, chunks[2]);
    }

    if matches!(app.mode, Mode::AddTask | Mode::EditTask) {
        draw_input_popup(f, app, area);
    }
}

fn draw_header(f: &mut Frame, area: Rect) {
    let para = Paragraph::new(HEADER)
        .style(bright_style())
        .block(Block::default().borders(Borders::NONE));
    f.render_widget(para, area);
}

fn draw_list(f: &mut Frame, app: &App, area: Rect) {
    let block = Block::default()
        .borders(Borders::ALL)
        .border_style(base_style())
        .title(Span::styled(" TASKS ", bright_style()));

    let items: Vec<ListItem> = app.filtered.iter().map(|&i| {
        let task = &app.tasks[i];
        let is_selected = app.selected.contains(&task.id);

        let pri_tag = match task.priority.as_deref() {
            Some("A") => "[A]",
            Some("B") => "[B]",
            Some("C") => "[C]",
            Some(p)   => p,
            None       => "[ ]",
        };

        let pri_style = match task.priority.as_deref() {
            Some("A") => Style::default().fg(BRIGHT).bg(BLACK).add_modifier(Modifier::BOLD),
            Some("B") => Style::default().fg(GREEN).bg(BLACK),
            _         => dim_style(),
        };

        let check = if is_selected { "◆" } else { " " };
        let done_mark = if task.completed { "✓ " } else { "  " };

        let desc_style = if task.completed {
            dim_style().add_modifier(Modifier::CROSSED_OUT)
        } else {
            base_style()
        };

        // projects and contexts in a different shade
        let projs: String = task.projects.iter().map(|p| format!(" +{p}")).collect();
        let ctxs: String = task.contexts.iter().map(|c| format!(" @{c}")).collect();

        let line = Line::from(vec![
            Span::styled(format!("{check} "), Style::default().fg(YELLOW).bg(BLACK)),
            Span::styled(format!("{pri_tag} "), pri_style),
            Span::styled(done_mark, dim_style()),
            Span::styled(task.description.clone(), desc_style),
            Span::styled(projs, Style::default().fg(DIM).bg(BLACK)),
            Span::styled(ctxs, Style::default().fg(DIM).bg(BLACK)),
        ]);

        ListItem::new(line)
    }).collect();

    let mut state = ListState::default();
    if !app.filtered.is_empty() {
        state.select(Some(app.cursor));
    }

    let list = List::new(items)
        .block(block)
        .highlight_style(
            Style::default()
                .fg(BLACK)
                .bg(GREEN)
                .add_modifier(Modifier::BOLD),
        )
        .highlight_symbol("▶ ");

    f.render_stateful_widget(list, area, &mut state);
}

fn draw_filter_bar(f: &mut Frame, app: &App, area: Rect) {
    let content = if app.mode == Mode::Filter {
        format!(" /{}_", app.input)
    } else if !app.filter.is_empty() {
        format!(" filter: {} ({} tasks)", app.filter, app.filtered.len())
    } else {
        String::new()
    };

    let para = Paragraph::new(content).style(bright_style());
    f.render_widget(para, area);
}

fn draw_status(f: &mut Frame, app: &App, area: Rect) {
    let help = if app.mode == Mode::Filter {
        " Enter:apply  Esc:cancel".to_string()
    } else if app.mode == Mode::ConfirmDelete {
        " y:confirm delete  n/Esc:cancel".to_string()
    } else {
        let sel = if app.selected.is_empty() {
            String::new()
        } else {
            format!("  [{}sel] X:del-sel  O:out-sel", app.selected.len())
        };
        format!(
            " j/k:move  Space:select  a:add  e:edit  d:done  D:delete  /:filter  A:toggle-done  r:refresh  q:quit{}",
            sel
        )
    };

    let style = dim_style();
    let para = Paragraph::new(help).style(style);
    f.render_widget(para, area);
}

fn draw_input_popup(f: &mut Frame, app: &App, area: Rect) {
    let title = if app.mode == Mode::AddTask { " ADD TASK " } else { " EDIT TASK " };

    let popup_width = area.width.saturating_sub(8).max(20);
    let popup_x = (area.width.saturating_sub(popup_width)) / 2;
    let popup_rect = Rect::new(popup_x, area.height / 2 - 2, popup_width, 4);

    f.render_widget(Clear, popup_rect);

    let block = Block::default()
        .borders(Borders::ALL)
        .border_style(bright_style())
        .title(Span::styled(title, bright_style()))
        .style(base_style());

    let inner = block.inner(popup_rect);
    f.render_widget(block, popup_rect);

    let display = format!("{}_", app.input);
    let para = Paragraph::new(display).style(bright_style());
    f.render_widget(para, inner);
}
