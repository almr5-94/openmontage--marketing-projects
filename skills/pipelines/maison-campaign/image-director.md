# Image Director

Produce one commanding image per execution from the shot list. Free routes first. Generation runs **only through the Runway MCP connector**, and only after the human elects it: show the model, the credits per call and the count, then record a `paid_election` decision (`record_election`) carrying the election ID before any call. Prompts describe qualities (light, hand, paper, palette); they never name a living artist, a photographer or a real house. Free sources first: Met, Cleveland, Rijksmuseum, AIC (CC0), Pexels, Pixabay, seeded `generative_art`.
Every image that may show a person passes `run_face_gate` (photo or cartoon mode) before it is placed; a failure moves the file to `components/` with the reason, never deletes it.
Keep every take (the rejected ones move to `components/`). Write `asset_manifest` with provenance.
