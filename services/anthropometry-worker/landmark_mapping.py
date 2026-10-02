"""Feature 05 — MediaPipe Pose (33 world landmarks) -> CAESAR-73 cloud.

The Landmarks2Anthropometry model (VISAPP 2024, vendored) consumes 73 named
CAESAR anatomical landmarks in millimetres (x=lateral with the subject's LEFT
positive, y=depth with the BACK positive, z=height UP), centred on Substernale
by the vendor's own ``process_landmarks``. A monocular photo observes a subset
of those points via MediaPipe Pose (Apache-2.0, world landmarks in metres,
hip-centred, x right, y DOWN, z negative toward the camera).

This module builds the full 73-point cloud from the 33 observed joints:

  * DIRECT   — a MediaPipe joint IS the landmark (Tragion<-ear,
               Calcaneous<-heel, Metacarpal/Metatarsal bases<-knuckles...).
  * SCAFFOLD — offsets around an observed joint whose DIRECTIONS come from the
               observed skeleton and whose MAGNITUDES are fractions of the
               subject's own frame. Every fraction below was CALIBRATED on the
               vendored demo cloud (a real CAESAR subject shipped with the
               model): see CALIBRATION notes — not hand-guessed ratios.
  * GIRDLE WIDENING — MediaPipe shoulder/hip joints sit medial to the CAESAR
               surface points (Acromion tips, greater trochanters). The cloud
               widens them to CAESAR proportions using the demo subject's own
               width-to-torso ratios (0.796 / 0.694), anchored on the
               subject's observed torso length.
  * MIRROR   — unobservable BACK points are placed symmetrically to their
               front counterparts (PSIS vs ASIS, Nuchale, 10th Rib Midspine,
               Waist-Post) using demo-calibrated depth offsets.

Every approximation is disclosed in the worker's response
(``landmark_source: mediapipe_pose_world_approx``); every measurement carries
the product disclaimer ±2-3 cm. Pure functions only — numpy in, plain dicts
out — so the mapping is unit-testable without MediaPipe or the model.
"""
from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

import numpy as np

# MediaPipe Pose world-landmark indices (33 joints).
MP = {
    "nose": 0, "left_eye_inner": 1, "left_eye": 2, "left_eye_outer": 3,
    "right_eye_inner": 4, "right_eye": 5, "right_eye_outer": 6,
    "left_ear": 7, "right_ear": 8, "mouth_left": 9, "mouth_right": 10,
    "left_shoulder": 11, "right_shoulder": 12, "left_elbow": 13, "right_elbow": 14,
    "left_wrist": 15, "right_wrist": 16, "left_pinky": 17, "right_pinky": 18,
    "left_index": 19, "right_index": 20, "left_thumb": 21, "right_thumb": 22,
    "left_hip": 23, "right_hip": 24, "left_knee": 25, "right_knee": 26,
    "left_ankle": 27, "right_ankle": 28, "left_heel": 29, "right_heel": 30,
    "left_foot_index": 31, "right_foot_index": 32,
}

# ── CALIBRATION (measured on the vendored CAESAR demo subject, metres) ──────
# demo: shoulder width .437, trochanter width .381, torso (acromion-mid ->
# trochanter-mid) .549, face width .171, ASIS->PSIS depth .226.
DEMO = {
    "shoulder_w": 0.437, "trochanter_w": 0.381, "torso": 0.549,
    "face_w": 0.171, "asis_psis_depth": 0.226,
}
SHOULDER_W_FRAC = DEMO["shoulder_w"] / DEMO["torso"]      # 0.796
TROCHANTER_W_FRAC = DEMO["trochanter_w"] / DEMO["torso"]  # 0.694

