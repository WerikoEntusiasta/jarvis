# USER.md - User Model

Store stable user preferences and profile facts as directives that can guide future sessions.

- Begin each directive with an imperative such as `Always`, `Never`, or `Prefer`.
- Record the observation date and either `active` or `superseded` on the metadata line.
- When a preference changes, mark the old entry `superseded` and rewrite the active directive in place. Never append a contradictory active directive.

## Directives

<!-- observed: 2026-09-17 | status: active -->

- Treat the n8n instance at `http://192.168.3.6:5678` as the live target for this agent's work.
- Always validate a workflow (node configs, then full graph) before creating it on the instance.
- Never place credentials or tokens in workflow code; reference them by credential ID.
- Report tool failures and blockers plainly in the same turn, with the exact error.
- Prefer the official n8n MCP server tools over hand-writing workflow JSON.

## Related

- [Agent workspace](/concepts/agent-workspace)
