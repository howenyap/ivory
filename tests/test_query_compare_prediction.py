from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Any

import polars as pl

import ivory.query_compare_prediction as query_compare_prediction
import ivory.query_compare_validation as query_compare_validation


def test_load_selected_estimator_uses_manifest_selected_family(tmp_path: Path) -> None:
    estimator_path = tmp_path / "selected.pkl"
    estimator_path.write_bytes(pickle.dumps({"sentinel": "ok"}))
    manifest_path = tmp_path / "training_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "selected_model_family_per_target": {
                    "planner_total_cost": "random_forest"
                },
                "final_model_input_columns_per_model": {
                    "random_forest": {"planner_total_cost": ["feature_a", "feature_b"]}
                },
                "model_artifact_paths": {
                    "planner_total_cost": {"random_forest": "selected.pkl"}
                },
            }
        )
    )

    original_root = query_compare_prediction.ROOT_DIR
    query_compare_prediction.ROOT_DIR = tmp_path
    try:
        family, feature_columns, estimator = (
            query_compare_prediction.load_selected_estimator(
                manifest_path=manifest_path
            )
        )
    finally:
        query_compare_prediction.ROOT_DIR = original_root

    assert family == "random_forest"
    assert feature_columns == ["feature_a", "feature_b"]
    assert estimator == {"sentinel": "ok"}


def test_load_formulations_uses_query_compare_paths_and_skips_excluded_templates(
    tmp_path: Path,
) -> None:
    benchmark_path = tmp_path / "benchmark.json"
    benchmark_path.write_text(
        json.dumps(
            {
                "templates": [
                    {
                        "template_id": "q3",
                        "template_status": "included",
                        "parameter_set_id": "q3-p0000",
                        "scale_factor": 1.0,
                        "baseline_sql": "select 1;\n",
                        "baseline_sql_path": "query_compare/sql/custom_q3_base.sql",
                        "accepted_formulations": [
                            {
                                "formulation_id": "q3_alt_1",
                                "formulation_type": "explicit_inner_join",
                                "sql": "select 2;\n",
                                "sql_path": (
                                    "query_compare/sql/custom_q3_formulation.sql"
                                ),
                            }
                        ],
                    },
                    {
                        "template_id": "q4",
                        "template_status": "excluded_after_screening",
                        "parameter_set_id": "q4-p0000",
                        "scale_factor": 1.0,
                        "accepted_formulations": [],
                    },
                ]
            }
        )
    )

    formulations = query_compare_prediction.load_formulations(
        benchmark_path=benchmark_path
    )

    assert [formulation.formulation_label for formulation in formulations] == [
        "baseline",
        "q3_alt_1",
    ]
    assert formulations[0].sql_path == "query_compare/sql/custom_q3_base.sql"
    assert formulations[1].sql_path == "query_compare/sql/custom_q3_formulation.sql"


def test_query_compare_validation_parser_defaults_use_query_compare_paths() -> None:
    parser = query_compare_validation._build_parser()
    args = parser.parse_args([])

    assert args.benchmark.endswith("query_compare/benchmark.json")
    assert args.output.endswith(
        "query_compare/results/validation/query_compare_validation_sf_1.json"
    )


def test_query_compare_prediction_parser_defaults_use_query_compare_paths() -> None:
    parser = query_compare_prediction._build_parser()
    args = parser.parse_args([])

    assert args.benchmark.endswith("query_compare/benchmark.json")
    assert args.output.endswith(
        "query_compare/results/predictions/query_compare_predictions_sf_1.parquet"
    )
    assert args.summary_output.endswith(
        "query_compare/results/predictions/query_compare_predictions_sf_1.json"
    )
    assert args.explain_dir.endswith("query_compare/results/explains")
    assert args.analyze is False


