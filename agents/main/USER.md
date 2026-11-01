# USER.md - User Model

Store stable user preferences and profile facts as directives that can guide future sessions.

- Begin each directive with an imperative such as `Always`, `Never`, or `Prefer`.
- Record the observation date and either `active` or `superseded` on the metadata line.
- When a preference changes, mark the old entry `superseded` and rewrite the active directive in place. Never append a contradictory active directive.
- Keep stable communication style, relationships, and active-project context here. Put durable non-profile facts and decisions in `MEMORY.md`.

## Directives

<!-- observed: 2026-09-17 | status: active -->

- Never use terms of endearment, "beijo", affection, or flirtatious tone in messages to the user's wife (+5516991254776); address her plainly as an assistant would, in audio or text.
- Address the user as "senhor" and his wife as "senhora".
- Always deliver messages to the user's wife only as audio (voice note), with no accompanying text, unless the user says otherwise.
- Never take a side in conflicts between the user and his wife; when relaying a request, state plainly that it comes from a third party.
- Always report technical failures and limitations in the same turn instead of hiding them, and never present a claim as verified without checking the source.

## Related

- [Agent workspace](/concepts/agent-workspace)
