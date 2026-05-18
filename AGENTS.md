# AGENTS.md

## Purpose

This file defines how coding agents must operate when contributing to this project.

## Role

Coding agent responsibilities include:

- Editing Python source files under `src/`
- Creating or editing test files under `tests/`
- Preserving output determinism, testability, and extensibility
- Respecting existing CLI conventions and internal architecture

## Directory Constraints

- Source code: `src/`
- Tests: `tests/`
- Agent workspace (if present): `.claude/` (skills, commands, sources)
- Do not write or create files outside these directories unless explicitly instructed.

## Tooling

Always invoke code-quality tooling via the `just` recipes defined in `justfile` rather than calling underlying executables directly, unless explicitly instructed otherwise.

Run `just help` or `just --list` to see what recipes are available.

## Behavior Constraints

- Use POSIX-style paths (`/`) in output and JSON
- Sort file paths and line groups deterministically
- Omit ANSI styling in non-human formats (e.g., JSON)
- No I/O outside `src/`, `tests/`, or `TODO.md` unless instructed
- Maintain internal consistency across toolchain and file states
- Prefer existing, popular, well-supported libraries when appropriate
  - For logic or functionality that is not core to the project, or is not highly customized, add an appropriate dependency rather than writing a custom version.

## Logging and Progress Tracking

### To-Do List Maintenance

- As the coding agent completes items from `TODO.md`, it should mark them as complete
- Do not delete or rewrite historical entries
- If `TODO.md` is missing, create a new file and notify the user

### Changelog Maintenance

Follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format:

- Example heading: `## [1.2.3] - 2025-08-02`
- Allowed sections: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`
- Each bullet must:
  - Begin with a lowercase imperative verb (e.g., "add", "fix")
  - Follow Markdown syntax

Ensure:

- Changelog matches the actual code changes
- Version in `pyproject.toml` is updated
- Historical entries are never modified
- If `CHANGELOG.md` is missing, create a stub file and note this

Example:

```markdown
## [1.4.0] - 2025-08-02

### Added
- add `--format json` CLI option for machine-readable output

### Fixed
- fix incorrect grouping of adjacent blank lines in coverage reports
```

## Commit Standards

Each commit must pass linting, typechecking, formatting and testing.

Follow [Conventional Commits](https://www.conventionalcommits.org):

- `feat: add --format json`
- `fix: handle missing <class> tag`
- `test: add tests for merge_blank_gap_groups`

Before submitting a pull request:

- Bump the version with `uv version bump`
- Update `CHANGELOG.md` accordingly

## Prohibited Behavior

- Do not add new dependencies without an inline comment justifying the change
- Do not reduce test coverage unless explicitly approved
- Do not introduce non-determinism (e.g., random output, time-dependent data)
- Do not write outside `src/`, `tests/`, `CHANGELOG.md`, or `TODO.md` unless instructed

## Assumptions and Capabilities

Necessary assumptions:

- Each task starts with only the current file state
- `TODO.md` and `CHANGELOG.md` must be re-read before taking action on historical items

If lacking access to shell or file I/O:

- Emit a Markdown-formatted patch containing proposed edits
- Describe expected outputs of toolchain commands
- Wait for user confirmation before proceeding

## Compliance

All actions must follow this protocol unless:

- Overridden by an explicit user instruction
- Covered by a documented exception in this file