def test_build_feature_frame_constructs_modeling_input() -> None:
    formulation = query_compare_prediction.Formulation(
        template_id="q3",
        formulation_label="baseline",
        formulation_kind="baseline",
        parameter_set_id="q3-p0000",
        scale_factor=1.0,
        sql_text="select sum(x) from foo where y = 1 order by 1 limit 1;\n",
        sql_path="query_compare/sql/q3_base.sql",
    )
    plan_document = {
        "Plan": {
            "Node Type": "Limit",
            "Plan Rows": 1,
            "Plan Width": 8,
            "Startup Cost": 0.0,
            "Total Cost": 12.5,
            "Plans": [
                {
                    "Node Type": "Aggregate",
                    "Plan Rows": 1,
                    "Plan Width": 8,
                    "Startup Cost": 0.0,
                    "Total Cost": 12.0,
                    "Plans": [
                        {
                            "Node Type": "Seq Scan",
                            "Plan Rows": 10,
                            "Plan Width": 4,
                            "Startup Cost": 0.0,
                            "Total Cost": 10.0,
                        }
                    ],
                }
            ],
        }
    }

    feature_df = query_compare_prediction.build_feature_frame(
        formulation=formulation,
        plan_document=plan_document,
    )
    row = feature_df.to_dicts()[0]

    assert row["observation_id"] == "q3__baseline"
    assert row["query_instance_id"] == "q3__baseline"
    assert row["sql_features_broadcast"] is True
    assert row["plan_features_broadcast"] is False
    assert row["targets"]["planner_total_cost"] == 12.5
    assert row["targets"]["execution_time_ms"] is None
    assert row["sql_features"]["aggregation_present"] is True
    assert row["sql_features"]["limit_count"] == 1
    assert row["plan_features"]["plan_node_count"] == 3
    assert row["plan_features"]["planner_total_cost"] == 12.5


def test_predict_query_compare_costs_writes_ranked_outputs(
    monkeypatch, tmp_path: Path
) -> None:
    benchmark_path = tmp_path / "benchmark.json"
    benchmark_path.write_text(
        json.dumps(
            {
                "templates": [
                    {
                        "template_id": "q3",
                        "parameter_set_id": "q3-p0000",
                        "scale_factor": 1.0,
                        "baseline_sql": "select 1;\n",
                        "baseline_sql_path": "query_compare/sql/q3_base.sql",
                        "accepted_formulations": [
                            {
                                "formulation_id": "q3_alt_1",
                                "formulation_type": "explicit_inner_join",
                                "sql": "select 2;\n",
                                "sql_path": (
                                    "query_compare/sql/"
                                    "q3_formulation_1_explicit_inner_join.sql"
                                ),
                            }
                        ],
                    }
                ]
            }
        )
    )
    output_path = tmp_path / "predictions.parquet"
    summary_output_path = tmp_path / "predictions.json"
    explain_dir = tmp_path / "explains"
    manifest_path = tmp_path / "training_manifest.json"

    class FakeEstimator:
        def predict(self, matrix: Any) -> list[float]:
            values = matrix.tolist()
            return [values[0][0]]

    monkeypatch.setattr(
        query_compare_prediction,
        "load_selected_estimator",
        lambda **_: ("random_forest", ["feature_0"], FakeEstimator()),
    )
    monkeypatch.setattr(
        query_compare_prediction,
        "fetch_explain_plan",
        lambda **kwargs: {
            "Plan": {
                "Node Type": "Seq Scan",
                "Plan Rows": 10,
                "Plan Width": 5,
                "Startup Cost": 0.0,
                "Total Cost": 10.0 if "select 1" in kwargs["sql_text"] else 8.0,
            },
            "Execution Time": 15.0 if "select 1" in kwargs["sql_text"] else 9.0,
        },
    )
    monkeypatch.setattr(
        query_compare_prediction,
        "build_feature_frame",
        lambda **kwargs: pl.DataFrame(
            [
                {
                    "feature_0": (
                        10.0
                        if kwargs["formulation"].formulation_label == "baseline"
                        else 8.0
                    )
                }
            ]
        ),
    )
    monkeypatch.setattr(
        query_compare_prediction,
        "flatten_modeling_dataset",
        lambda feature_df: (feature_df, feature_df.columns),
    )
    original_root = query_compare_prediction.ROOT_DIR
    query_compare_prediction.ROOT_DIR = tmp_path
    (tmp_path / "query_compare" / "sql").mkdir(parents=True)
    (tmp_path / "query_compare" / "sql" / "q3_base.sql").write_text("select 1;\n")
    (
        tmp_path / "query_compare" / "sql" / "q3_formulation_1_explicit_inner_join.sql"
    ).write_text("select 2;\n")

    try:
        summary = query_compare_prediction.predict_query_compare_costs(
            benchmark_path=benchmark_path,
            database="tpch_sf_1",
            output_path=output_path,
            summary_output_path=summary_output_path,
            explain_dir=explain_dir,
            manifest_path=manifest_path,
            analyze=True,
        )
    finally:
        query_compare_prediction.ROOT_DIR = original_root

    predictions = pl.read_parquet(output_path).sort("formulation_id")
    assert predictions["formulation_id"].to_list() == ["baseline", "q3_alt_1"]
    assert predictions["planner_total_cost_rank"].to_list() == [2, 1]
    assert predictions["model_predicted_cost_rank"].to_list() == [2, 1]
    assert predictions["execution_time_ms_rank"].to_list() == [2, 1]
    assert predictions["planner_total_cost_delta_vs_baseline"].to_list() == [
        0.0,
        -2.0,
    ]
    assert predictions["model_predicted_cost_delta_vs_baseline"].to_list() == [
        0.0,
        -2.0,
    ]
    assert predictions["execution_time_ms_delta_vs_baseline"].to_list() == [
        0.0,
        -6.0,
    ]
    assert predictions["execution_time_ms"].to_list() == [15.0, 9.0]
    assert predictions["runtime_collection_enabled"].to_list() == [True, True]
    assert predictions["explain_artifact_path"].to_list() == [
        str(explain_dir / "q3__baseline.json"),
        str(explain_dir / "q3__q3_alt_1.json"),
    ]

    summary_document = json.loads(summary_output_path.read_text())
    assert summary_document["model_family"] == "random_forest"
    assert summary_document["runtime_collection_enabled"] is True
    assert summary_document["prediction_artifact_path"] == str(output_path)
    assert summary_document["explain_artifact_dir"] == str(explain_dir)
    assert summary["templates"][0]["best_predicted_formulation_id"] == "q3_alt_1"
    assert summary["templates"][0]["best_planner_formulation_id"] == "q3_alt_1"
    assert summary["templates"][0]["best_execution_time_formulation_id"] == "q3_alt_1"
    assert summary["templates"][0]["planner_vs_model_agree"] is True
    assert summary["templates"][0]["planner_vs_runtime_agree"] is True
    assert summary["templates"][0]["model_vs_runtime_agree"] is True
    assert summary["templates"][0]["all_signals_agree"] is True
    assert summary["templates"][0]["planner_vs_model_dense_rank_correlation"] == 1.0
    assert summary["templates"][0]["planner_vs_runtime_dense_rank_correlation"] == 1.0
    assert summary["templates"][0]["model_vs_runtime_dense_rank_correlation"] == 1.0


