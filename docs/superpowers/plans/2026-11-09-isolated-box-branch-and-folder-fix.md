# Isolated Agent Box, Branch Per Change, and Folder Linking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the project folder addition bug so linked folders appear in the projects section and allow new chats, implement an isolated box mode for agent edits with conflict-free merge, and implement a branch-per-change git workflow with default branch auto-detection, test verification, and user approval merge.

**Architecture:**
- Extend PC Bridge folder linking and listing in `agent/bridge/pc_bridge.py`: auto-scaffold `PROJECT.md` and `.devpilot/` upon linking; recognize symlinked and configured project folders in `h_project_list`.
- Add runtime settings in `agent/jarvis/runtime_settings.py` for `isolated_agent_box` and `branch_per_change`.
- Implement isolated edit sandbox and conflict-free merge logic in `agent/bridge/pc_bridge.py` and `agent/jarvis/engine.py`.
- Implement branch-per-change with automatic main/master branch detection, test validation gate, and user approval merge endpoints in `agent/jarvis/project_logic.py`, `agent/jarvis/codetools.py`, and `agent/jarvis/server.py`.
- Expose settings and UI controls in `agent/jarvis/index.html` and `agent/jarvis/ui/projects.js`.

**Tech Stack:** Python 3 standard library (`subprocess`, `pathlib`, `json`, `shlex`, `re`), Vanilla JS/CSS (K.R.Y.Z.E.N frontend), Git.

## Global Constraints
- Zero third-party pip dependencies; standard library Python only.
- Bubblewrap and path sandboxing must be respected.
- All 113 existing tests must continue to pass without regressions.
- Follow Andrej Karpathy LLM coding guidelines (simplicity first, surgical changes, goal-driven verification).

## Review Focus
1. Adding a folder from anywhere in `~` without a `PROJECT.md` must register immediately in `/api/projects` and appear in the `#projectList` UI.
2. Clicking "New chat" on the newly added project folder must create a chat targeting that specific project.
3. Enabling `isolated_agent_box` must isolate agent file edits and merge cleanly when verified.
4. Enabling `branch_per_change` must create a dedicated branch, detect `main` vs `master` dynamically, run tests, and only merge after user approval.

---

### Task 1: Fix Folder Linking and Listing Bug

**Files:**
- Modify: `agent/bridge/pc_bridge.py`
- Modify: `agent/jarvis/ui/projects.js`
- Test: `agent/jarvis/tests/test_reliability.py` (and new test in `agent/jarvis/tests/test_project_link.py`)

- [ ] Write failing test in `agent/jarvis/tests/test_project_link.py` verifying that linking an external folder without `PROJECT.md` creates `PROJECT.md` and causes `h_project_list` to include it.
- [ ] Run `python3 -m unittest agent/jarvis/tests/test_project_link.py` and verify test failure.
- [ ] Update `h_project_link` in `agent/bridge/pc_bridge.py`:
  - When linking a target directory, if `(target / "PROJECT.md").exists()` is False, create an initial `PROJECT.md` and `.devpilot/` directory.
- [ ] Update `h_project_list` in `agent/bridge/pc_bridge.py`:
  - Include any directory or symlink in `WORKSPACE` that has `PROJECT.md` or is a valid symlink to a directory or is in `.linked-projects.json`.
- [ ] Update `agent/jarvis/ui/projects.js` to ensure that after `api("/api/project/link")`, `loadProjects()` correctly refreshes and selects the new project and renders the project in `#projectList`.
- [ ] Run `python3 -m unittest agent/jarvis/tests/test_project_link.py` and verify test passes.
- [ ] Run `python3 -m unittest discover -s agent/jarvis/tests` to ensure all tests pass.

---

### Task 2: Add Runtime Settings for Isolated Box & Branch Per Change

**Files:**
- Modify: `agent/jarvis/runtime_settings.py`
- Test: `agent/jarvis/tests/test_runtime_settings.py` (or extend existing settings tests in `agent/jarvis/tests/test_reliability.py`)

- [ ] Write failing test for `isolated_agent_box` and `branch_per_change` default values and validation in settings.
- [ ] Add `isolated_agent_box: False` and `branch_per_change: False` to `DEFAULTS` in `agent/jarvis/runtime_settings.py`.
- [ ] Run settings tests and verify pass.

---

### Task 3: Implement Isolated Box Agent Edits and Conflict-Free Merge

**Files:**
- Modify: `agent/bridge/pc_bridge.py`
- Modify: `agent/jarvis/engine.py`
- Modify: `agent/jarvis/codetools.py`
- Test: `agent/jarvis/tests/test_isolated_box.py`

- [ ] Write failing test in `agent/jarvis/tests/test_isolated_box.py` for creating an isolated box, recording edits in the box, and merging cleanly back to project root.
- [ ] Implement `create_isolated_box(slug, task_id)` and `merge_isolated_box(slug, task_id)` in `agent/bridge/pc_bridge.py` / `agent/jarvis/codetools.py`:
  - When `isolated_agent_box` is active, file writes are directed to `.devpilot/isolated/<task_id>/`.
  - Conflict checking: compares base revisions against target project files.
  - Conflict-free merge: applies changed files atomically, or aborts if conflicting modifications occurred.
- [ ] Add endpoint `/api/isolated/merge` in `agent/jarvis/server.py` and support in `engine.py`.
- [ ] Run test and verify pass.

---

### Task 4: Implement Branch-Per-Change, Main/Master Detection, and Approval Merge

**Files:**
- Modify: `agent/jarvis/codetools.py`
- Modify: `agent/jarvis/server.py`
- Test: `agent/jarvis/tests/test_branch_workflow.py`

- [ ] Write failing test in `agent/jarvis/tests/test_branch_workflow.py`:
  - Detect default branch (`main` vs `master`).
  - Create feature branch `agent/<task>`.
  - Commit change.
  - Verify tests.
  - Merge into default branch on user approval.
- [ ] Implement `detect_default_branch(slug)` in `agent/jarvis/codetools.py`.
- [ ] Implement `create_change_branch(slug, task_name)` and `merge_change_branch(slug, branch_name, approve=True)` in `agent/jarvis/codetools.py`.
- [ ] Add `/api/git/branch/create`, `/api/git/branch/status`, and `/api/git/branch/merge` in `agent/jarvis/server.py`.
- [ ] Run test and verify pass.

---

### Task 5: UI Integration in Jarvis

**Files:**
- Modify: `agent/jarvis/index.html`
- Modify: `agent/jarvis/ui/projects.js`

- [ ] Add UI switches in Settings (`secModels` or settings panel):
  - "Isolated Agent Box: edit in isolated sandbox before merging"
  - "Branch per change: commit to own branch & merge upon user approval"
- [ ] In project view / run control: show branch status and approval button when a branch change is pending merge approval.
- [ ] Test UI rendering and API interactions.

---

### Task 6: GitHub Issue Documentation & Final Verification

**Files:**
- Create: `docs/issues/ISSUE-001-folder-linking-and-isolated-box.md`
- Verify: Full test suite passing with `python3 -m unittest discover -s agent/jarvis/tests`
- Verify: Git commit with comprehensive message referencing the issue.
