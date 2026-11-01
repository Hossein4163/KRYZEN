# Mesh and Flow controls

The mesh uses a graphite canvas, muted lilac navigation, teal activity and the existing system/mono typography. Following the user's latest feedback, agents use circular cores, colored halos and attached orbital tool dots. Real team/tool/skill counts orient the user. The orchestrator occupies the center of an orbital composition; phones use a readable explorable orbit with background panning.

## Mesh interaction

- Drag an agent to rearrange it. Its connections and attached capabilities follow. Click, Enter or Space opens configuration; dragging does not open the editor.
- Focus a circular agent node and use arrows to move it by 10 canvas units, or Shift+arrow for 30 units.
- Drag the background to pan. Scroll pans; Ctrl/Command+scroll zooms. Zoom controls and Fit are in a separate navigation band beneath the drawing.
- Circular positions are saved in this browser under `jarvis.mesh.orbit.v3`, keyed by agent name with separate mobile and desktop arrangements. Previous rectangular layouts remain stored separately and are not applied to the new orbit. Reset layout restores only the current arrangement. This does not write an Obsidian canvas or change delegation.
- Tools, Skills and Handoffs toggles expose their state through `aria-pressed`. Handoffs show the standard lifecycle; the active Flow canvas remains the source of specialist routing.
- Motion controls ambient circular-node/halo movement and animated connections. Appearance settings, reduced-motion preference and document visibility take precedence. Ambient motion is labeled separately from actual working states. The implementation uses CSS/SVG animation rather than a continuous JavaScript layout loop.

## Flow controls

Composition, routing, selection and navigation have separate control groups. Center selected centers a card or connection without moving its saved geometry; Deselect clears the inspector. Active/inactive routing and generated/read-only status remain visible on phones. Native Canvas files, content revisions, saving and existing keyboard editing are preserved.

Mobile/coarse-pointer controls use 44px touch targets. Important text compensates for drawing zoom; optional skill summaries hide at small scales to reduce clutter. Reduced-motion settings disable ambient animation without removing functional controls or actual activity state.