def test_predict_query_compare_costs_defaults_runtime_fields_to_null(
    monkeypatch, tmp_path: Path
) -> None:
    benchmark_path = tmp_path / "benchmark.json"
    benchmark_path.write_text(
        json.dumps(
            {
                "templates": [
                    {
                        "template_id": "q3",
                        "parameter_set_id": "q3-p0000",
                        "scale_factor": 1.0,
                        "baseline_sql": "select 1;\n",
                        "baseline_sql_path": "query_compare/sql/q3_base.sql",
                        "accepted_formulations": [
                            {
                                "formulation_id": "q3_alt_1",
                                "formulation_type": "explicit_inner_join",
                                "sql": "select 2;\n",
                                "sql_path": (
                                    "query_compare/sql/"
                                    "q3_formulation_1_explicit_inner_join.sql"
                                ),
                            }
                        ],
                    }
                ]
            }
        )
    )
    output_path = tmp_path / "predictions.parquet"
    summary_output_path = tmp_path / "predictions.json"
    explain_dir = tmp_path / "explains"
    manifest_path = tmp_path / "training_manifest.json"

    class FakeEstimator:
        def predict(self, matrix: Any) -> list[float]:
            values = matrix.tolist()
            return [values[0][0]]

    monkeypatch.setattr(
        query_compare_prediction,
        "load_selected_estimator",
        lambda **_: ("random_forest", ["feature_0"], FakeEstimator()),
    )
    monkeypatch.setattr(
        query_compare_prediction,
        "fetch_explain_plan",
        lambda **kwargs: {
            "Plan": {
                "Node Type": "Seq Scan",
                "Plan Rows": 10,
                "Plan Width": 5,
                "Startup Cost": 0.0,
                "Total Cost": 10.0 if "select 1" in kwargs["sql_text"] else 8.0,
            }
        },
    )
    monkeypatch.setattr(
        query_compare_prediction,
        "build_feature_frame",
        lambda **kwargs: pl.DataFrame(
            [
                {
                    "feature_0": (
                        10.0
                        if kwargs["formulation"].formulation_label == "baseline"
                        else 8.0
                    )
                }
            ]
        ),
    )
    monkeypatch.setattr(
        query_compare_prediction,
        "flatten_modeling_dataset",
        lambda feature_df: (feature_df, feature_df.columns),
    )
    original_root = query_compare_prediction.ROOT_DIR
    query_compare_prediction.ROOT_DIR = tmp_path
    (tmp_path / "query_compare" / "sql").mkdir(parents=True)
    (tmp_path / "query_compare" / "sql" / "q3_base.sql").write_text("select 1;\n")
    (
        tmp_path / "query_compare" / "sql" / "q3_formulation_1_explicit_inner_join.sql"
    ).write_text("select 2;\n")

    try:
        summary = query_compare_prediction.predict_query_compare_costs(
            benchmark_path=benchmark_path,
            database="tpch_sf_1",
            output_path=output_path,
            summary_output_path=summary_output_path,
            explain_dir=explain_dir,
            manifest_path=manifest_path,
        )
    finally:
        query_compare_prediction.ROOT_DIR = original_root

    predictions = pl.read_parquet(output_path).sort("formulation_id")
    assert predictions["execution_time_ms"].to_list() == [None, None]
    assert predictions["execution_time_ms_rank"].to_list() == [None, None]
    assert predictions["execution_time_ms_delta_vs_baseline"].to_list() == [
        None,
        None,
    ]
    assert predictions["runtime_collection_enabled"].to_list() == [False, False]

    summary_document = json.loads(summary_output_path.read_text())
    assert summary_document["runtime_collection_enabled"] is False
    assert summary["templates"][0]["best_execution_time_formulation_id"] is None
    assert summary["templates"][0]["planner_vs_runtime_dense_rank_correlation"] is None
    assert summary["templates"][0]["model_vs_runtime_dense_rank_correlation"] is None


