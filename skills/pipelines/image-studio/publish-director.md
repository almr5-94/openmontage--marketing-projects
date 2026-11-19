# Publish Director — Image Studio Pipeline

## When to Use

The user approved the images. Package and hand them over. Produce `publish_log`.

## Steps

1. Final names in `projects/<id>/renders/`: `<project>_<frame>_<format>.<ext>`, e.g.
   `spring-offer_f01_instagram_story.jpg`.
2. Send every final file to the user with the session's file-send tool. A path alone is not a
   hand-off.
3. If the user asked for posting, use the publisher tools under `tools/publishers/` only with
   their explicit go-ahead for that post; otherwise `publish_log.entries[].status` is
   `exported` with `platform` set to the intended platform.
4. `publish_log` entries: one per platform/format with `timestamp` (ISO 8601).
