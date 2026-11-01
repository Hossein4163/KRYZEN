# Builder source policy

Checked 2026-10-24. Installed as the `preferred-ui-sources` skill, assigned to Orchestrator, Reference, Planner, Build and QA. Build now has Browser, Web Search and Fetch Page tools. Both Jarvis and the compiled n8n agent workflow include these assignments.

For every project, inspect these sources and record the chosen component URLs, access/license, package versions and compatibility in that project's `docs/references/UI-SOURCES.md`. Use compatible components; document a concrete reason when a source cannot apply. Preserve the application's existing framework.

| Source | Official reference | Intended use |
| --- | --- | --- |
| Uilora | https://www.uilora.com/ · https://www.uilora.com/help | Interface components; inspect free/paid access before selecting source. |
| ForgeUI | https://forgeui.in/docs/introduction | React/Tailwind components and blocks; verify each component's registry instructions. |
| Uiverse | https://uiverse.io/ | Adapt individual elements to the project's design tokens; inspect source, license and accessibility. |
| Sileo | https://sileo.aaryan.design/ · https://github.com/hiaaryan/sileo | React notifications; verify installation and styles in current docs. |
| Blobatar | https://blobatar.dev/docs · https://github.com/Alain00/blobatar | Deterministic user-avatar fallback, preferably generated locally with opaque stable IDs. |

Jarvis itself uses a Python server and vanilla JavaScript. Its new controls extend its existing design system. Uilora and ForgeUI components were researched as builder defaults; their components were not copied into this change. Uiverse was researched as an element source. Sileo is a React library and is not installed into Jarvis's vanilla client. New React projects should use it following its current documentation.

Jarvis's user avatar **is implemented**: `assets/user-avatar.svg` was generated locally using the published `blobatar` **2.7.0** package with seed `jarvis-local-user`. It is served from the local server, makes no external requests and has a graceful image-error fallback. The package's MIT license is retained in `assets/BLOBATAR-LICENSE`. Builder instructions prefer the appropriate framework adapter or local generator for future projects and preserve uploaded profile pictures.

The public avatar endpoint returned HTTP 403 from this machine during implementation; local package generation succeeded. No paid component access or authenticated libraries were used.
