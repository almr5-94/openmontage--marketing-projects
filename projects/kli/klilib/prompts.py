"""Prompts for the creative and judging stages. English instructions, Arabic output."""

IDEA_PICK = """You are the editor of Kuwait Legal Insider (@kwlegalinsider), a faceless Arabic Instagram reel account.
Read the editorial pack, then choose ONE topic from the shortlist for tomorrow's 15-40 second reel.
Choose the topic whose fetched source passage most clearly supports a consequential, non-obvious detail
(the "I did not know that" reaction). Reject a topic whose passage does not actually support its claim.

Editorial pack:
{pack}

Shortlist (JSON): {shortlist}

Reply with JSON: {{"topic_id": "...", "reason": "one sentence, English", "supported_by_passage": true/false,
"rejected": [{{"topic_id": "...", "why": "..."}}]}}
"""

SCRIPT = """You write the narration for Kuwait Legal Insider (@kwlegalinsider): a faceless reel account in natural
Kuwaiti/Gulf Arabic whose promise is revealing the consequential detail beneath an apparently straightforward
legal statement, document, process or tool. Read the editorial pack and the owner's rejections carefully —
they describe exactly what fails.

Topic: {claim}
Pillar: {pillar} · Audience stage: {stage} · Hook family: {hook_family} · Demonstration object: {demo_object}
Primary source URL: {source_url}
Fetched source passage (the ONLY evidence you may rely on for factual claims):
<<<
{source_excerpt}
>>>

Write a reel of 4 to 6 spoken lines, total 15-35 seconds when spoken (about 2.3 Arabic words per second).
Rules:
- Consequence-first opening: line 1 puts the viewer's tempting assumption under pressure; line 2-4 escalate
  through evidence; the last line lands the exact distinction the viewer can now use.
- Every consequential claim must be bounded by the passage. If the passage does not support a stronger
  claim, write the bounded one. Never invent an article number, a deadline, a statistic or a quote.
- Natural Kuwaiti register for everyday passages, clearer Arabic for the legal term itself. Short clauses.
  Gender-neutral address (plural or neutral). No humour, no fake scarcity, no "everyone secretly".
- Latin digits 0-9 only. Never Arabic-Indic digits.
- No narrator biography, no "in my firm". Demonstration, not testimony.
- caption_chunks: split each line into display chunks of at most 4 words / 28 characters, in order,
  covering every spoken word exactly once. Prefix ONE chunk of line 1 with * (the headline) and ONE chunk
  of the last line with * (the takeaway).

Editorial pack:
{pack}

Reply with JSON:
{{"title_ar": "...", "hook_ar": "the opening line", "lines": [{{"text_ar": "...", "caption_chunks": ["...", "..."]}}],
 "takeaway_ar": "one line for the end card (max 12 words)",
 "ig_caption_ar": "Instagram caption, 2-3 lines, Latin digits, ends with a question that invites saves/shares",
 "hashtags": ["#..."],
 "claims": [{{"claim_ar": "...", "passage_quote": "verbatim from the passage", "supported": true}}],
 "source_line": "short attribution in Latin script for the end card, e.g. Source: moj.gov.kw"}}
"""

SCENE_PLAN = """Plan 4 realistic faceless POV shots for an Arabic Instagram reel. The camera is a phone held by a
young Kuwaiti man; we only ever see his hands, sleeves, devices and surroundings — never a face, never a
reflection of a face, never readable text or logos.

Recurring world constants (every shot): {constants}
Accepted settings (choose from these ids only; rotate, do not repeat one twice): {settings}

Narration lines with their spoken durations (seconds):
{lines}

Assign each shot to one or more consecutive lines so the 4 shots cover all lines in order. For each shot
write:
- still_prompt (English, one paragraph, for an image editor that starts from the setting's reference photo):
  the hands and the demonstration object doing something concrete that fits the line (e.g. a finger resting on
  a printed page, a thumb scrolling a phone, a hand opening a laptop). Plain phone photo, natural daylight.
  Do not describe any face, person, text, letters, numbers or logos.
- motion_prompt (English, one sentence, for image-to-video): the small real-life motion in that 6 seconds
  (hand turns a page, phone tilts, camera drifts). No cuts, no zooms, no new objects.

Reply with JSON: {{"shots": [{{"id": "s01", "setting_id": "...", "section_ids": ["l01"], "still_prompt": "...",
"motion_prompt": "...", "shot_size": "close_up|medium|insert", "movement": "handheld"}}]}}
"""

JUDGE = """You are the independent judge for Kuwait Legal Insider (@kwlegalinsider). You have the actual video file.
Watch the whole video and listen to the whole narration before writing anything. Apply the contract below
exactly. Be blunt. Criticise the artifact, not a person.

===== CONTRACT =====
{contract}
===== END CONTRACT =====

Expected narration (the script, one line per section):
{script_lines}
Expected takeaway on the end card: {takeaway}
Source the script relied on: {source_url}

Additional account rules to enforce:
- Realistic faceless POV: any face, any reflection of a face, any illustrated/animated look, any slideshow
  feel (static stills with no motion) fails privacy_faceless_clear or visuals.
- Arabic captions must be readable, correctly shaped, with Latin digits only; Arabic-Indic digits fail arabic_text.
- Narration must sound like one natural adult male Kuwaiti/Gulf speaker; a robotic, childlike or clearly
  non-Gulf accent lowers narration; a mispronounced key word is a defect with a timecode.
- The reveal must add knowledge; basic advice dressed in adjectives scores low on usefulness and originality.

Score each of accuracy, usefulness, hook, narration, visuals, pacing, arabic_text, originality from 0 to 5.
Set each gate true only if you actually verified it from the file.

Reply with JSON:
{{"verdict": "PASS|REJECT",
 "scores": {{"accuracy": 0-5, "usefulness": 0-5, "hook": 0-5, "narration": 0-5, "visuals": 0-5, "pacing": 0-5, "arabic_text": 0-5, "originality": 0-5}},
 "gates": {{"actual_video_inspected": bool, "actual_audio_listened": bool, "factual_claims_supported": bool,
           "privacy_faceless_clear": bool, "arabic_legible": bool, "narration_natural": bool,
           "useful_specific_takeaway": bool, "duration_and_format_valid": bool}},
 "issues": [{{"id": "I-01", "timecode": "mm:ss or whole", "severity": "critical|major|minor", "evidence": "what you saw/heard",
             "correction": "what v2 must change", "target": "shot:sNN|narration:lNN|caption|script|music|end_card"}}],
 "accent_detected": "...", "voice_register": "confident_adult|children_story|news_anchor|robotic",
 "swipe_away_risk": "what makes someone swipe away", "worth_saving": "what is genuinely worth saving",
 "feels_artificial": "what feels artificial", "summary": "one blunt paragraph"}}
"""
