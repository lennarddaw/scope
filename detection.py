import cv2
import torch
import numpy as np
from transformers import DetrImageProcessor, DetrForObjectDetection
import requests

# ESP32-CAM URL
stream_url = 'http://192.168.2.197/stream'

# Modell laden (DETR)
processor = DetrImageProcessor.from_pretrained("facebook/detr-resnet-50")
model = DetrForObjectDetection.from_pretrained("facebook/detr-resnet-50")



# COCO Labels
COCO_CLASSES = [
    'N/A', 'person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train', 
    'truck', 'boat', 'traffic light', 'fire hydrant', 'N/A', 'stop sign', 
    'parking meter', 'bench', 'bird', 'cat', 'dog', 'horse', 'sheep', 'cow', 
    'elephant', 'bear', 'zebra', 'giraffe', 'N/A', 'backpack', 'umbrella', 
    'N/A', 'N/A', 'handbag', 'tie', 'suitcase', 'frisbee', 'skis', 'snowboard', 
    'sports ball', 'kite', 'baseball bat', 'baseball glove', 'skateboard', 
    'surfboard', 'tennis racket', 'bottle', 'N/A', 'wine glass', 'cup', 'fork', 
    'knife', 'spoon', 'bowl', 'banana', 'apple', 'sandwich', 'orange', 
    'broccoli', 'carrot', 'hot dog', 'pizza', 'donut', 'cake', 'chair', 'couch', 
    'potted plant', 'bed', 'N/A', 'dining table', 'N/A', 'N/A', 'toilet', 
    'N/A', 'tv', 'laptop', 'mouse', 'remote', 'keyboard', 'cell phone', 
    'microwave', 'oven', 'toaster', 'sink', 'refrigerator', 'N/A', 'book', 
    'clock', 'vase', 'scissors', 'teddy bear', 'hair drier', 'toothbrush'
]

# GPU oder CPU?
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model.to(device)

# Robustes Abgreifen des ESP32-CAM MJPEG-Streams
stream = requests.get(stream_url, stream=True)
byte_buffer = bytes()

for chunk in stream.iter_content(chunk_size=1024):
    byte_buffer += chunk
    a = byte_buffer.find(b'\xff\xd8')  # JPEG-Start
    b = byte_buffer.find(b'\xff\xd9')  # JPEG-Ende
    if a != -1 and b != -1:
        jpg = byte_buffer[a:b+2]
        byte_buffer = byte_buffer[b+2:]
        frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)

        # Prüfen ob das Frame korrekt ist
        if frame is None:
            continue

        # DETR-Erkennung durchführen
        inputs = processor(images=frame, return_tensors="pt").to(device)
        outputs = model(**inputs)

        target_sizes = torch.tensor([frame.shape[:2]])
        results = processor.post_process_object_detection(outputs, target_sizes=target_sizes)[0]

        confidence_threshold = 0.7
        for score, label, box in zip(results["scores"], results["labels"], results["boxes"]):
            if score > confidence_threshold:
                box = box.int().cpu().numpy()
                xmin, ymin, xmax, ymax = box
                label_text = f"{COCO_CLASSES[label]}: {score:.2f}"
                
                # Box und Label zeichnen
                cv2.rectangle(frame, (xmin, ymin), (xmax, ymax), (0,255,0), 2)
                cv2.putText(frame, label_text, (xmin, ymin-5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,0), 2)

        # Frame mit Erkennung anzeigen
        cv2.imshow('DETR Object Detection - ESP32 CAM', frame)

        # 'q' drücken zum Beenden
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

cv2.destroyAllWindows()
