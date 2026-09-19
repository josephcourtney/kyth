from pathlib import Path

import pytest

from kyth.changes import ChangeEffect, ChangePolicy, classify_batch
from kyth.model import FileBatch, FileEvent, FileOperation


@pytest.mark.unit
@pytest.mark.small
def test_classification_separates_restart_browser_and_other_paths() -> None:
    batch = FileBatch.from_events([
        FileEvent(Path("/project/src/app.py"), FileOperation.MODIFIED),
        FileEvent(Path("/project/.env.development"), FileOperation.MODIFIED),
        FileEvent(Path("/project/templates/index.html"), FileOperation.MODIFIED),
        FileEvent(Path("/project/README.md"), FileOperation.MODIFIED),
    ])

    changes = classify_batch(batch)

    effects = {item.path.name: item.effect for item in changes.paths}
    assert effects == {
        "app.py": ChangeEffect.SERVER_RESTART,
        ".env.development": ChangeEffect.SERVER_RESTART,
        "index.html": ChangeEffect.BROWSER_CHANGE,
        "README.md": ChangeEffect.OTHER,
    }
    assert changes.requires_restart


@pytest.mark.unit
@pytest.mark.small
def test_configured_restart_pattern_classifies_runtime_configuration() -> None:
    batch = FileBatch.from_events([
        FileEvent(Path("/project/config/settings.yaml"), FileOperation.MODIFIED),
        FileEvent(Path("/project/content/article.yaml"), FileOperation.MODIFIED),
    ])

    changes = classify_batch(batch, policy=ChangePolicy(restart_patterns=("config/*.yaml",)))

    effects = {item.path.name: item.effect for item in changes.paths}
    assert effects == {
        "settings.yaml": ChangeEffect.SERVER_RESTART,
        "article.yaml": ChangeEffect.OTHER,
    }


@pytest.mark.unit
@pytest.mark.small
def test_restart_policy_rejects_empty_pattern() -> None:
    with pytest.raises(ValueError, match="restart patterns must be non-empty"):
        ChangePolicy(restart_patterns=("",))
