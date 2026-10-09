# Designer Naming Conventions

Branch: `design-develop-ConsistentNaming`  
Scope: `jiuwenswarm/` only (hard break — no load-time aliases for old graphs).

## Canonical vocabulary

| Concept | Use | Do not use |
|---|---|---|
| Person asset | `character` | solo(s), character card, character still |
| Character asset payload | `character_specs` | character card, solo sheet, identity sheet (as product name) |
| Setting asset | `scene` | place |
| Scene asset payload | `scene_specs` | scene plate, scene bible, scene card (as product name) |
| Timed video unit | `clip` | shot, beat (as unit name) |
| Clip index / analysis list | `clip_index`, `clips[]` | `shot_index`, `shots[]` |
| Graph node id | `n_clip_{n}`, `n_character_{…}`, `n_scene_{…}` | `n_frame_*`; role `character_design` |
| Pipeline role | `character`, `scene`, `clip`, `compose`, … | `character_design`, `frame`, `keyframe`, `shot` |
| Person look lock | `character_consistency` | continuity, continuity_card (person) |
| Setting look lock | `scene_consistency` | place hygiene, scene continuity |
| Cross-clip cinematic lock | `shot_consistency` | clip continuity, beat continuity |
| Default graph mode stamp | `scene_specs_plus_clips` | `scene_card_plus_clip_shots` |

## Rules

1. **One term per concept** in code identifiers, JSON keys, roles, filenames, UI product strings, and tests.
2. **No placeholder aliases** (e.g. `shot_is_clip`, dual-read of old keys).
3. **Pipeline path:** Brief → Character specs → Scene specs → Storyboard → Clips → Compose. No frame/keyframe nodes on the default R2V path.
4. **Consistency vs unit:** The video unit is always `clip`. The cross-clip consistency feature is named `shot_consistency`.
5. **Skills exception:** In cinematic skill/prompt prose only, “shot” may appear as a filmmaking concept. Everywhere else use `clip`.

## Banned terms (production code)

`solo`, `solos`, `keyframe`, `keyframes`, `scene_plate`, `scene_bible`, `place_hygiene`, `continuity_card`, `shot_index`, `character_design` (as role), `PIPELINE_FRAME`, `n_frame_`.

## File renames

_(Filled during refactor — see Change log below.)_

## Change log

_(Per-file inventory filled as renames land.)_
