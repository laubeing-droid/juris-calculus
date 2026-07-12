from compiler_core.completion_status import CompletionStatus, StageResult
from compiler_core.version import __version__


def test_stage_result_uses_shared_runtime_version_by_default() -> None:
    result = StageResult(CompletionStatus.COMPLETE, None, None)

    assert result.producer_version == f"v{__version__}"
