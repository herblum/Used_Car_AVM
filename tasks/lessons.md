# Lessons Learned

## Session Start Protocol

**Rule**: At the start of every session working in this project, ALWAYS read `tasks/todo.md` before doing anything else — including before exploring code or responding to the first user request.

**Why**: The todo.md contains the full project state, architecture decisions, current metrics, and what's been completed. Without it, you start cold and waste time re-deriving context that's already documented. The user had to stop and correct this mistake.

**How to apply**: First tool call of any session in `UC_AVM project/` must be reading `tasks/todo.md`. If already in plan mode or responding to a first message, still read it before exploring or spawning agents.
