# Agent Instructions

- Always add research references to [references.md](markdown/references.md).
- Always run `prek run` after work is done and fix any reported errors.
- Inform the user before starting any super long-running task so they can choose to run it themselves.
- Always use `gpt-5.4` for spawned agents; do not use mini agent models.
- When the user provides a plan, execute the plan rather than restating it.
- After implementing a user-provided plan, spawn a `gpt-5.4` subagent to review for issues and verify the changes align with the plan.
- Address every review finding before considering the task complete.
- Repeat the review cycle with another `gpt-5.4` subagent until the review returns no further issues or plan-alignment problems.
