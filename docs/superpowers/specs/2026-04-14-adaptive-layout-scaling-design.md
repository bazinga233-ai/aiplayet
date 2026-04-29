# 2026-04-14 Adaptive Layout Scaling Design

## Goal

Make the workbench keep the same three-column desktop composition on different desktop resolutions, while scaling panel spacing, padding, typography, and preview height proportionally to the viewport.

## Problem

The current frontend layout mixes responsive breakpoints with machine-specific fixed sizes. On another desktop resolution, the page still uses the same desktop structure, but several hard-coded values cause the visual proportions to drift:

- top banner padding and card density stay too large or too small
- the center preview height is tied to a large fixed clamp
- the three columns keep their desktop ratio, but inner spacing and typography do not scale with them
- the result panel scroll region and action cards do not stay visually balanced with the center preview

## Chosen Approach

Use a lightweight viewport scaling hook in the frontend root, compute a desktop `uiScale` from the current window width and height, and expose the result through CSS custom properties.

Why this approach:

- keeps the existing three-column structure intact
- avoids dozens of hand-tuned breakpoints for specific devices
- lets the page scale proportionally across 1366x768, 1600x900, 1920x1080, and similar desktop resolutions
- stays local to layout code, without touching data flow or task logic

## Scope

In scope:

- add a small hook that reads `window.innerWidth` and `window.innerHeight`
- compute a bounded desktop scale factor and derived CSS variables
- apply those variables at the app shell level
- replace the key hard-coded desktop layout values with variable-driven values
- add regression tests for multiple viewport sizes

Out of scope:

- redesigning the layout
- changing the mobile stacked layout
- changing business logic, API calls, or result rendering behavior

## Scaling Model

Base desktop reference:

- width: 1600
- height: 960

Derived values:

- `uiScale`: bounded desktop scale factor
- `shellPadding`: page outer padding
- `layoutGap`: spacing between major columns and stacked panels
- `panelPadding`: panel internal padding
- `panelRadius`: major panel corner radius
- `leftColumnMin`: minimum width of the left column
- `previewFrameHeight`: center preview target height for desktop
- `scriptViewerMinHeight`: lower bound for the right script viewer on non-desktop layouts

Behavior:

- desktop resolutions smaller than the reference shrink proportionally, but stop at a lower bound
- larger desktop resolutions expand moderately, but stop at an upper bound
- existing mobile breakpoints still handle narrow screens

## Implementation Plan

1. Add `useWorkbenchScale` hook under `frontend/src/hooks/`.
2. Compute a desktop scale profile from the viewport and return a CSS variable map.
3. Apply the variable map on the root `.app-shell` in `frontend/src/App.tsx`.
4. Replace the fixed desktop dimensions in `frontend/src/styles.css` with the new CSS variables.
5. Keep the existing desktop layout and task/result alignment logic in place.
6. Add tests proving that different desktop viewport sizes produce different scale variables.

## Validation

The change is correct when:

- the same three-column desktop layout remains visible on common desktop resolutions
- smaller desktop screens render a visibly denser but still aligned layout
- larger desktop screens render a roomier layout without oversized preview height
- front-end tests confirm scale variables change across viewport sizes
