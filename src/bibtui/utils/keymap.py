"""Central key-string constants for shortcuts that need a Cmd (super) alias.

Every ctrl-based Binding that should also fire on macOS terminals capable of
forwarding Cmd as ``super`` (Kitty, WezTerm, Ghostty, iTerm2 3.5+ with the
Kitty keyboard protocol enabled) gets its key string defined here once,
instead of being duplicated as a literal string at each Binding call site.

Ctrl is never removed — on terminals that don't forward Cmd (the default on
macOS: Terminal.app, stock iTerm2), Cmd+key never reaches the app at all, so
these are additive aliases, not a platform-conditional swap. No
``platform.system()`` branching is needed: ``super+`` simply never fires on
a terminal/OS that doesn't produce it.

NOTE: this module is the source of truth only for the *Binding* key strings.
Two other places describe these shortcuts in prose and are NOT derived from
here — update them by hand alongside any change to this file:
  - ``_HELP_PARTS`` in src/bibtui/widgets/modals.py (in-app ``?`` help screen)
  - docs/keybindings.md (project docs)
"""

COPY_KEY = "ctrl+c,super+c"
COPY_ENTRY = "ctrl+shift+c,super+shift+c"
SAVE = "ctrl+s,super+s"
COMMAND_PALETTE = "ctrl+p,super+p"
