from pathlib import Path

import pytest

from kyth.changes import ChangeEffect, classify_batch
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
