# Third party assets and dependencies

Inter and League Spartan are redistributed under SIL Open Font License 1.1. The license texts and credits are in `src/stickman/assets/fonts/OFL-*.txt` and must remain with the fonts.

The included pop and whoosh effects and ambient instrumental background are original procedural assets released under the MIT license of this repository. No songs, cloned voices, private channel clips, or personal media are included.

## Bundled background music: "Accralate" by Kevin MacLeod (CC BY 4.0)

`src/stickman/assets/music/accralate.mp3` is "Accralate" by Kevin MacLeod (incompetech.com), used under Creative Commons Attribution 4.0 International (CC BY 4.0): http://creativecommons.org/licenses/by/4.0/. Source download: archive.org/details/Incompetech (md5 `b9a667797ffb9db79bb4b9e36bf26790`, duration ~305 s). License text and provenance are kept next to the track in `src/stickman/assets/music/LICENSE.txt`, with sha256 provenance in `src/stickman/assets/music/manifest.json`.

It is the default background (`render.bgm=accralate`) and is mixed under the narration with ducking (sidechain) at `render.bgm_volume` 0.10. The pipeline automatically appends the required credit to every `output/caption.txt` and delivered `caption.txt` without touching your own credits:

"Accralate" Kevin MacLeod (incompetech.com) — Licensed under Creative Commons: By Attribution 4.0 — http://creativecommons.org/licenses/by/4.0/

To opt out, set `render.bgm` to `none` (no music, no credit). To keep the procedural bed, use `render.bgm` `bundled` (or `ambient`). To use your own licensed track, set `render.bgm` to its path (relative to the project, or absolute) and keep its own attribution; the automatic CC BY credit is only added for the bundled Accralate track.

Python packages, FFmpeg, and the Codex CLI retain their own licenses and service terms. FFmpeg and Codex binaries are not included in this repository. Check the license of the FFmpeg build you install and the terms of any remote provider you use. Permission to use this code does not grant rights to external voices, models, or assets you add.

The procedural ambient bed stays available with `render.bgm=bundled` (or `ambient`); set `render.bgm` to `none` or to a path for your own licensed track. Keep applicable attribution in your videos.