# Midline scaffolds, (up_frac, fwd_frac) x torso — EXACT symmetrized demo
# fractions (Lt/Rt mirrored and averaged; rotation-induced lateral drift zeroed).
MID_FROM_SHOULDER = {
    "Suprasternale": (-0.060, +0.131),
    "Substernale": (-0.479, +0.222),
    "Cervicale": (+0.137, -0.025),
    "Nuchale": (+0.268, -0.016),
}
MID_FROM_HIP = {
    "Crotch": (-0.264, 0.000),
    "Waist, Preferred, Post.": (+0.272, -0.067),
    "10th Rib Midspine": (+0.406, -0.072),
}
# Per-side scaffolds: (up_frac, fwd_frac, inward_frac) x torso from the anchor.
FROM_ACROMION = {
    "Axilla, Ant.": (-0.199, +0.093, 0.015),
    "Axilla, Post.": (-0.228, -0.094, 0.019),
    "Clavicale": (-0.042, +0.131, 0.228),
    "Thelion/Bustpoint": (-0.326, +0.201, 0.108),
}
FROM_TROCHANTER = {
    "ASIS": (+0.100, +0.145, 0.051),
    "PSIS": (+0.166, -0.119, 0.174),
    "Iliocristale": (+0.231, +0.023, 0.008),
    "10th Rib": (+0.289, +0.155, 0.075),
}
# Limb widths as fractions of the widened girdle widths (exact demo values:
# elbow 79mm, wrist 63mm, knee 124mm, ankle 83mm, foot 108mm).
LIMB_WIDTH = {
    "elbow": 0.182,   # x shoulder width
    "wrist": 0.145,   # x shoulder width
    "knee": 0.325,    # x trochanter width
    "ankle": 0.217,   # x trochanter width
    "foot": 0.284,    # x trochanter width
}
# Head scaffolds x face width (tragion-to-tragion), exact demo fractions.
HEAD = {
    "sellion_up": 0.15, "sellion_fwd": 0.03,     # from the eye-line midpoint
    "supramenton_down": 0.25,                    # below the mouth midpoint
    "gonion_down": 0.53, "gonion_fwd": 0.05, "gonion_inward": 0.16,
}

REQUIRED_VISIBILITY = ("left_shoulder", "right_shoulder", "left_hip", "right_hip",
                       "left_knee", "right_knee", "left_ankle", "right_ankle",
                       "left_heel", "right_heel")
MIN_VISIBILITY = 0.5

# Pose-quality envelopes (the vendored model was trained on CAESAR standing
# A-pose scans; outside these envelopes the reading is refused, honestly).
MAX_YAW_DEG = 25.0         # shoulder-line yaw relative to the camera
MAX_SHOULDER_TILT_DEG = 15.0
MAX_ARM_BEND_RATIO = 0.10  # shoulder→elbow→wrist path vs chord; CAESAR A-pose
                           # keeps arms essentially straight (~0.01-0.05).
                           # Hands-on-hips reads ~0.15+ and is refused: the
                           # vendored models were trained on straight-arm
                           # A-pose scans and bent arms distort them.
# MediaPipe places the knee landmark at the (forward-protruding) patella, so
# even perfectly straight legs read ~150-155°; truly bent legs read <140°.
MIN_KNEE_ANGLE_DEG = 145.0


class LandmarkMappingError(ValueError):
    """Raised when the observed pose cannot ground an honest measurement."""


def _mp_to_caesar_axes(p: np.ndarray) -> np.ndarray:
    """MediaPipe world frame -> CAESAR axes (still metres).

    mp: x right(=subject's left when facing the camera), y DOWN, z negative
    toward the camera (subject front). CAESAR: x LEFT+, y BACK+, z UP.
    Verified against the vendored demo cloud (Lt. Tragion x>0, Nuchale y>0,
    Sellion z high).
    """
    return np.array([p[0], p[2], -p[1]], dtype=np.float64)