def test_predict_query_compare_costs_summary_handles_runtime_disagreement(
    monkeypatch, tmp_path: Path
) -> None:
    benchmark_path = tmp_path / "benchmark.json"
    benchmark_path.write_text(
        json.dumps(
            {
                "templates": [
                    {
                        "template_id": "q3",
                        "parameter_set_id": "q3-p0000",
                        "scale_factor": 1.0,
                        "baseline_sql": "select 1;\n",
                        "baseline_sql_path": "query_compare/sql/q3_base.sql",
                        "accepted_formulations": [
                            {
                                "formulation_id": "q3_alt_1",
                                "formulation_type": "explicit_inner_join",
                                "sql": "select 2;\n",
                                "sql_path": (
                                    "query_compare/sql/"
                                    "q3_formulation_1_explicit_inner_join.sql"
                                ),
                            },
                            {
                                "formulation_id": "q3_alt_2",
                                "formulation_type": "single_table_filter_ctes",
                                "sql": "select 3;\n",
                                "sql_path": (
                                    "query_compare/sql/"
                                    "q3_formulation_2_single_table_filter_ctes.sql"
                                ),
                            },
                        ],
                    }
                ]
            }
        )
    )
    output_path = tmp_path / "predictions.parquet"
    summary_output_path = tmp_path / "predictions.json"
    explain_dir = tmp_path / "explains"
    manifest_path = tmp_path / "training_manifest.json"

    class FakeEstimator:
        def predict(self, matrix: Any) -> list[float]:
            values = matrix.tolist()
            return [values[0][0]]

    monkeypatch.setattr(
        query_compare_prediction,
        "load_selected_estimator",
        lambda **_: ("random_forest", ["feature_0"], FakeEstimator()),
    )

    def fake_fetch_explain_plan(**kwargs: Any) -> dict[str, Any]:
        sql_text = kwargs["sql_text"]
        return {
            "Plan": {
                "Node Type": "Seq Scan",
                "Plan Rows": 10,
                "Plan Width": 5,
                "Startup Cost": 0.0,
                "Total Cost": {
                    "select 1;\n": 10.0,
                    "select 2;\n": 8.0,
                    "select 3;\n": 9.0,
                }[sql_text],
            },
            "Execution Time": {
                "select 1;\n": 5.0,
                "select 2;\n": 7.0,
                "select 3;\n": 4.0,
            }[sql_text],
        }

    monkeypatch.setattr(
        query_compare_prediction,
        "fetch_explain_plan",
        fake_fetch_explain_plan,
    )
    monkeypatch.setattr(
        query_compare_prediction,
        "build_feature_frame",
        lambda **kwargs: pl.DataFrame(
            [
                {
                    "feature_0": {
                        "baseline": 9.0,
                        "q3_alt_1": 6.0,
                        "q3_alt_2": 7.0,
                    }[kwargs["formulation"].formulation_label]
                }
            ]
        ),
    )
    monkeypatch.setattr(
        query_compare_prediction,
        "flatten_modeling_dataset",
        lambda feature_df: (feature_df, feature_df.columns),
    )
    original_root = query_compare_prediction.ROOT_DIR
    query_compare_prediction.ROOT_DIR = tmp_path
    (tmp_path / "query_compare" / "sql").mkdir(parents=True)
    (tmp_path / "query_compare" / "sql" / "q3_base.sql").write_text("select 1;\n")
    (
        tmp_path / "query_compare" / "sql" / "q3_formulation_1_explicit_inner_join.sql"
    ).write_text("select 2;\n")
    (
        tmp_path
        / "query_compare"
        / "sql"
        / "q3_formulation_2_single_table_filter_ctes.sql"
    ).write_text("select 3;\n")

    try:
        summary = query_compare_prediction.predict_query_compare_costs(
            benchmark_path=benchmark_path,
            database="tpch_sf_1",
            output_path=output_path,
            summary_output_path=summary_output_path,
            explain_dir=explain_dir,
            manifest_path=manifest_path,
            analyze=True,
        )
    finally:
        query_compare_prediction.ROOT_DIR = original_root

    predictions = pl.read_parquet(output_path).sort("formulation_id")
    assert predictions["execution_time_ms_rank"].to_list() == [2, 3, 1]
    assert predictions["execution_time_ms_delta_vs_baseline"].to_list() == [
        0.0,
        2.0,
        -1.0,
    ]

    template_summary = summary["templates"][0]
    assert template_summary["best_planner_formulation_id"] == "q3_alt_1"
    assert template_summary["best_predicted_formulation_id"] == "q3_alt_1"
    assert template_summary["best_execution_time_formulation_id"] == "q3_alt_2"
    assert template_summary["planner_vs_model_agree"] is True
    assert template_summary["planner_vs_runtime_agree"] is False
    assert template_summary["model_vs_runtime_agree"] is False
    assert template_summary["all_signals_agree"] is False
    assert template_summary["planner_vs_model_dense_rank_correlation"] == 1.0
    assert template_summary["planner_vs_runtime_dense_rank_correlation"] == -0.5
    assert template_summary["model_vs_runtime_dense_rank_correlation"] == -0.5


