"""Generic minimalist stickman art direction and semantic concept prompts."""
import re
STYLE_LOCK = (
    "GLOBAL STYLE LOCK (apply to EVERY image): clean illustrated 2D stickman "
    "cartoon with a warm off-white or muted colored background, never a blank "
    "pure-white void. Use simple layered scenery related to the scene: a ground "
    "plane and one or two contextual shapes such as a wall, tree, road or hill. "
    "Keep near-black (#1A1A1A) readable outlines, simple stick limbs and round "
    "heads; give props a little more shape and material detail while retaining "
    "clear silhouettes. Add one soft cast shadow beneath each grounded person "
    "or object and gentle tonal shading on props; use one consistent light "
    "direction. Reserve selective yellow (#F2C94C) for the focal action. "
    "Leave generous uncluttered space for later text overlays, with no more "
    "than three focal elements. A stickman appears ONLY if the SUBJECT line "
    "asks for one. If the SUBJECT is an object, diagram or landscape, do not "
    "draw any person or stickman."
)

PALETTE_LOCK = (
    "PALETTE (restrained, apply to EVERY image): background warm off-white "
    "#F3EBDD, pale sage #DDE5D8 or dusty blue #DEE5EA, chosen to fit the "
    "scene; avoid large pure-white regions. Outlines #1A1A1A, selective focal "
    "yellow #F2C94C, muted props #BDB8AE and #9B968D, optional soft accent "
    "#C97F6B. Shadows are soft desaturated versions of the local surface."
)

NEGATIVES_LOCK = (
    "NEGATIVES (apply to EVERY image): text, letters, numbers, captions, "
    "labels, logos, watermarks, harsh black shadows, heavy gradients, "
    "photorealism, 3D render, isometric depth, photographic textures, "
    "crowded backgrounds, neon colors, recurring costumed character cast, "
    "hats, glasses, costumes, multiple protagonists."
)

SAFE_ZONES_LOCK = (
    "SAFE ZONES (16:9 crop + overlays): the video crops the central 16:9 "
    "region of this 1536x1024 canvas, so keep ALL critical content inside "
    "the central 16:9 area (nothing critical in the top or bottom 8% edge "
    "bands and nothing in the outer 5% side margins). Keep the top band "
    "y=170..320 and the bottom band y=760..870 free of key elements "
    "(reserved for later text overlays)."
)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def build_concept_prompt(concept: dict, scene: dict, index: int) -> str:
    lines = [
        f"Image {index} ({concept['id']}, scene {scene['id']}): minimalist flat "
        f"cartoon composed 16:9-safe widescreen on a 1536x1024 landscape "
        f"canvas. Do not add any words, letters, numbers, labels, captions, "
        f"logos or watermarks to the image.",
        "",
        STYLE_LOCK,
        "",
        PALETTE_LOCK,
        "",
        NEGATIVES_LOCK,
        "",
        f"SCENE (semantic visual): {concept['semantic_visual']}",
        f"SUBJECT: {concept['subject']}",
        f"VISIBLE ACTION: {concept['visible_action']}",
        f"OBJECT: {concept['object']}",
        f"SPATIAL RELATION: {concept['spatial_relation']}",
        f"COMPOSITION: {concept['composition']}",
        f"SINGLE FOCUS: exactly one clear focal point — the {concept['anchor']}; "
        f"all other elements are muted and secondary.",
        "FROZEN MOMENT: one single visible moment of the action happening now; "
        "no talking heads, no static standing poses.",
        "",
        SAFE_ZONES_LOCK,
    ]
    return "\n".join(lines)

