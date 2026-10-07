#!/usr/bin/env bash
set -o errexit

echo "==> Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "==> Ensuring ONNX models directory exists..."
mkdir -p data/models

echo "==> Fetching YuNet detector weights..."
if [ ! -f data/models/face_detection_yunet_2023mar.onnx ] || [ $(stat -c%s "data/models/face_detection_yunet_2023mar.onnx" 2>/dev/null || stat -f%z "data/models/face_detection_yunet_2023mar.onnx") -lt 10000 ]; then
  curl -L -o data/models/face_detection_yunet_2023mar.onnx "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
fi

echo "==> Fetching SFace recognizer weights..."
if [ ! -f data/models/face_recognition_sface_2021dec.onnx ] || [ $(stat -c%s "data/models/face_recognition_sface_2021dec.onnx" 2>/dev/null || stat -f%z "data/models/face_recognition_sface_2021dec.onnx") -lt 10000000 ]; then
  curl -L -o data/models/face_recognition_sface_2021dec.onnx "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx"
fi

echo "==> Build completed successfully."