def _unit(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    if n < 1e-9:
        raise LandmarkMappingError("degenerate limb direction (zero-length)")
    return v / n


def _perp(v: np.ndarray, up: np.ndarray) -> np.ndarray:
    w = np.cross(v, up)
    n = np.linalg.norm(w)
    if n < 1e-9:
        raise LandmarkMappingError("degenerate perpendicular direction")
    return w / n


def validate_pose(world_landmarks, visibilities=None) -> None:
    """Fail honestly (before any inference) if the photo is not a usable
    full-body pose: 33 finite landmarks, key joints visible, sane frame."""
    if world_landmarks is None or len(world_landmarks) != 33:
        raise LandmarkMappingError("pose detector returned no full-body landmarks")
    arr = np.asarray(world_landmarks, dtype=np.float64)
    if not np.isfinite(arr).all():
        raise LandmarkMappingError("pose landmarks contain non-finite values")
    if visibilities is not None:
        low = [k for k in REQUIRED_VISIBILITY
               if len(visibilities) > MP[k] and float(visibilities[MP[k]]) < MIN_VISIBILITY]
        if low:
            raise LandmarkMappingError(
                "not a full-body photo — poorly visible: " + ", ".join(low))


def build_caesar_cloud(world_landmarks: Sequence[Sequence[float]],
                       flip_x: bool = False) -> Dict[str, Tuple[float, float, float]]:
    """33 MediaPipe world landmarks (metres) -> 73 CAESAR landmarks (mm)."""
    mp_arr = np.asarray(world_landmarks, dtype=np.float64)
    if mp_arr.shape != (33, 3):
        raise LandmarkMappingError(f"expected 33x3 world landmarks, got {mp_arr.shape}")

    P = {name: _mp_to_caesar_axes(mp_arr[idx]) for name, idx in MP.items()}
    if flip_x:  # mirrored subject: flip lateral axis and swap left/right
        P = {name: np.array([-v[0], v[1], v[2]]) for name, v in P.items()}
        for a, b in (("left_ear", "right_ear"), ("left_shoulder", "right_shoulder"),
                     ("left_elbow", "right_elbow"), ("left_wrist", "right_wrist"),
                     ("left_hip", "right_hip"), ("left_knee", "right_knee"),
                     ("left_ankle", "right_ankle"), ("left_heel", "right_heel"),
                     ("left_foot_index", "right_foot_index"),
                     ("left_index", "right_index"), ("left_pinky", "right_pinky")):
            P[a], P[b] = P[b], P[a]

    up = np.array([0.0, 0.0, 1.0])
    fwd = np.array([0.0, -1.0, 0.0])
    lat_axis = np.array([1.0, 0.0, 0.0])  # +x = subject's left

    # ── observed frame ────────────────────────────────────────────────
    sh_mid_obs = (P["left_shoulder"] + P["right_shoulder"]) / 2.0
    hip_mid_obs = (P["left_hip"] + P["right_hip"]) / 2.0
    torso = float(np.linalg.norm(sh_mid_obs - hip_mid_obs))
    leg = float(np.linalg.norm(P["left_hip"] - P["left_ankle"]))
    mp_sh_w = float(np.linalg.norm(P["left_shoulder"] - P["right_shoulder"]))
    mp_hip_w = float(np.linalg.norm(P["left_hip"] - P["right_hip"]))
    if torso < 0.15 or leg < 0.25 or mp_sh_w < 0.10 or mp_hip_w < 0.06:
        raise LandmarkMappingError("implausible body frame (too small or partial)")

    # CAESAR-proportioned girdle widths from the subject's own torso length.
    sh_w = SHOULDER_W_FRAC * torso
    tr_w = TROCHANTER_W_FRAC * torso
    face_w = max(float(np.linalg.norm(P["left_ear"] - P["right_ear"])), 0.10)
    eye_mid = (P["left_eye_outer"] + P["right_eye_outer"]) / 2.0
    mouth_mid = (P["mouth_left"] + P["mouth_right"]) / 2.0
    ear_mid = (P["left_ear"] + P["right_ear"]) / 2.0

    # Widened girdle points: keep the OBSERVED joint position (which carries
    # the subject's real pose/rotation) and push it OUTWARD along the girdle
    # line so the surface landmarks sit at CAESAR proportions. The offset is
    # (CAESAR width − observed joint width)/2, so an observed pose that is
    # already at CAESAR width is left untouched.
    def widen(obs_l: np.ndarray, obs_r: np.ndarray, target_w: float):
        line = obs_r - obs_l
        cur_w = float(np.linalg.norm(line))
        if cur_w < 1e-6:
            raise LandmarkMappingError("degenerate girdle (joints coincide)")
        out = line / cur_w * ((target_w - cur_w) / 2.0)
        return obs_l - out, obs_r + out

    acr_l, acr_r = widen(P["left_shoulder"], P["right_shoulder"], sh_w)
    tro_l, tro_r = widen(P["left_hip"], P["right_hip"], tr_w)
    acromion = {"Lt.": acr_l, "Rt.": acr_r}
    trochanter = {"Lt.": tro_l, "Rt.": tro_r}
    sh_mid = (acromion["Lt."] + acromion["Rt."]) / 2.0
    hip_mid = (trochanter["Lt."] + trochanter["Rt."]) / 2.0

    cloud: Dict[str, np.ndarray] = {}

    def put(name: str, v: np.ndarray) -> None:
        cloud[name] = np.asarray(v, dtype=np.float64)

    def scaffold(anchor: np.ndarray, up_f: float, fwd_f: float, lat_f: float,
                 side_sign: float = 0.0) -> np.ndarray:
        """anchor + (up_f*up + fwd_f*fwd)*torso + lat_f*lateral*torso, where
        the lateral term is TOWARD the body midline for either side."""
        lateral = np.array([side_sign, 0.0, 0.0])  # +x = Lt
        inward = -side_sign * lat_f  # toward midline
        return anchor + (up_f * up + fwd_f * fwd) * torso + lateral * inward * torso

    # ── head ──────────────────────────────────────────────────────────
    put("Sellion", eye_mid + (HEAD["sellion_up"] * up + HEAD["sellion_fwd"] * fwd) * face_w)
    for side in ("Lt.", "Rt."):
        ear = P["left_ear"] if side == "Lt." else P["right_ear"]
        eye = P["left_eye_outer"] if side == "Lt." else P["right_eye_outer"]
        inward = -1.0 if side == "Lt." else +1.0
        put(f"{side} Tragion", ear)                                    # DIRECT
        put(f"{side} Infraorbitale", eye)                              # DIRECT
        put(f"{side} Gonion", ear
            + (HEAD["gonion_inward"] * inward * lat_axis + HEAD["gonion_fwd"] * fwd
               - HEAD["gonion_down"] * up) * face_w)
    put("Supramenton", mouth_mid - up * (HEAD["supramenton_down"] * face_w))

    # ── midline torso/pelvis (demo-calibrated fractions) ──────────────
    for name, (u, f) in MID_FROM_SHOULDER.items():
        put(name, scaffold(sh_mid, u, f, 0.0))
    for name, (u, f) in MID_FROM_HIP.items():
        put(name, scaffold(hip_mid, u, f, 0.0))

    # ── per-side torso scaffolds ──────────────────────────────────────
    for side in ("Lt.", "Rt."):
        s = 1.0 if side == "Lt." else -1.0
        for name, (u, f, inw) in FROM_ACROMION.items():
            put(f"{side} {name}", scaffold(acromion[side], u, f, inw, s))
        for name, (u, f, inw) in FROM_TROCHANTER.items():
            put(f"{side} {name}", scaffold(trochanter[side], u, f, inw, s))
        put(f"{side} Acromion", acromion[side])
        put(f"{side} Trochanterion", trochanter[side])

    # ── arms (observed joints + demo-scaled widths) ───────────────────
    for side, s_key, e_key, w_key, i_key, p_key, sgn in (
        ("Lt.", "left_shoulder", "left_elbow", "left_wrist", "left_index", "left_pinky", 1.0),
        ("Rt.", "right_shoulder", "right_elbow", "right_wrist", "right_index", "right_pinky", -1.0),
    ):
        sh, el, wr = P[s_key], P[e_key], P[w_key]
        elbow_w = LIMB_WIDTH["elbow"] * sh_w
        wrist_w = LIMB_WIDTH["wrist"] * sh_w
        upper_arm = _unit(el - sh)
        forearm = _unit(wr - el)
        arm_lat = _perp(upper_arm + forearm, up)
        if arm_lat[0] * sgn < 0:  # keep the lateral side OUTWARD on each side
            arm_lat = -arm_lat
        put(f"{side} Humeral Lateral Epicn", el + arm_lat * (elbow_w / 2))
        put(f"{side} Humeral Medial Epicn", el - arm_lat * (elbow_w / 2))
        # Olecranon: demo puts it ~16mm below-behind the elbow centre.
        put(f"{side} Olecranon", el - (0.016 * up + 0.016 * fwd) * torso)
        put(f"{side} Radiale", el + forearm * (0.5 * elbow_w))
        put(f"{side} Radial Styloid", wr + arm_lat * (wrist_w / 2))
        put(f"{side} Ulnar Styloid", wr - arm_lat * (wrist_w / 2))
        hand_dir = _unit(P[i_key] - wr)
        put(f"{side} Metacarpal Phal. II", P[i_key])                   # DIRECT
        put(f"{side} Metacarpal Phal. V", P[p_key])                    # DIRECT
        # Dactylion/Digit II: ~2 wrist-widths of finger beyond the knuckle
        # (demo: 112mm; the demo's own Digit II point is an anomaly 0.9m
        # below the knuckle — impossible anatomy, corrected here).
        put(f"{side} Dactylion", P[i_key] + hand_dir * (2.0 * wrist_w))
        put(f"{side} Digit II", P[i_key] + hand_dir * (2.2 * wrist_w))

    # ── legs / feet ───────────────────────────────────────────────────
    for side, h_key, k_key, a_key, c_key, f_key, sgn in (
        ("Lt.", "left_hip", "left_knee", "left_ankle", "left_heel", "left_foot_index", 1.0),
        ("Rt.", "right_hip", "right_knee", "right_ankle", "right_heel", "right_foot_index", -1.0),
    ):
        hip, knee, ankle, heel, foot = P[h_key], P[k_key], P[a_key], P[c_key], P[f_key]
        knee_w = LIMB_WIDTH["knee"] * tr_w
        ankle_w = LIMB_WIDTH["ankle"] * tr_w
        foot_w = LIMB_WIDTH["foot"] * tr_w
        thigh_dir = _unit(knee - hip)
        knee_lat = _perp(thigh_dir, up)
        if knee_lat[0] * sgn < 0:
            knee_lat = -knee_lat
        put(f"{side} Femoral Lateral Epicn", knee + knee_lat * (knee_w / 2))
        put(f"{side} Femoral Medial Epicn", knee - knee_lat * (knee_w / 2))
        # Knee crease: demo puts it 35mm behind, 8mm below the knee centre.
        put(f"{side} Knee Crease", knee - (0.015 * up + 0.063 * fwd) * torso)
        shank_dir = _unit(ankle - knee)
        ankle_lat = _perp(shank_dir, up)
        if ankle_lat[0] * sgn < 0:
            ankle_lat = -ankle_lat
        lat_mal = ankle + ankle_lat * (ankle_w / 2)
        med_mal = ankle - ankle_lat * (ankle_w / 2)
        put(f"{side} Lateral Malleolus", lat_mal)
        put(f"{side} Medial Malleolus", med_mal)
        # Sphyrion: 23mm below the medial malleolus (exact demo offset).
        put(f"{side} Sphyrion", med_mal - up * (0.28 * ankle_w))
        put(f"{side} Calcaneous, Post.", heel)                          # DIRECT
        foot_lat = _perp(_unit(foot - heel), up)
        if foot_lat[0] * sgn < 0:
            foot_lat = -foot_lat
        put(f"{side} Metatarsal Phal. I", foot - foot_lat * (foot_w / 2))
        put(f"{side} Metatarsal Phal. V", foot + foot_lat * (foot_w / 2))

    return {name: (round(float(v[0] * 1000.0), 3),
                   round(float(v[1] * 1000.0), 3),
                   round(float(v[2] * 1000.0), 3))
            for name, v in cloud.items()}


def direct_geometry_measurements(world_landmarks) -> Dict[str, float]:
    """Measurements that are PURE GEOMETRY on the observed landmarks — no
    model, no scaffold, no mirror. Reported with ``source: direct_geometry``."""
    mp_arr = np.asarray(world_landmarks, dtype=np.float64)
    P = {name: mp_arr[idx] for name, idx in MP.items()}
    out: Dict[str, float] = {}
    out["Arm Length (Shoulder to Elbow)"] = round(float(np.linalg.norm(
        P["left_shoulder"] - P["left_elbow"]) * 1000), 1)
    out["Arm Length (Shoulder to Wrist)"] = round(float(np.linalg.norm(
        P["left_shoulder"] - P["left_wrist"]) * 1000), 1)
    left_leg = float(np.linalg.norm(P["left_hip"] - P["left_ankle"]))
    right_leg = float(np.linalg.norm(P["right_hip"] - P["right_ankle"]))
    out["Inseam (Hip to Ankle)"] = round((left_leg + right_leg) / 2 * 1000, 1)
    ears = (P["left_ear"] + P["right_ear"]) / 2.0
    ear_w = float(np.linalg.norm(P["left_ear"] - P["right_ear"]))
    heels = np.minimum(P["left_heel"], P["right_heel"])
    # Crown ≈ half an ear-width above the ear line (verified on the vendored
    # CAESAR demo subject: ear_mid + 0.5*face_w ≈ stature − heel span).
    stature = float(np.linalg.norm(ears + np.array([0, -0.5 * ear_w, 0]) - heels))
    out["Stature"] = round(stature * 1000, 1)
    return out


def pose_quality(world_landmarks) -> Dict[str, float]:
    """Quantify how far the observed pose is from the CAESAR A-pose envelope.
    The worker uses these metrics to refuse out-of-envelope photos honestly
    (HTTP 422 with guidance) instead of returning garbage measurements."""
    mp_arr = np.asarray(world_landmarks, dtype=np.float64)
    if mp_arr.shape != (33, 3):
        raise LandmarkMappingError(f"expected 33x3 world landmarks, got {mp_arr.shape}")
    P = {name: mp_arr[idx] for name, idx in MP.items()}

    def ang(a, b, c):  # angle at b (degrees)
        v1, v2 = a - b, c - b
        cos = float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-12))
        return float(np.degrees(np.arccos(np.clip(cos, -1, 1))))

    # Shoulder-line yaw: depth difference between shoulders vs their width.
    sh_d = P["left_shoulder"] - P["right_shoulder"]
    width = float(np.linalg.norm(sh_d[:2]))
    yaw = float(np.degrees(np.arctan2(abs(sh_d[2]), width + 1e-9)))
    tilt = float(np.degrees(np.arctan2(abs(P["left_shoulder"][1] - P["right_shoulder"][1]),
                                       abs(P["left_shoulder"][0] - P["right_shoulder"][0]) + 1e-9)))
    # Bent arms (e.g. hands on hips): shoulder→elbow→wrist path vs chord.
    # Straight arm → 0; elbow bent 90° → ~0.41.
    arm_ratios = []
    for s, e, w in (("left_shoulder", "left_elbow", "left_wrist"),
                    ("right_shoulder", "right_elbow", "right_wrist")):
        chord = float(np.linalg.norm(P[w] - P[s])) + 1e-9
        path = float(np.linalg.norm(P[w] - P[e]) + np.linalg.norm(P[e] - P[s]))
        arm_ratios.append(max(0.0, path / chord - 1.0))
    legs = []
    for h, k, a in (("left_hip", "left_knee", "left_ankle"),
                    ("right_hip", "right_knee", "right_ankle")):
        legs.append(ang(P[h], P[k], P[a]))
    return {
        "yaw_deg": round(yaw, 1),
        "shoulder_tilt_deg": round(tilt, 1),
        "arm_bend_ratio": round(max(arm_ratios), 3),
        "knee_angle_deg": round(min(legs), 1),
    }


