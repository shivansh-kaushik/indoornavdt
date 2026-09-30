"""
crowd_detection.py  —  Phase 2: Person counting from CCTV camera feeds

Uses YOLOv8 (ultralytics) for real-time person detection.
Supports: image files, video files, RTSP streams, webcam index.

Falls back to a simple OpenCV HOG person detector if ultralytics is not
installed.

Usage
-----
    # Single image / frame
    count, frame = detect_crowd_in_frame("frame.jpg")

    # Continuous video / stream
    run_stream_detector(
        source="rtsp://192.168.1.10/cam1",
        camera_id="CAM_01",
        graph=G,
        camera_node_map=camera_node_map,
    )

    # Simulated mode (for testing without real cameras)
    counts = simulate_crowd_counts(camera_node_map, max_per_cam=8)
"""

from __future__ import annotations

import logging
import random
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Backend selection
# ─────────────────────────────────────────────────────────────────────────────

def _get_yolo_model(model_name: str = "yolov8n.pt"):
    """Load YOLOv8 nano model. Downloads automatically on first use."""
    try:
        from ultralytics import YOLO  # noqa: PLC0415
        logger.info("Loading YOLOv8 model: %s", model_name)
        return YOLO(model_name)
    except ImportError:
        logger.warning("ultralytics not installed — pip install ultralytics")
        return None


def _hog_detector():
    """OpenCV HOG person detector (fallback, no GPU, less accurate)."""
    try:
        import cv2  # noqa: PLC0415
        hog = cv2.HOGDescriptor()
        hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        return hog
    except ImportError:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Per-frame detection
# ─────────────────────────────────────────────────────────────────────────────

def detect_crowd_in_frame(
    source,                      # path str | np.ndarray (BGR)
    model=None,                  # YOLO model or None -> auto-select
    conf_threshold: float = 0.4,
    draw: bool = False,
) -> Tuple[int, Optional[np.ndarray]]:
    """
    Detect and count persons in a single image/frame.

    Parameters
    ----------
    source          : file path (str/Path) or BGR numpy array
    model           : pre-loaded YOLO model (reuse for speed); None = auto
    conf_threshold  : minimum confidence to count as a person
    draw            : if True, return annotated frame; else return None

    Returns
    -------
    (person_count, annotated_frame_or_None)
    """
    try:
        import cv2  # noqa: PLC0415
    except ImportError:
        logger.error("OpenCV not installed: pip install opencv-python")
        return 0, None

    # Load image
    if isinstance(source, (str, Path)):
        frame = cv2.imread(str(source))
        if frame is None:
            logger.error("Cannot read image: %s", source)
            return 0, None
    elif isinstance(source, np.ndarray):
        frame = source
    else:
        logger.error("Unsupported source type: %s", type(source))
        return 0, None

    # Try YOLO first
    if model is None:
        model = _get_yolo_model()

    person_count = 0
    annotated = frame.copy() if draw else None

    if model is not None:
        # YOLOv8 detection — class 0 = person in COCO
        results = model.predict(frame, classes=[0], conf=conf_threshold, verbose=False)
        for result in results:
            person_count += len(result.boxes)
            if draw:
                annotated = result.plot()
    else:
        # HOG fallback
        hog = _hog_detector()
        if hog:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            rects, _ = hog.detectMultiScale(
                gray, winStride=(8, 8), padding=(4, 4), scale=1.05
            )
            person_count = len(rects)
            if draw and annotated is not None:
                for (x, y, w, h) in rects:
                    cv2.rectangle(annotated, (x, y), (x + w, y + h), (0, 200, 0), 2)
        else:
            logger.warning("No detection backend available")

    return person_count, annotated


# ─────────────────────────────────────────────────────────────────────────────
# Stream / video detector
# ─────────────────────────────────────────────────────────────────────────────

def run_stream_detector(
    source: str | int,                      # RTSP URL | video path | webcam index
    camera_id: str,
    camera_node_map: Dict[str, List[str]],
    on_count_update: Optional[Callable[[str, int], None]] = None,
    model_name: str = "yolov8n.pt",
    conf_threshold: float = 0.4,
    frame_skip: int = 5,                    # process every Nth frame
    display: bool = False,
) -> None:
    """
    Continuously read frames from a camera source, count persons,
    and call on_count_update(camera_id, count) for each processed frame.

    Parameters
    ----------
    source          : RTSP URL ("rtsp://..."), video file path, or webcam int
    camera_id       : ID to report counts under (e.g. "CAM_01")
    camera_node_map : {camera_id -> [node_guids]} for logging
    on_count_update : callback(camera_id, count) — use to update nav graph
    frame_skip      : only run detector every N frames (saves CPU)
    display         : show annotated frames in a window
    """
    try:
        import cv2  # noqa: PLC0415
    except ImportError:
        logger.error("OpenCV required: pip install opencv-python")
        return

    model = _get_yolo_model(model_name)
    cap   = cv2.VideoCapture(source)

    if not cap.isOpened():
        logger.error("Cannot open source: %s", source)
        return

    logger.info("Stream detector running: %s (camera %s)", source, camera_id)
    frame_idx  = 0
    last_count = 0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                logger.info("Stream ended: %s", source)
                break

            frame_idx += 1
            if frame_idx % frame_skip != 0:
                continue

            count, annotated = detect_crowd_in_frame(
                frame, model=model, conf_threshold=conf_threshold, draw=display
            )

            if count != last_count:
                logger.info("Camera %s: %d persons detected", camera_id, count)
                if on_count_update:
                    on_count_update(camera_id, count)
                last_count = count

            if display and annotated is not None:
                cv2.imshow(f"IndoorNav — {camera_id}", annotated)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

    except KeyboardInterrupt:
        logger.info("Stream detector stopped by user")
    finally:
        cap.release()
        if display:
            cv2.destroyAllWindows()


# ─────────────────────────────────────────────────────────────────────────────
# Simulation mode (for testing without real cameras)
# ─────────────────────────────────────────────────────────────────────────────

def simulate_crowd_counts(
    camera_node_map: Dict[str, List[str]],
    max_per_cam: int = 8,
    seed: Optional[int] = None,
) -> Dict[str, int]:
    """
    Generate random crowd counts per camera for testing the navigation
    crowd-avoidance logic without real CCTV feeds.

    Returns
    -------
    {camera_id -> person_count}
    """
    if seed is not None:
        random.seed(seed)

    counts = {
        cam_id: random.randint(0, max_per_cam)
        for cam_id in camera_node_map
    }
    logger.info("Simulated crowd counts: %s", counts)
    return counts


# ─────────────────────────────────────────────────────────────────────────────
# Convenience: run detection on a folder of snapshot images
# ─────────────────────────────────────────────────────────────────────────────

def batch_detect_snapshots(
    image_folder: str | Path,
    camera_id_prefix: str = "CAM",
) -> Dict[str, int]:
    """
    Run crowd detection on all .jpg/.png images in a folder.
    Filenames are expected to be camera IDs (e.g. CAM_01.jpg).

    Returns
    -------
    {camera_id -> person_count}
    """
    folder = Path(image_folder)
    counts: Dict[str, int] = {}
    model   = _get_yolo_model()

    for img_path in sorted(folder.glob("*.jpg")) + sorted(folder.glob("*.png")):
        cam_id = img_path.stem
        count, _ = detect_crowd_in_frame(img_path, model=model)
        counts[cam_id] = count
        logger.info("%s: %d persons", cam_id, count)

    return counts
