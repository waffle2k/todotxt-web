-- todo.lua — floating-window todo.txt UI backed by ~/bin/todo
local M = {}

local TODO_CMD = vim.fn.expand("~/bin/todo")
local NS = vim.api.nvim_create_namespace("todo-txt")
local state = { buf = nil, win = nil, tasks = {}, mode = "incomplete" }

-- ── Highlights ────────────────────────────────────────────────────────────────

local function setup_hl()
  vim.api.nvim_set_hl(0, "TodoPriA",  { link = "DiagnosticError",   default = true })
  vim.api.nvim_set_hl(0, "TodoPriB",  { link = "DiagnosticWarn",    default = true })
  vim.api.nvim_set_hl(0, "TodoPriC",  { link = "DiagnosticInfo",    default = true })
  vim.api.nvim_set_hl(0, "TodoDone",  { link = "Comment",           default = true })
  vim.api.nvim_set_hl(0, "TodoId",    { link = "LineNr",            default = true })
  vim.api.nvim_set_hl(0, "TodoCtx",   { link = "Special",           default = true })
  vim.api.nvim_set_hl(0, "TodoProj",  { link = "Identifier",        default = true })
  vim.api.nvim_set_hl(0, "TodoPri",   { link = "Bold",              default = true })
end

-- ── CLI wrapper ───────────────────────────────────────────────────────────────

local function run(args)
  local cmd = { TODO_CMD, "-p" }
  vim.list_extend(cmd, args)
  local r = vim.system(cmd, { text = true }):wait()
  return r.stdout or "", r.stderr or "", r.code
end

-- ── Parsing ───────────────────────────────────────────────────────────────────

local function parse_tasks(raw)
  local tasks = {}
  for line in raw:gmatch("[^\n]+") do
    if not line:match("^%-%-") and not line:match("^TODO:") then
      local id, rest = line:match("^%s*(%d+)%s+(.+)$")
      if id then
        local priority = rest:match("^%(([A-Z])%)")
        local done = rest:match("^x ") and true or false
        table.insert(tasks, {
          id       = tonumber(id),
          text     = rest,
          priority = priority,
          done     = done,
          display  = string.format("%3d  %s", tonumber(id), rest),
        })
      end
    end
  end
  return tasks
end

-- ── Buffer rendering ──────────────────────────────────────────────────────────

local function apply_hl(buf, tasks)
  vim.api.nvim_buf_clear_namespace(buf, NS, 0, -1)
  for i, task in ipairs(tasks) do
    local row = i - 1
    local line = task.display

    -- Whole-line color
    local line_hl = task.done and "TodoDone"
      or (task.priority == "A" and "TodoPriA")
      or (task.priority == "B" and "TodoPriB")
      or (task.priority == "C" and "TodoPriC")
      or nil
    if line_hl then
      vim.api.nvim_buf_add_highlight(buf, NS, line_hl, row, 0, -1)
    end

    -- Task ID
    local id_end = line:find("%s%s")
    if id_end then
      vim.api.nvim_buf_add_highlight(buf, NS, "TodoId", row, 0, id_end)
    end

    -- Priority marker
    local ps, pe = line:find("%(([A-Z])%)")
    if ps then
      vim.api.nvim_buf_add_highlight(buf, NS, "TodoPri", row, ps - 1, pe)
    end

    -- @contexts
    local col = 0
    while true do
      local s, e = line:find("@%S+", col + 1)
      if not s then break end
      vim.api.nvim_buf_add_highlight(buf, NS, "TodoCtx", row, s - 1, e)
      col = e
    end

    -- +projects
    col = 0
    while true do
      local s, e = line:find("%+%S+", col + 1)
      if not s then break end
      vim.api.nvim_buf_add_highlight(buf, NS, "TodoProj", row, s - 1, e)
      col = e
    end
  end
end

