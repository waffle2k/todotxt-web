-- Load the local todo.txt plugin
return {
  {
    name   = "todo-txt",
    dir    = vim.fn.stdpath("config"),
    lazy   = false,
    config = function()
      require("todo").setup({
        key = "<leader>td",  -- open the floating window
      })
    end,
  },
}
