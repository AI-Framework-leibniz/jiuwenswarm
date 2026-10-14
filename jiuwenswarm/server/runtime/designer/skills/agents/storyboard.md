# Storyboard Agent Skill

Emit a timed camera table — **one row per clip**. Each row needs: timeline, camera framing (shot size / move as film language), action, scene change flag, and a **clip prompt**. Align actions to **character_specs** and setting to **scene_specs**.

Materialize the Brief's full narrative/content arc and speech plan into distinct sequential **clips**.
Every **clip** must advance the story or message; do not use repeated action or alternate coverage as runtime filler. Keep exact dialogue/voiceover with its speaker and timed **clip**, and honor silence.

Keep exactly one climax. Each clip carries a Director-authored start state, the new action, and an irreversible end state as STRUCTURED fields (metadata); the next clip opens from the previous end (**shot_consistency**). Record per-clip wardrobe, emotion, and presence when they change, without changing the character's face. Locks (scene locks, character locks, scene bible, clip locks with initial/final positioning) live in those structured fields only — never write lock text into the storyboard table or the brief.
