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
| Topology freeze flag | `freeze_clip_topology` | `freeze_shot_topology` |
| Animate-still binding | `animate_still` | `animate_keyframe` |
| Prior-edit strategy | `edit_prior_clip` | `edit_prior_keyframe` |

## Rules

1. **One term per concept** in code identifiers, JSON keys, roles, filenames, UI product strings, and tests.
2. **No placeholder aliases** (e.g. `shot_is_clip`, dual-read of old keys, `_LEGACY` value acceptors for renamed enums).
3. **Pipeline path:** Brief → Character specs → Scene specs → Storyboard → Clips → Compose. No frame/keyframe nodes on the default R2V path.
4. **Consistency vs unit:** The video unit is always `clip`. The cross-clip consistency feature is named `shot_consistency`.
5. **Skills exception:** In cinematic skill/prompt prose only, “shot” may appear as a filmmaking concept. Everywhere else use `clip`. User-input NLP may still *parse* legacy words (`keyframe`, `镜头`) into clip counts.

## Banned terms (production code)

`solo`, `solos`, `keyframe` / `keyframes` (as identifiers or product strings), `scene_plate`, `scene_bible`, `place_hygiene`, `continuity_card`, `shot_index`, `character_design` (as role), `PIPELINE_FRAME`, `n_frame_`.

Allowlist exceptions:

- Skills markdown teaching film language (“shot size”, “this shot”).
- `director_contract` user-prompt NLP regex that recognizes legacy count words.
- Pose string `present_in_frame_clearly_visible` (literal “in frame”, not pipeline role).

## File renames

| Old | New |
|---|---|
| `pipeline/continuity_card.py` | `pipeline/character_consistency.py` |
| `pipeline/movie_continuity_guide.py` | `pipeline/movie_consistency_guide.py` |
| `pipeline/clip_shot_scope.py` | `pipeline/clip_scope.py` |
| `pipeline/director_shot_sheet.py` | `pipeline/director_clip_sheet.py` |
| `pipeline/shot_staging_lock.py` | `pipeline/clip_staging_lock.py` |
| `pipeline/storyboard_shot_state.py` | `pipeline/storyboard_clip_state.py` |
| `chat_shot_references.py` | `chat_clip_references.py` |
| `pipeline/clip_continuity_contract.py` | `pipeline/shot_consistency_contract.py` |
| `pipeline/leaf_agent_continuity.py` | `pipeline/leaf_agent_consistency.py` |
| `pipeline/keyframe_policy.py` | `pipeline/clip_policy.py` |
| `pipeline/production_bible.py` | `pipeline/production_specs.py` |
| `skills/agents/frame.md` | **deleted** |
| Frontend `storyboardShots.ts` | `storyboardClips.ts` |
| `test_continuity_card.py` | `test_character_consistency.py` |
| `test_clip_shot_scope.py` | `test_clip_scope.py` |
| `test_shot_staging_lock.py` | `test_clip_staging_lock.py` |
| `test_storyboard_shot_state.py` | `test_storyboard_clip_state.py` |
| `test_clip_continuity_contract.py` | `test_shot_consistency_contract.py` |
| `test_clip_continuity_holds.py` | `test_shot_consistency_holds.py` |
| `test_missing_shot_scrub.py` | `test_missing_clip_scrub.py` |
| `test_shot_reference_grammar.py` | `test_clip_reference_grammar.py` |
| `test_shot_beat_budget.py` | `test_clip_beat_budget.py` |

## Key symbol renames

| Old | New |
|---|---|
| `PIPELINE_CHARACTER_DESIGN` / `NODE_ROLE_CHARACTER_DESIGN` | `PIPELINE_CHARACTER` / `NODE_ROLE_CHARACTER` (`"character"`) |
| `PIPELINE_FRAME` / `NODE_ROLE_FRAME` / `n_frame_*` / `frame_node_id` | **removed** |
| `shot_index` / `node_shot_index` | `clip_index` / `node_clip_index` |
| analysis `"shots"` | `"clips"` |
| `target_shot_count` | `target_clip_count` |
| `scene_card_plus_clip_shots` | `scene_specs_plus_clips` |
| `compose_from_solo_refs` | `compose_from_character_specs` |
| `clip_from_scene_and_solos` | `clip_from_scene_and_character_specs` |
| `continuity_card` APIs | `character_consistency` |
| `production_bible` | `production_specs` |
| `freeze_shot_topology` | `freeze_clip_topology` |
| `VIDEO_ANIMATE_KEYFRAME` / `"animate_keyframe"` | `VIDEO_ANIMATE_STILL` / `"animate_still"` |
| `edit_prior_keyframe` | `edit_prior_clip` |
| `_explicit_shot_count_from_prompt` | `_explicit_clip_count_from_prompt` |
| `_heuristic_shots` / `_select_shots_for_budget` | `_heuristic_clips` / `_select_clips_for_budget` |
| `ensure_shot_start_end_states` | `ensure_clip_start_end_states` |
| Canvas “Scene N: Shot M” | “Scene N: Clip M” |
| UI i18n “this shot” / “Has shot” | clip-oriented copy (EN/ZH) |

## Surfaces touched (summary)

- **Schema:** `jiuwenswarm/common/schema/designer_graph.py`
- **Pipeline / orchestration:** `smart_graph.py`, `script_analysis.py`, `orchestration.py`, `executor.py`, `reference_led.py`, handlers, Wan binding, prompt practice, axis/cast locks
- **Frontend:** `features/designer/*`, i18n `en.json` / `zh.json`, fixtures
- **Skills:** `skills/**` (character/scene/clip vocabulary; `frame` agent removed from index)
- **Docs:** `docs/reference-mode/*`, this file
- **Tests:** `tests/unit_tests/designer/*` (~45 modules; parametric reference-led matrix ~40×1000)

## Verification

```text
pytest tests/unit_tests/designer/ -q --no-cov
→ 160447 passed
```

Ban-term scan on production designer Python/TS (excluding skills cinematic allowlist and this doc): clean aside from `present_in_frame_clearly_visible` pose literal and director NLP regex.

## Persistence note

Hard break: pre-rename saved graphs (`shots`, `shot_index`, `keyframe_*`, `character_design`, `n_frame_*`, etc.) are not migrated and may fail to load on this branch.