def check_pose_envelope(quality: Dict[str, float]) -> None:
    """Raise LandmarkMappingError with actionable guidance when the pose is
    outside the A-pose envelope the measurements are valid for."""
    problems = []
    if quality["yaw_deg"] > MAX_YAW_DEG:
        problems.append(f"body turned {quality['yaw_deg']:.0f}° from the camera — please face the camera directly")
    if quality["shoulder_tilt_deg"] > MAX_SHOULDER_TILT_DEG:
        problems.append("shoulders are tilted — please stand level")
    if quality["arm_bend_ratio"] > MAX_ARM_BEND_RATIO:
        problems.append("arms appear bent — let them hang relaxed, slightly away from the body")
    if quality["knee_angle_deg"] < MIN_KNEE_ANGLE_DEG:
        problems.append("legs appear bent — please stand straight")
    if problems:
        raise LandmarkMappingError("; ".join(problems))


def plausibility_check(measurements_mm: Dict[str, float]) -> List[str]:
    """Honesty gate: anatomically impossible values are reported and the
    worker refuses to ship a measurement set that fails these bounds."""
    bounds = {
        "Ankle Circumference": (150, 400),
        "Arm Length (Shoulder to Elbow)": (200, 500),
        "Arm Length (Shoulder to Wrist)": (400, 750),
        "Arm Length (Spine to Wrist)": (550, 950),
        "Chest Circumference": (650, 1600),
        "Crotch Height": (500, 1100),
        "Head Circumference": (450, 700),
        "Hip Circ Max Height": (600, 1250),
        "Hip Circumference, Maximum": (700, 1700),
        "Neck Base Circumference": (280, 600),
        "Stature": (1300, 2200),
        "Inseam (Hip to Ankle)": (550, 1000),
    }
    bad = []
    for name, v in measurements_mm.items():
        # measurement names come in two forms: model outputs carry an explicit
        # "(mm)" suffix, direct-geometry outputs don't — normalize before
        # matching (a silent skip would be a plausibility hole).
        key = name.replace(" (mm)", "")
        if key not in bounds:
            continue
        lo, hi = bounds[key]
        if v is not None and not (lo <= v <= hi):
            bad.append(name)
    return bad
