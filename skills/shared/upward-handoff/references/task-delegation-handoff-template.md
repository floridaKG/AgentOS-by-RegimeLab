# Task Delegation Handoff Template

A concrete example: delegating a gold Mandelbrot SVG logo to a design agent.

## Structure (annotated)

```
# Handoff: [Task Title]

**To:** [Agent name/role]
**From:** [Your name / agent role]
**Status:** [Phase state — e.g. Design + prototype on scratch landing page, no main app changes yet]

---

## The Goal

[Single sentence. Then a paragraph with the key requirement.]

---

## Design / Context Reference

[Point to existing code or assets. Include specific paths and what to look for.]

| File | What to reference |
|---|---|
| path/to/file.js | Line X, existing pattern |
| path/to/asset.svg | Current version to replace |

---

## File Inventory

| File | Role | What to do |
|---|---|---|
| path/to/file.tsx | Description | Replace / update / create |
| path/to/another.tsx | Description | Update import |

Every file the agent will touch, with the action needed.

---

## Execution Plan

### Phase 1: [Design / Prototype]

What to build, what format, constraints.
"Do NOT modify the app yet."

### Phase 2: [Test / Preview]

Preview page or validation before integration.
What to check, how to verify.

### Phase 3: [Integration]

Once approved, swap into the codebase.
Files to replace, files to delete.
Verify the build compiles.

---

## Key Constraints

- Format (SVG > PNG)
- Color palette
- Size limits
- What NOT to do
- What NOT to touch

---

## Deliverables

1. First deliverable — description + path
2. Second deliverable — description + path
3. Verification — how to confirm done
```

## Full Example (Gold Mandelbrot Logo)

Key sections used:

- **Goal**: "Replace the current project logo with a Mandelbrot set fractal in gold, transparent background"
- **Design reference**: Pointed to `watermark.ts` line 70 (existing Mandelbrot base64) and current `logo-mark.svg`
- **File inventory**: 4 files with roles (LogoMark.tsx, FractalLogo.tsx, logo-mark.svg, logo.png)
- **Execution plan**: Phase 1 (SVG design) → Phase 2 (scratch preview page at all sizes on dark+light) → Phase 3 (swap into app after approval)
- **Constraints**: Gold only, no canvas, no blue, transparent bg, under 15KB, SVG preferred over PNG
- **11 usage locations**: Listed every file that imports LogoMark

## When to use this template

- **Another agent is executing work you've scoped** — you know the codebase, the files, and the approach
- **The task is bounded and concrete** — not exploratory or analytical
- **You want to test work in isolation before touching the main app**

## When NOT to use this template

- You're surfacing findings for analysis → use the upward handoff format instead
- The other agent has more context than you → use P7 peer briefing pattern
- You don't know the right approach → use upward handoff to ask
