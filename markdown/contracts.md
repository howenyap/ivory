# Experiment Contract

The machine-readable contract for Phase 0b lives in [`configs/experiment.toml`](../configs/experiment.toml) and the JSON files under [`schemas/`](../schemas). Those files are authoritative.

The frozen modeling grain is `successful_observation`. The final `features` artifact contains one row per successful `observation_id`, where `observation_id` is the surviving successful `run_attempt_id` for a `query_instance_id` at a specific `scale_factor`.

The canonical identifiers have fixed meanings across all later phases:

- `template_id`: normalized SQL template before parameter binding
- `parameter_set_id`: concrete parameter bundle applied to a template
- `query_instance_id`: rendered query produced from `template_id`, `parameter_set_id`, and `scale_factor`
- `scale_factor`: TPC-H scale factor used to select the PostgreSQL database
- `run_attempt_id`: one execution attempt for a query instance, including retries
- `observation_id`: the row identifier carried through artifacts; in `raw_runs` it matches `run_attempt_id`, and in the final modeling dataset it is the successful attempt identifier

`sql_features` and `plan_features` are query-instance-level artifacts. They are broadcast onto the observation-level final dataset by joining on `query_instance_id`, `template_id`, `parameter_set_id`, and `scale_factor`. Later phases must not invent a second broadcast policy.

Failure semantics are fixed as follows:

- failed executions remain in `raw_runs` with `run_status = failed`
- timed out executions remain in `raw_runs` with `run_status = timed_out`
- intentionally removed rows use `run_status = excluded` plus `exclusion_stage` and `exclusion_reason`
- retries remain as separate rows with unique `run_attempt_id` values and `is_retry = true` after the first attempt
- rows excluded because SQL or plan features cannot be produced remain documented in `raw_runs` and do not appear in final `features`

The null policy for final modeling data is also fixed. Nullable source features remain nullable in the machine-readable schema, and the final dataset must expose explicit null-indicator columns describing which feature families were missing. Rows are excluded only when required targets for a successful observation do not exist.