local function render(buf, tasks, title_extra)
  local lines = {}
  for _, t in ipairs(tasks) do
    table.insert(lines, t.display)
  end
  if #lines == 0 then
    lines = { "  (no tasks)" }
  end

  vim.bo[buf].modifiable = true
  vim.api.nvim_buf_set_lines(buf, 0, -1, false, lines)
  vim.bo[buf].modifiable = false

  apply_hl(buf, tasks)

  if state.win and vim.api.nvim_win_is_valid(state.win) then
    local count = #tasks
    local label = state.mode == "all" and "all" or "open"
    vim.api.nvim_win_set_config(state.win, {
      title = string.format(" Todo [%s] (%d) ", label, count),
      title_pos = "center",
    })
  end
end

local function refresh()
  if not state.buf or not vim.api.nvim_buf_is_valid(state.buf) then return end
  local completed = state.mode == "all" and "all" or "incomplete"
  local out = run({ "ls" .. (completed == "all" and "a" or ""), })
  -- fallback: call the right subcommand
  if completed == "all" then
    out = run({ "lsa" })
  else
    out = run({ "ls" })
  end
  state.tasks = parse_tasks(out)
  render(state.buf, state.tasks)
end

-- ── Cursor helpers ────────────────────────────────────────────────────────────

local function task_at_cursor()
  if not state.buf then return nil end
  local row = vim.api.nvim_win_get_cursor(0)[1]
  return state.tasks[row]
end

-- ── Actions ───────────────────────────────────────────────────────────────────

local function action_done()
  local task = task_at_cursor()
  if not task then return end
  if task.done then
    vim.notify("Task already done. Press u to undo.", vim.log.levels.WARN)
    return
  end
  run({ "do", tostring(task.id) })
  refresh()
end

local function action_undone()
  local task = task_at_cursor()
  if not task then return end
  if not task.done then
    vim.notify("Task is not done.", vim.log.levels.WARN)
    return
  end
  run({ "undone", tostring(task.id) })
  refresh()
end

local function action_delete()
  local task = task_at_cursor()
  if not task then return end
  local ok, choice = pcall(vim.fn.confirm, "Delete: " .. task.text, "&Yes\n&No", 2)
  if ok and choice == 1 then
    run({ "del", "-f", tostring(task.id) })
    refresh()
  end
end

local function action_add()
  local ok, input = pcall(vim.fn.input, "Add task: ")
  if ok and input ~= "" then
    run({ "add", input })
    refresh()
  end
end

local function action_pri()
  local task = task_at_cursor()
  if not task then return end
  local ok, input = pcall(vim.fn.input, "Priority (A-Z, blank to remove): ", task.priority or "")
  if not ok then return end
  if input == "" then
    run({ "depri", tostring(task.id) })
  else
    run({ "pri", tostring(task.id), input:upper():sub(1, 1) })
  end
  refresh()
end

local function action_edit()
  local task = task_at_cursor()
  if not task then return end
  local ok, input = pcall(vim.fn.input, "Replace task: ", task.text)
  if ok and input ~= "" then
    run({ "replace", tostring(task.id), input })
    refresh()
  end
end

local function action_toggle_all()
  state.mode = state.mode == "all" and "incomplete" or "all"
  refresh()
end

-- ── Window ────────────────────────────────────────────────────────────────────

local function set_keymaps(buf)
  local function map(key, fn, desc)
    vim.keymap.set("n", key, fn, { buffer = buf, nowait = true, desc = desc })
  end
  map("a",     action_add,        "Add task")
  map("<CR>",  action_done,       "Mark done")
  map("d",     action_done,       "Mark done")
  map("u",     action_undone,     "Mark undone")
  map("D",     action_delete,     "Delete task")
  map("p",     action_pri,        "Set priority")
  map("e",     action_edit,       "Edit/replace task")
  map("r",     refresh,           "Refresh")
  map("A",     action_toggle_all, "Toggle show all / open only")
  map("q",     M.close,           "Close")
  map("<Esc>", M.close,           "Close")
  map("?",     M.help,            "Show keymaps")
