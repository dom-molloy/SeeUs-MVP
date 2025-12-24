# SeeUs MVP Upgrade Checklist (Diff-Style)

## Files changed / added
- **questions.py** ✅ Rewritten to canonical schema + primary/branch + tone variants
- **scoring.py** ✅ Updated to new question IDs/dimensions (MVP heuristic)
- **reporting.py** ✅ Updated dimension order/labels
- **db.py** ✅ Sessions table: add `tone_profile` (auto-migration) + create_session accepts it
- **app.py** ✅
  - Adds Truth Temperature selector
  - Uses tone-specific prompts
  - Adds branch queue per respondent
  - Adds Mirror Moment after 5 primary answers
  - Progress counts only primary questions

## Behavioral changes (expected)
- Users see **10 core questions** (primary)
- Follow-ups are asked only when needed (branch queue)
- Mirror Moment appears once mid-way (per respondent per session)
- Tone controls question phrasing

## Manual test script (5 minutes)
1) Create relationship → Start Duo session → pick tone “No sugarcoating”
2) Answer Q1 with a short/vague response → verify it queues **values_example_followup**
3) Answer through Q5 → verify **Mirror Moment** appears
4) Confirm “Not quite” → enter correction → verify response saved as `mirror_correction`
5) Finish core 10 for A and B → go to Report → run Deep Research → Download PDF

## Known limitations (MVP)
- Branch triggers are intentionally simple (vagueness-based)
- Mirror Moment synthesis is heuristic (LLM upgrade later)
- Invite link does not enforce auth beyond token
