---
name: mod-visual-validation
description: "对照基线检查 Mod 截图或录屏。用于模型、材质、动画、光照、姿态、比例和画面异常的视觉验收；不用于编辑图片。Compare mod screenshots or recordings against a baseline for model, material, animation, lighting, pose, proportion, and artifact acceptance; do not edit images."
---

# Mod Visual Validation

Use the `glm-vision` MCP as the video engine: `analyze_video_diff` pixel-diffs the recording, localizes the spike frame pairs where the picture changes, and writes side-by-side annotated JPEGs. Read those JPEGs yourself and give the semantic analysis (what changed and why). The MCP server does pure pixel work and calls no vision model — subject localization is also yours: when you need subject-focused analysis, first run `probe_frame`, Read the returned frame, locate the main character/subject yourself, and pass its pixel box (`x,y,w,h`) as `subject` to `analyze_video_diff`. Still images are Read by the main model directly. This skill defines the comparison protocol; it does not duplicate vision algorithms and does not modify the supplied media.

## Define the comparison

Identify:

- the validated baseline and candidate;
- the exact question or acceptance criterion;
- relevant scene, lighting, camera, pose, equipment, and frame/time;
- whether the evidence supports a global judgment or only the shown view.

If capture conditions differ, separate visible mod changes from camera, exposure, animation frame, field of view, or environment changes. Request an additional matched capture only when the mismatch prevents a meaningful conclusion.

## Select evidence

Use the smallest sufficient set:

- geometry, proportion, attachment angle: matched front and side views;
- material, brightness, transparency, metalness: representative normal, dark, and bright scenes;
- animation, jitter, floating, transition: the relevant recording interval or matched frames;
- distant face or silhouette readability: one near and one representative far view.

For video, run `analyze_video_diff` on the recording: its report already includes duration, frame rate, and the spike list with timestamps (pulse = isolated defect candidate, action = normal fast motion), and it writes annotated comparison JPEGs for each spike. When background motion drowns the subject, rerun with `subject` obtained via `probe_frame` (annotate the frame yourself). Read those JPEGs, judge whether the flagged spikes explain the reported defect, and record the timestamps in the verdict.

## Produce a standardized verdict

Report:

1. observable differences, without assigning a cause prematurely;
2. pass, fail, or inconclusive against the stated criterion;
3. confidence and evidence limitations;
4. the most likely technical layer, clearly labeled as an inference;
5. the smallest next capture or experiment if unresolved.

Visual evidence can route diagnosis but cannot by itself prove a binary resource, hook, or configuration cause. Use `reengine-asset-diagnosis` for layer diagnosis and `mod-debugging` for runtime log evidence.

When project rules require it, save the textual verdict in the project's docs and refer to that verdict later instead of repeatedly loading old media.
