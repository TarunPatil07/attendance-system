import base64
from typing import List, Tuple

import cv2
import numpy as np
from insightface.app import FaceAnalysis


class FaceRecognitionService:
    """RetinaFace detection + ArcFace embeddings via insightface FaceAnalysis."""

    def __init__(self) -> None:
        # CPU-only by default (ctx_id=-1). Adjust det_size for speed vs accuracy.
        self.app = FaceAnalysis(name="buffalo_l")
        self.app.prepare(ctx_id=-1, det_size=(640, 640))

    @staticmethod
    def _image_from_bytes(image_bytes: bytes) -> np.ndarray:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Could not decode image bytes")
        return img

    def _extract_embeddings(self, img: np.ndarray) -> List[np.ndarray]:
        faces = self.app.get(img)
        embeddings: List[np.ndarray] = []
        for face in faces:
            emb = getattr(face, "normed_embedding", None)
            if emb is None:
                emb = getattr(face, "embedding", None)
            if emb is None:
                continue
            embeddings.append(np.asarray(emb, dtype=np.float32))
        return embeddings

    def embeddings_from_bytes(self, image_bytes: bytes) -> List[np.ndarray]:
        img = self._image_from_bytes(image_bytes)
        return self._extract_embeddings(img)

    def embeddings_from_base64(self, image_data: str) -> Tuple[bytes, List[np.ndarray]]:
        """Accepts data URL or raw base64 string. Returns original bytes + embeddings."""
        if "," in image_data:
            image_data = image_data.split(",", 1)[1]
        image_bytes = base64.b64decode(image_data)
        embeddings = self.embeddings_from_bytes(image_bytes)
        return image_bytes, embeddings


def serialize_embedding(vec: np.ndarray) -> str:
    """Convert embedding vector to a comma-separated string for DB storage."""
    return ",".join(str(float(x)) for x in vec.flatten())


def deserialize_embedding(data: str) -> np.ndarray:
    """Convert comma-separated string back to numpy vector."""
    if not data:
        return np.zeros((512,), dtype=np.float32)
    arr = np.fromstring(data, sep=",", dtype=np.float32)
    return arr


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two embedding vectors."""
    if a.size == 0 or b.size == 0:
        return -1.0
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return -1.0
    return float(np.dot(a, b) / denom)
