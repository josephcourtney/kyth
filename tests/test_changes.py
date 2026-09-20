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


@pytest.mark.unit
@pytest.mark.small
def test_external_hmr_pattern_suppresses_kyth_browser_classification() -> None:
    batch = FileBatch.from_events([
        FileEvent(Path("/project/frontend/app.js"), FileOperation.MODIFIED),
        FileEvent(Path("/project/static/site.css"), FileOperation.MODIFIED),
    ])
    policy = ChangePolicy(external_hmr_patterns=("frontend/*.js",))

    result = classify_batch(batch, policy=policy)

    effects = {item.path.name: item.effect for item in result.paths}
    assert effects == {
        "app.js": ChangeEffect.EXTERNAL_HMR,
        "site.css": ChangeEffect.BROWSER_CHANGE,
    }
    assert result.external_hmr_paths == (Path("/project/frontend/app.js"),)


@pytest.mark.unit
@pytest.mark.small
def test_fallback_scoped_source_is_browser_change_even_without_browser_suffix() -> None:
    source = Path("/project/content/article.md")
    batch = FileBatch.from_events([FileEvent(source, FileOperation.MODIFIED)])

    changes = classify_batch(batch, fallback_scope_paths={source})

    assert changes.browser_paths == (source,)
    assert changes.other_paths == ()


@pytest.mark.unit
@pytest.mark.small
def test_restart_and_external_hmr_precede_fallback_scope_classification() -> None:
    python = Path("/project/src/app.py")
    frontend = Path("/project/frontend/app.js")
    batch = FileBatch.from_events([
        FileEvent(python, FileOperation.MODIFIED),
        FileEvent(frontend, FileOperation.MODIFIED),
    ])
    policy = ChangePolicy(external_hmr_patterns=("frontend/*.js",))

    changes = classify_batch(
        batch,
        policy=policy,
        fallback_scope_paths={python, frontend},
    )

    effects = {item.path: item.effect for item in changes.paths}
    assert effects[python] is ChangeEffect.SERVER_RESTART
    assert effects[frontend] is ChangeEffect.EXTERNAL_HMR
