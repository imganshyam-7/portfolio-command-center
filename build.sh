#!/usr/bin/env bash
set -o errexit

echo "==> Upgrading pip and installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "==> Build completed successfully."
