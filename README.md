# 🧠 ESP32-CAM Object Detection with Ultralytics

This project combines an **ESP32-CAM** with modern **AI-based object detection models** (e.g., YOLOv8 by [Ultralytics](https://github.com/ultralytics/ultralytics)). It streams live images from the ESP32-CAM and performs real-time object detection using pre-trained models.

---

## 🚀 Features

- Live MJPEG stream from ESP32-CAM
- Real-time object detection with YOLOv8 or other Ultralytics models
- Bounding box rendering using OpenCV
- Offline inference with locally stored models
- Modular separation between Arduino and Python logic

---

## 🔧 Requirements

### 🔌 Hardware

- ESP32-CAM module
- USB-to-Serial adapter
- 5V power supply (e.g., power bank)

### 🧪 Software

- Arduino IDE
- Python 3.9+
- Required Python packages (see below)

---

## 🛠️ Setup Guide

### 1. Upload ESP32 Sketch

- Open `detection/detection.ino` in Arduino IDE
- Select board: `AI Thinker ESP32-CAM`
- Upload the sketch to the board
- Open Serial Monitor to obtain the ESP32 IP (e.g., `http://192.168.2.xxx`)

### 2. Set Up Python Environment

```bash
pip install -r ultralytics-main/requirements.txt
Alternatively:

bash
Kopieren
Bearbeiten
pip install ultralytics opencv-python requests
3. Download Pretrained Model
bash
Kopieren
Bearbeiten
python download_model.py
4. Start Object Detection
bash
Kopieren
Bearbeiten
python detection.py
📷 Example Output
plaintext
Kopieren
Bearbeiten
[✓] ESP32-CAM stream connected!
[✓] YOLOv8 model loaded.
[🧠] Detected: person (87%), bottle (54%), chair (60%)
