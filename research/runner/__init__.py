"""Benchmark runner and trace labeling helpers."""

from .benchmark_runner import BenchmarkRunConfig, BenchmarkRunner
from .claims import attach_memory_claims, extract_memory_claims, find_stale_claims
from .comparison import compare_runs
from .decision_beliefs import (
    extract_decision_beliefs,
    summarize_decision_beliefs,
)
from .artifacts import generate_artifact_bundle, generate_artifact_summary
from .labeling import label_high_risk_claims
from .metrics import (
    build_memory_health_report,
    compute_attribution_accuracy,
    compute_false_completion_rate,
    compute_semantic_drift_score,
    compute_structured_memory_metrics,
    compute_task_state_accuracy,
    compute_temporal_accuracy,
)
from .matrix_analysis import (
    analyze_model_matrix_manifest,
    format_model_matrix_analysis_markdown,
    write_model_matrix_analysis,
)
from .measurement_validation import (
    load_manual_measurement_labels,
    validate_manual_measurements,
)
from .model_adapters import (
    DeterministicModelAdapter,
    LlamaCppHttpAdapter,
    ModelRequest,
    ModelResponse,
    OllamaModelAdapter,
    create_model_adapter,
)
from .model_matrix import load_model_matrix, run_model_matrix
from .experiment_protocol import (
    audit_model_matrix_manifest,
    build_artifact_index,
    build_experiment_protocol,
    sha256_file,
)
from .statistics import (
    build_paired_statistics,
    exact_mcnemar,
    paired_bootstrap_mean_difference,
    wilson_interval,
)
from .verification import (
    VerificationPolicy,
    build_verification_report,
    retrieval_consistency_score,
    verify_claim,
    verify_run,
)

__all__ = [
    "BenchmarkRunConfig",
    "BenchmarkRunner",
    "VerificationPolicy",
    "DeterministicModelAdapter",
    "LlamaCppHttpAdapter",
    "ModelRequest",
    "ModelResponse",
    "OllamaModelAdapter",
    "attach_memory_claims",
    "build_verification_report",
    "create_model_adapter",
    "extract_memory_claims",
    "find_stale_claims",
    "generate_artifact_bundle",
    "generate_artifact_summary",
    "label_high_risk_claims",
    "analyze_model_matrix_manifest",
    "format_model_matrix_analysis_markdown",
    "write_model_matrix_analysis",
    "load_model_matrix",
    "load_manual_measurement_labels",
    "validate_manual_measurements",
    "compare_runs",
    "extract_decision_beliefs",
    "summarize_decision_beliefs",
    "build_memory_health_report",
    "compute_attribution_accuracy",
    "compute_false_completion_rate",
    "compute_semantic_drift_score",
    "compute_structured_memory_metrics",
    "compute_task_state_accuracy",
    "compute_temporal_accuracy",
    "retrieval_consistency_score",
    "verify_claim",
    "verify_run",
    "run_model_matrix",
    "build_artifact_index",
    "audit_model_matrix_manifest",
    "build_experiment_protocol",
    "sha256_file",
    "build_paired_statistics",
    "exact_mcnemar",
    "paired_bootstrap_mean_difference",
    "wilson_interval",
]
