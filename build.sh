#!/usr/bin/env bash
set -o errexit

echo "==> Upgrading pip and installing production dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "==> Ensuring data/models directory exists..."
mkdir -p data/models

echo "==> Checking YuNet weights..."
if [ ! -f data/models/face_detection_yunet_2023mar.onnx ] || [ $(stat -c%s "data/models/face_detection_yunet_2023mar.onnx" 2>/dev/null || stat -f%z "data/models/face_detection_yunet_2023mar.onnx") -lt 100000 ]; then
  echo "==> Downloading YuNet binary..."
  curl -L -o data/models/face_detection_yunet_2023mar.onnx "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
fi

echo "==> Checking SFace weights..."
if [ ! -f data/models/face_recognition_sface_2021dec.onnx ] || [ $(stat -c%s "data/models/face_recognition_sface_2021dec.onnx" 2>/dev/null || stat -f%z "data/models/face_recognition_sface_2021dec.onnx") -lt 10000000 ]; then
  echo "==> Downloading SFace binary (~37 MB)..."
  curl -L -o data/models/face_recognition_sface_2021dec.onnx "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx"
fi

echo "==> Production build verification successful."