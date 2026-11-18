# Native landscape title cover

`scripts/render_cover.mjs` renders the real B1 composition at 1920×1080. It exports `cover.png`, `cover.jpg` and `cover-provenance.json`, without modifying the prepared instance. This separate-cover tool is a workflow addition, not an upstream platform publishing feature.

## Inputs and setup

Run runtime bootstrap first. The cover script reads `runtime.json` from `KINETIC_RUNTIME_HOME`, `--work`, or the default sibling `.kinetic-tech-runtime` directory. It uses that runtime's Chrome and Playwright. Custom `--chrome` and `--playwright-root` options are available; the latter points to a directory containing `node_modules/playwright-core`. Browser temporary files default to `runtime/temp/cover`.

```text
node scripts/render_cover.mjs --work /path/to/runtime --instance /path/to/instance --out /path/to/cover --presenter-frame /path/to/selected-frame.png --title "本期主题" --label "主题标签" --subtitle "一个清楚的观点\n一个必要的补充" --footer "相关关键词"
```

Paths and text are arguments, not text for a model to execute as shell code. Quote paths with spaces. The title and presenter frame are required; label, subtitle and footer default to empty. The frame may be absolute or relative to the prepared instance. JPG, PNG and WebP are accepted. Subtitle supports a real newline or the literal `\n`, with at most two lines. `--help` lists all options.

The prepared instance must contain its settings, fonts, textures and native code. The frame should have the same subject/crop assumptions as the instance's presenter metadata; adjust the inputs rather than stretching a portrait to fill a landscape scene.

## Content and visual checks

Use a clear real frame from the supplied video: eyes open, natural expression, unobstructed face. Select a short title that expresses the whole video's actual topic. Do not copy a reference title or a claimed outcome that the video does not support.

The cover has a dark technology background, a large metallic title on the left, the presenter on the right, and optional gold supporting text. Caption overlays, timecode and technical labels are hidden only for the cover. Long titles or supporting lines that do not fit are rejected instead of silently cropped. Rewrite the text and retry in a fresh output directory.

Actually inspect the PNG/JPG at full size and as a small preview: no cropped title, missing glyphs, distorted subject or accidental debug text. Existing outputs are not overwritten. Generated provenance includes the source image hash and local paths for the user's own project; it should be reviewed before publishing a project's evidence files.

## Final delivery

The cover renderer only creates the images. The workflow/finish stage replaces frame zero of the final video, without adding introductory time or shifting the original audio. Deliver both independent image formats alongside the MP4. A first-frame image does not automatically set a social platform's publishing cover; the user can choose the separate JPG there.

This layout is landscape. A vertical version requires a separate layout adaptation and review, not cropping away the existing left and right content.