end

function M.close()
  if state.win and vim.api.nvim_win_is_valid(state.win) then
    vim.api.nvim_win_close(state.win, true)
  end
  state.win = nil
end

function M.help()
  local lines = {
    "  Todo keymaps",
    "  ────────────",
    "  a      Add new task",
    "  <CR>/d Mark task as done",
    "  u      Mark task as undone",
    "  D      Delete task",
    "  p      Set / clear priority",
    "  e      Edit / replace task",
    "  r      Refresh",
    "  A      Toggle open / all tasks",
    "  q/Esc  Close",
    "  ?      This help",
  }
  vim.notify(table.concat(lines, "\n"), vim.log.levels.INFO)
end

function M.open()
  setup_hl()

  -- Reuse existing window if open
  if state.win and vim.api.nvim_win_is_valid(state.win) then
    vim.api.nvim_set_current_win(state.win)
    refresh()
    return
  end

  local width  = math.max(60, math.floor(vim.o.columns * 0.75))
  local height = math.max(10, math.floor(vim.o.lines   * 0.55))
  local row    = math.floor((vim.o.lines   - height) / 2)
  local col    = math.floor((vim.o.columns - width)  / 2)

  local buf = vim.api.nvim_create_buf(false, true)
  vim.bo[buf].filetype    = "todo"
  vim.bo[buf].bufhidden   = "wipe"
  vim.bo[buf].modifiable  = false
  vim.bo[buf].buftype     = "nofile"

  local win = vim.api.nvim_open_win(buf, true, {
    relative   = "editor",
    width      = width,
    height     = height,
    row        = row,
    col        = col,
    style      = "minimal",
    border     = "rounded",
    title      = " Todo ",
    title_pos  = "center",
  })
  vim.wo[win].cursorline  = true
  vim.wo[win].wrap        = false
  vim.wo[win].number      = false

  state.buf  = buf
  state.win  = win
  state.mode = "incomplete"

  set_keymaps(buf)

  vim.api.nvim_create_autocmd("WinClosed", {
    buffer  = buf,
    once    = true,
    callback = function()
      state.win = nil
      state.buf = nil
    end,
  })

  refresh()
end

-- ── :Todo command ─────────────────────────────────────────────────────────────

function M.cmd(opts)
  local args = vim.split(opts.args, "%s+", { trimempty = true })
  if #args == 0 then
    M.open(); return
  end
  local out, err, code = run(args)
  local msg = (out ~= "" and out or err):gsub("\n$", "")
  vim.notify(msg, code == 0 and vim.log.levels.INFO or vim.log.levels.ERROR)
end

function M.complete(lead, line, _)
  local cmds = {
    "add", "addm", "append", "app", "archive", "deduplicate",
    "del", "rm", "depri", "dp", "do", "list", "ls", "listall", "lsa",
    "listcon", "lsc", "listproj", "lsprj", "listpri", "lsp",
    "prepend", "prep", "pri", "p", "replace", "report", "undone", "u",
  }
  local parts = vim.split(line, "%s+")
  if #parts <= 2 then
    return vim.tbl_filter(function(c) return c:find("^" .. lead) end, cmds)
  end
  return {}
end

-- ── Setup ─────────────────────────────────────────────────────────────────────

function M.setup(opts)
  opts = opts or {}
  setup_hl()

  vim.api.nvim_create_user_command("Todo", M.cmd, {
    nargs       = "*",
    complete    = M.complete,
    desc        = "Run todo CLI command or open todo window",
  })

  -- Let :todo expand to :Todo (Neovim commands must start uppercase)
  vim.cmd("cabbrev todo Todo")

  local key = (opts.key or "<leader>td")
  vim.keymap.set("n", key, M.open, { desc = "Open todo list" })
end

return M
