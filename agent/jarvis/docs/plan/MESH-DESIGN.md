# Mesh and flow design iteration

Improve the live mesh and flow workspace while preserving project, chat, agent configuration, saved canvas geometry and routing behavior. Latest user direction: restore the attractive circular/orbital mesh shapes while retaining the improved controls and movement.

## Acceptance criteria

- Mesh agents use circular cores, halos and an orbital composition; actual counts, readable names and idle/live states remain clear. Flow Studio retains its native editable cards.
- Mesh nodes can move through pointer/touch input and an equivalent keyboard action. Connections follow the nodes. Moving a node does not open its configuration dialog.
- Saved local mesh positions survive reload; Reset restores the default layout without changing the active Obsidian canvas.
- Ambient motion has an explicit control and respects reduced-motion and appearance settings. Motion communicates visual orientation; activity highlights reflect real agent events.
- Mesh layer, layout, configuration and sync controls are grouped and expose their toggle state.
- Flow editing, canvas navigation, routing and save controls have distinct hierarchy and clear saved/read-only/active states. Existing native Canvas files remain compatible.
- Desktop, tablet and phone layouts fit their viewport and preserve usable interaction sizes and focus.

## Verification

Run the existing Python and browser regressions in disposable fixtures. Add browser checks for changed mesh movement/layout/motion controls and flow interactions. Inspect screenshots at 390, 768 and 1440 pixels, console errors, keyboard behavior and persistence. Obtain an independent design evaluation and address concrete findings. No paid model calls or user project mutations are required.
