# App Forge skill

When the user wants an app, site, tool, or prototype built ("build me…",
"make an app for…", "scaffold…"), use the `forge_app` tool.

How it works:
1. Call `forge_app` with a clear `description` of what to build and a
   kebab-case `project_name`.
2. Forge designs the project and writes real, runnable files under
   `data/forged/<project-name>/`.
3. Summarize what was built: the stack, the file list, and how to run it.
4. If the user wants changes, describe the change and call `forge_app`
   again — or tell them which file to edit.

Rules:
- Keep descriptions concrete ("a todo app with localStorage", not "something cool").
- Never write outside `data/forged/` — the sandbox is a safety boundary.
- Generated code is a starting point; review before deploying anywhere.