def test_predict_query_compare_costs_summary_treats_tied_winners_as_ambiguous(
    monkeypatch, tmp_path: Path
) -> None:
    benchmark_path = tmp_path / "benchmark.json"
    benchmark_path.write_text(
        json.dumps(
            {
                "templates": [
                    {
                        "template_id": "q3",
                        "parameter_set_id": "q3-p0000",
                        "scale_factor": 1.0,
                        "baseline_sql": "select 1;\n",
                        "baseline_sql_path": "query_compare/sql/q3_base.sql",
                        "accepted_formulations": [
                            {
                                "formulation_id": "q3_alt_1",
                                "formulation_type": "explicit_inner_join",
                                "sql": "select 2;\n",
                                "sql_path": (
                                    "query_compare/sql/"
                                    "q3_formulation_1_explicit_inner_join.sql"
                                ),
                            }
                        ],
                    }
                ]
            }
        )
    )
    output_path = tmp_path / "predictions.parquet"
    summary_output_path = tmp_path / "predictions.json"
    explain_dir = tmp_path / "explains"
    manifest_path = tmp_path / "training_manifest.json"

    class FakeEstimator:
        def predict(self, matrix: Any) -> list[float]:
            return [10.0]

    monkeypatch.setattr(
        query_compare_prediction,
        "load_selected_estimator",
        lambda **_: ("random_forest", ["feature_0"], FakeEstimator()),
    )
    monkeypatch.setattr(
        query_compare_prediction,
        "fetch_explain_plan",
        lambda **kwargs: {
            "Plan": {
                "Node Type": "Seq Scan",
                "Plan Rows": 10,
                "Plan Width": 5,
                "Startup Cost": 0.0,
                "Total Cost": 10.0,
            },
            "Execution Time": 5.0,
        },
    )
    monkeypatch.setattr(
        query_compare_prediction,
        "build_feature_frame",
        lambda **kwargs: pl.DataFrame([{"feature_0": 10.0}]),
    )
    monkeypatch.setattr(
        query_compare_prediction,
        "flatten_modeling_dataset",
        lambda feature_df: (feature_df, feature_df.columns),
    )
    original_root = query_compare_prediction.ROOT_DIR
    query_compare_prediction.ROOT_DIR = tmp_path
    (tmp_path / "query_compare" / "sql").mkdir(parents=True)
    (tmp_path / "query_compare" / "sql" / "q3_base.sql").write_text("select 1;\n")
    (
        tmp_path / "query_compare" / "sql" / "q3_formulation_1_explicit_inner_join.sql"
    ).write_text("select 2;\n")

    try:
        summary = query_compare_prediction.predict_query_compare_costs(
            benchmark_path=benchmark_path,
            database="tpch_sf_1",
            output_path=output_path,
            summary_output_path=summary_output_path,
            explain_dir=explain_dir,
            manifest_path=manifest_path,
            analyze=True,
        )
    finally:
        query_compare_prediction.ROOT_DIR = original_root

    template_summary = summary["templates"][0]
    assert template_summary["best_predicted_formulation_ids"] == [
        "baseline",
        "q3_alt_1",
    ]
    assert template_summary["best_predicted_formulation_id"] is None
    assert template_summary["best_planner_formulation_ids"] == [
        "baseline",
        "q3_alt_1",
    ]
    assert template_summary["best_planner_formulation_id"] is None
    assert template_summary["planner_vs_model_agree"] is None
    assert template_summary["all_signals_agree"] is None
    assert template_summary["planner_vs_model_dense_rank_correlation"] is None


