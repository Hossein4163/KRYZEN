# Charcoal studio reference

The user's dashboard screenshot is the visual direction for K.R.Y.Z.E.N. The app keeps its real Mesh, Flow, Plan, Code, and Control workspaces and live agent activity.

The design uses a near-neutral charcoal page (`#1c1c1f`), softly glossy surfaces, a thin luminous upper border, 22–24px main corner radii, and restrained sky blue (`#8bbcff`) for selected views and primary actions. Separate brand and navigation pills, a compact studio heading, and actual agent/tool/skill counts establish the same information hierarchy as the reference. The configuration's individual agent colors retain their meaning inside the mesh.

The new `reference-theme.css` is an additive visual layer loaded after `studio.css` and before `panel-resize.css`. It styles existing selectors and the overview markup. It does not set main workspace grid columns, alter hidden workspace semantics, replace live content with sample data, or change the mesh graph's geometry. Native WebKit avoids backdrop filters and uses small static inset shadows.

Desktop uses the header, overview, and flexible workspace as three grid rows. Tablet wraps the navigation while keeping the existing working layout. Phone shows a compact heading and metric row, keeps the active workspace first, and preserves page scrolling. Narrow screens retain touch-sized workspace controls; keyboard focus is sky blue and reduced-motion preference removes animated decoration. Code, terminals, inspector, empty/loading/error states, and dialogs use the same palette.

Integration: load the stylesheet, add the `workspace-overview` section, and populate `overviewAgents`, `overviewTools`, and `overviewSkills` from live configuration. Panel width and height behavior remains owned by the separate resize implementation.
