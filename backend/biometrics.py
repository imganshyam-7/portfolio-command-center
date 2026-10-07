import os
import urllib.request
import base64
import cv2
import numpy as np

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(BASE_DIR, "data", "models")
os.makedirs(MODELS_DIR, exist_ok=True)

YUNET_PATH = os.path.join(MODELS_DIR, "face_detection_yunet_2023mar.onnx")
SFACE_PATH = os.path.join(MODELS_DIR, "face_recognition_sface_2021dec.onnx")

# Direct links to GitHub LFS media CDN to guarantee binary ONNX weights (not text pointers)
YUNET_URL = "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
SFACE_URL = "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx"

def ensure_models():
    """Ensure genuine ONNX binary weights exist on disk (> 100 KB to avoid Git LFS text pointers)."""
    if not os.path.exists(YUNET_PATH) or os.path.getsize(YUNET_PATH) < 100000:
        print("[BIOMETRICS] Fetching YuNet binary weights...")
        urllib.request.urlretrieve(YUNET_URL, YUNET_PATH)
        
    if not os.path.exists(SFACE_PATH) or os.path.getsize(SFACE_PATH) < 10000000:
        print("[BIOMETRICS] Fetching SFace binary weights...")
        urllib.request.urlretrieve(SFACE_URL, SFACE_PATH)

def decode_base64_image(base64_str: str) -> np.ndarray:
    if "," in base64_str:
        base64_str = base64_str.split(",", 1)[1]
    image_bytes = base64.b64decode(base64_str)
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Invalid camera frame data received.")
    return img

def extract_face_embedding(base64_image: str) -> list:
    """Detects facial boundaries, crops and aligns, then extracts a 128-dimensional embedding vector."""
    ensure_models()
    img = decode_base64_image(base64_image)
    h, w, _ = img.shape

    detector = cv2.FaceDetectorYN.create(YUNET_PATH, "", (w, h), score_threshold=0.6)
    detector.setInputSize((w, h))
    _, faces = detector.detect(img)

    if faces is None or len(faces) == 0:
        raise ValueError("No face detected in video frame. Ensure adequate lighting and look directly into the camera.")

    recognizer = cv2.FaceRecognizerSF.create(SFACE_PATH, "")
    aligned = recognizer.alignCrop(img, faces[0])
    embedding = recognizer.feature(aligned)
    return embedding[0].tolist()

def verify_faces(enrolled_embedding: list, probe_base64_image: str, threshold: float = 0.363) -> bool:
    """Compares the live probe frame against the enrolled embedding using SFace Cosine Similarity."""
    ensure_models()
    probe_emb = extract_face_embedding(probe_base64_image)
    
    v1 = np.array(enrolled_embedding, dtype=np.float32).reshape(1, -1)
    v2 = np.array(probe_emb, dtype=np.float32).reshape(1, -1)

    recognizer = cv2.FaceRecognizerSF.create(SFACE_PATH, "")
    score = recognizer.match(v1, v2, cv2.FaceRecognizerSF_FR_COSINE)
    return bool(score >= threshold)