def test_predict_query_compare_costs_removes_stale_explain_artifacts(
    monkeypatch, tmp_path: Path
) -> None:
    benchmark_path = tmp_path / "benchmark.json"
    benchmark_path.write_text(
        json.dumps(
            {
                "templates": [
                    {
                        "template_id": "q3",
                        "parameter_set_id": "q3-p0000",
                        "scale_factor": 1.0,
                        "baseline_sql": "select 1;\n",
                        "baseline_sql_path": "query_compare/sql/q3_base.sql",
                        "accepted_formulations": [],
                    }
                ]
            }
        )
    )
    output_path = tmp_path / "predictions.parquet"
    summary_output_path = tmp_path / "predictions.json"
    explain_dir = tmp_path / "explains"
    explain_dir.mkdir()
    stale_explain = explain_dir / "stale.json"
    stale_explain.write_text("{}\n")
    manifest_path = tmp_path / "training_manifest.json"

    class FakeEstimator:
        def predict(self, matrix: Any) -> list[float]:
            return [10.0]

    monkeypatch.setattr(
        query_compare_prediction,
        "load_selected_estimator",
        lambda **_: ("random_forest", ["feature_0"], FakeEstimator()),
    )
    monkeypatch.setattr(
        query_compare_prediction,
        "fetch_explain_plan",
        lambda **kwargs: {
            "Plan": {
                "Node Type": "Seq Scan",
                "Plan Rows": 10,
                "Plan Width": 5,
                "Startup Cost": 0.0,
                "Total Cost": 10.0,
            }
        },
    )
    monkeypatch.setattr(
        query_compare_prediction,
        "build_feature_frame",
        lambda **kwargs: pl.DataFrame([{"feature_0": 10.0}]),
    )
    monkeypatch.setattr(
        query_compare_prediction,
        "flatten_modeling_dataset",
        lambda feature_df: (feature_df, feature_df.columns),
    )
    original_root = query_compare_prediction.ROOT_DIR
    query_compare_prediction.ROOT_DIR = tmp_path
    (tmp_path / "query_compare" / "sql").mkdir(parents=True)
    (tmp_path / "query_compare" / "sql" / "q3_base.sql").write_text("select 1;\n")

    try:
        query_compare_prediction.predict_query_compare_costs(
            benchmark_path=benchmark_path,
            database="tpch_sf_1",
            output_path=output_path,
            summary_output_path=summary_output_path,
            explain_dir=explain_dir,
            manifest_path=manifest_path,
        )
    finally:
        query_compare_prediction.ROOT_DIR = original_root

    assert stale_explain.exists() is False
    assert (explain_dir / "q3__baseline.json").exists() is True
