# conftest.py -- juris-calculus test collection configuration

# Orphaned test files: reference modules that were removed or renamed
# during the src -> 源码 refactoring (2026-06).
# These files are preserved for audit trail; they can be re-enabled if
# the target functionality is restored under a compatible import path.
collect_ignore = [
    # src.evaluator module removed (StratifiedEvaluator, CompletionStatus gone)
    "test_composition_safety.py",
    "unit/test_p0_auditability.py",
    "unit/test_stratified_evaluator.py",
    # compiler_core.argumentation.ArgumentationFramework does not exist
    "test_argumentation_b6.py",
]
