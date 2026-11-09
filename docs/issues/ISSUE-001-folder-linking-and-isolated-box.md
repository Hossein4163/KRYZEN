# Issue #001: Folder Linking Visibility in Projects Section & Isolated Agent Box / Branch-Per-Change Workflows

**Status:** Resolved (Fixed & Verified)  
**Date:** 2026-11-09  
**Component:** PC Bridge (`agent/bridge/pc_bridge.py`), Jarvis Engine (`agent/jarvis/engine.py`), Codetools (`agent/jarvis/codetools.py`), Mission Control UI (`agent/jarvis/index.html`, `ui/projects.js`)  

---

## 1. Problem Description
When adding a folder through the "+ Add a project folder" picker:
1. The UI reported `Project <slug> added`.
2. However, the newly added folder did not appear in the projects folder section (`#projectList`) above the chats.
3. Users could not select the project or start a new chat inside it.

Furthermore, user requested:
- An update allowing every agent to perform edits in an isolated box, merging into the main project only after completion without conflicts or bugs (toggleable in settings).
- An option to commit every change to its own branch, automatically detecting the repository's default primary branch (`main` vs `master`), and merging into the default branch only after test verification and user approval.

---

## 2. Root Cause Analysis
1. **Missing `PROJECT.md` in Linked Directories**:
   `h_project_link` previously created a symlink or unhid existing folders in the workspace, but never initialized `PROJECT.md` or `.devpilot/` state.
2. **Strict Listing Filter**:
   `h_project_list` strictly evaluated `(p / "PROJECT.md").exists()`. Because external or plain folders did not contain `PROJECT.md`, they were excluded from `/api/projects`.
3. **Dropdown and Sidebar Rebuild**:
   `loadProjects()` in `index.html` only populated `<select id="proj">` from `/api/projects`. When the linked folder was missing, `switchProject()` failed, leaving the selection empty and omitting the folder row from `#projectList`.
4. **Lack of Isolated Box & Branch Controls**:
   Agent edits previously wrote directly to target files without staging isolation or conflict-free rollback mechanisms, and did not support dynamic branch creation and approval gates.

---

## 3. Resolution Details
1. **Folder Linking & Listing Fix**:
   - Updated `h_project_link` in `agent/bridge/pc_bridge.py` to automatically scaffold `PROJECT.md` and `.devpilot/` when linking any folder lacking a specification.
   - Updated `h_project_list` to recognize directories with `PROJECT.md`, valid symlinks, and linked projects.
   - Updated `agent/jarvis/ui/projects.js` to immediately register the new slug in local storage and synchronize rows.
2. **Isolated Agent Box Staging**:
   - Added `isolated_agent_box` setting in `agent/jarvis/runtime_settings.py`.
   - Built `create_isolated_box`, `write_isolated_box`, `read_isolated_box`, `list_isolated_box`, and `merge_isolated_box` in `agent/jarvis/codetools.py`.
   - Merging checks baseline hashes against concurrent modifications and aborts if conflicts exist, protecting primary project files.
   - Integrated into `agent/jarvis/engine.py` during agent write operations and turn completion.
3. **Branch Per Change with Dynamic Default Branch Detection & Approval Gate**:
   - Added `branch_per_change` setting in `agent/jarvis/runtime_settings.py`.
   - Implemented `detect_default_branch(slug)` in `agent/jarvis/codetools.py` to dynamically inspect `origin/HEAD`, `main`, and `master`.
   - Built `create_change_branch`, `commit_change_branch`, `get_branch_change_status`, and `merge_change_branch`.
   - Added REST endpoints in `agent/jarvis/server.py`:
     - `GET /api/git/branch/status`
     - `POST /api/git/branch/create`
     - `POST /api/git/branch/commit`
     - `POST /api/git/branch/merge`
     - `GET /api/isolated/list`
     - `POST /api/isolated/create`
     - `POST /api/isolated/merge`
     - `POST /api/isolated/discard`
4. **Mission Control UI Integration**:
   - Added toggles in `index.html` settings under "Autonomous Agent Sandboxing & Git Strategy".
   - Added "BRANCH READY FOR MERGE" banner with 1-click "Approve & Merge" button directly in the project view.

---

## 4. Verification & Testing
- Unit tests created:
  - `agent/jarvis/tests/test_project_link.py` (2 tests, passes)
  - `agent/jarvis/tests/test_runtime_settings.py` (3 tests, passes)
  - `agent/jarvis/tests/test_isolated_box.py` (2 tests, passes)
  - `agent/jarvis/tests/test_branch_workflow.py` (2 tests, passes)
  - `agent/jarvis/tests/test_endpoints.py` (2 tests, passes)
- Full regression suite execution:
  - **124/124 tests passing**. Zero regressions.
