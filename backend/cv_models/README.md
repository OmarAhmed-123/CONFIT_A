# CV verification models (test/CI only)

MediaPipe Tasks landmarker models used by the VTON pose/anatomy regression
harness (`backend/tests/vton_artifact_check.py`). NOT part of the production
runtime closure (the harness is test-only; the dependency gate keeps the
Vercel bundle free of mediapipe).

- `hand_landmarker.task` (7.8 MB) — MediaPipe HandLandmarker (Google, Apache-2.0)
- `pose_landmarker_lite.task` (5.8 MB) — MediaPipe PoseLandmarker lite (Google, Apache-2.0)

Download (if ever needed to re-fetch):
  https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task
  https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task
