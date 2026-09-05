# VTON test fixtures — person reference images

Deterministic test fixtures for the pose/hand artifact regression harness
(`backend/tests/test_vton_pose_artifact_regression.py`). These are used ONLY
for automated regression testing of the artifact-detection harness — never
as final production acceptance (per the 2026-09-05 directive).

- `person_two_hands.jpg` — single subject, 2 hands visible
  (Unsplash photo-1594938298603-c8148c4dae35, via the production catalog
  product-1 asset, Unsplash licence).
- `person_arms_crossed.jpg` — single subject, arms-crossed non-neutral pose
  (Unsplash photo-1521119989659-a83eee488004, Unsplash licence).

CV models in `backend/cv_models/` (MediaPipe Tasks, Google AI, Apache-2.0):
- `hand_landmarker.task` — https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task
- `pose_landmarker_lite.task` — https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task

- `person_hands_on_waist.jpg` — single subject, hands-on-waist (akimbo) pose,
  2 hands + full pose reliably detected (the exact pose category from the
  2026-09-05 directive). Stock agency preview (colourbox), used as a test
  fixture only.
