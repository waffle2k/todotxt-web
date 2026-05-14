# todotui

A retro green-on-black terminal UI for [todotxt-web](https://github.com/waffle2k/todotxt-web), written in Rust.

## Build

Requires Rust (stable). Build and install the binary:

```bash
cargo build --release
cp target/release/todotui ~/bin/todotui
```

## Configuration

Credentials are read from environment variables, with `~/.config/todotui/config` as a fallback. Environment variables take precedence.

**Config file** (`~/.config/todotui/config`):

```ini
# URL of the todotxt-web instance (default: http://localhost:5000)
TODO_URL=https://todo.example.com
TODO_USER=youruser
TODO_PASS=yourpassword
```

`TODO_USER` and `TODO_PASS` are required — the binary will error if neither source provides them.

## Usage

```
todotui          # launch interactive TUI
todotui --list   # print all open tasks to stdout (id<TAB>raw_line), no TUI
```

### Interactive keybindings

| Key | Action |
|-----|--------|
| `j` / `k` / arrows | Navigate |
| `Space` | Toggle select |
| `*` / `\` | Select all / deselect all |
| `/` | Regex filter |
| `c` | Clear filter |
| `a` | Add task |
| `e` | Edit task |
| `d` / Enter | Toggle complete/incomplete |
| `D` | Delete (confirm with `y`) |
| `X` | Bulk delete selected |
| `A` | Toggle show completed tasks |
| `r` | Refresh |
| `q` / `o` / Esc | Quit (prints selected tasks to stdout) |

On quit, any selected tasks are printed as raw todo.txt lines to stdout.

### Shell / fzf integration

`--list` outputs tasks as `id<TAB>raw_line`, one per line — no TUI, suitable for piping:

```bash
# Interactive pick with fzf, then mark done
todotui --list | fzf --multi --with-nth=2.. | cut -f1 | xargs -I{} todo do {}

# Pre-filter by project, then pick
todotui --list | grep '+homelab' | fzf --with-nth=2..
```

The filter (`/`) accepts full regex (Rust `regex` crate syntax):

```
/\+homelab       tasks tagged +homelab
/@home           tasks with @home context
/ryzen|email     OR match
```
