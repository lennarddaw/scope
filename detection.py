import cv2
import torch
import numpy as np
from transformers import DetrImageProcessor, DetrForObjectDetection
from transformers import CLIPProcessor, CLIPModel
import requests
import threading
import queue
import time

stream_url = 'http://10.5.13.123/stream'

# Performance-Einstellungen
FRAME_SKIP = 2           # Jedes 2. Frame
DETR_INTERVAL = 4
CLIP_INTERVAL = 4
RESIZE_WIDTH = 640
CONFIDENCE_THRESHOLD = 0.75  # Höherer Threshold für weniger False Positives


print("Lade DETR Modell...")
processor = DetrImageProcessor.from_pretrained("facebook/detr-resnet-50")
model = DetrForObjectDetection.from_pretrained("facebook/detr-resnet-50")


print("Lade CLIP Modell...")
clip_model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
clip_processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")


COCO_CLASSES = [
    'N/A', 'person',
]

clip_labels = [
    "a LEGO minifigure",
    "a LEGO minifigure waving", 
    "a LEGO minifigure with weapon",
    "a LEGO minifigure with helmet",
    "no LEGO minifigure"
]


device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model.to(device)
clip_model.to(device)


if device.type == 'cuda':
    model.half()
    clip_model.half()
    torch.backends.cudnn.benchmark = True

print(f"Using device: {device}")
print("Models loaded and optimized!")


frame_queue = queue.Queue(maxsize=3)
current_detections = []
current_clip_result = ""
frame_count = 0

def resize_frame(frame, width=RESIZE_WIDTH):
    """Frame intelligent resizen unter Beibehaltung des Seitenverhältnisses"""
    height, orig_width = frame.shape[:2]
    if orig_width <= width:
        return frame
    
    ratio = width / orig_width
    new_height = int(height * ratio)
    return cv2.resize(frame, (width, new_height))

def preprocess_frame(frame):
    """Frame für bessere Performance vorverarbeiten"""
    frame = resize_frame(frame)
    
    
    return frame

def detr_worker():
    """Worker Thread für DETR Objekterkennung"""
    global current_detections
    
    while True:
        try:
            if not frame_queue.empty():
                frame = frame_queue.get_nowait()
                
                # DETR-Analyse
                with torch.no_grad():
                    inputs = processor(images=frame, return_tensors="pt").to(device)
                    if device.type == 'cuda':
                        inputs = {k: v.half() if v.dtype == torch.float32 else v for k, v in inputs.items()}
                    
                    outputs = model(**inputs)
                    target_sizes = torch.tensor([frame.shape[:2]])
                    results = processor.post_process_object_detection(outputs, target_sizes=target_sizes)[0]
                
                
                detections = []
                for score, label, box in zip(results["scores"], results["labels"], results["boxes"]):
                    if score > CONFIDENCE_THRESHOLD:
                        box = box.int().cpu().numpy()
                        detections.append({
                            'box': box,
                            'label': COCO_CLASSES[label],
                            'score': float(score)
                        })
                
                current_detections = detections
                
        except Exception as e:
            print(f"[DETR Worker] Error: {e}")
        
        time.sleep(0.01)

def clip_worker():
    """Worker Thread für CLIP Analyse"""
    global current_clip_result
    
    while True:
        try:
            if not frame_queue.empty():
                frame = frame_queue.get_nowait()
                
                # CLIP-Analyse
                with torch.no_grad():
                    clip_inputs = clip_processor(
                        text=clip_labels, 
                        images=frame, 
                        return_tensors="pt", 
                        padding=True
                    ).to(device)
                    
                    if device.type == 'cuda':
                        clip_inputs = {k: v.half() if v.dtype == torch.float32 else v for k, v in clip_inputs.items()}
                    
                    clip_outputs = clip_model(**clip_inputs)
                    probs = clip_outputs.logits_per_image.softmax(dim=1).cpu().numpy()[0]
                
                
                top_idx = int(np.argmax(probs))
                top_prob = probs[top_idx]
                
                if top_prob > 0.4 and "no LEGO" not in clip_labels[top_idx]:
                    current_clip_result = f"{clip_labels[top_idx]} ({top_prob:.2f})"
                else:
                    current_clip_result = ""
                
        except Exception as e:
            print(f"[CLIP Worker] Error: {e}")
        
        time.sleep(0.05)  # Längere Pause für CLIP

detr_thread = threading.Thread(target=detr_worker, daemon=True)
clip_thread = threading.Thread(target=clip_worker, daemon=True)

print("Starte Background-Threads...")
detr_thread.start()
clip_thread.start()

# Hauptloop
try:
    stream = requests.get(stream_url, stream=True, timeout=5)
    byte_buffer = bytes()
    
    print("Verbunden mit ESP32-CAM. Drücke 'q' zum Beenden...")
    fps_start_time = time.time()
    fps_frame_count = 0
    
    for chunk in stream.iter_content(chunk_size=1024):
        byte_buffer += chunk
        a = byte_buffer.find(b'\xff\xd8')
        b = byte_buffer.find(b'\xff\xd9')
        
        if a != -1 and b != -1:
            jpg = byte_buffer[a:b+2:]
            byte_buffer = byte_buffer[b+2:]
            frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)

            if frame is None:
                continue

            frame_count += 1
            fps_frame_count += 1

            
            if frame_count % FRAME_SKIP != 0:
                continue

            
            processed_frame = preprocess_frame(frame)
            
            
            if frame_count % DETR_INTERVAL == 0:
                if not frame_queue.full():
                    frame_queue.put_nowait(processed_frame.copy())
            
            
            display_frame = processed_frame.copy()
            
            
            for detection in current_detections:
                box = detection['box']
                xmin, ymin, xmax, ymax = box
                label_text = f"{detection['label']}: {detection['score']:.2f}"
                
                cv2.rectangle(display_frame, (xmin, ymin), (xmax, ymax), (0, 255, 0), 2)
                cv2.putText(display_frame, label_text, (xmin, ymin-5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

            # CLIP Ergebnis anzeigen
            if current_clip_result:
                cv2.putText(display_frame, f"CLIP: {current_clip_result}", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

            # FPS berechnen und anzeigen
            elapsed_time = time.time() - fps_start_time
            if elapsed_time >= 1.0:
                fps = fps_frame_count / elapsed_time
                fps_start_time = time.time()
                fps_frame_count = 0
            else:
                fps = 0

            if fps > 0:
                cv2.putText(display_frame, f"FPS: {fps:.1f}", (10, display_frame.shape[0] - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

            
            cv2.imshow('Optimized DETR + CLIP Detection', display_frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

except Exception as e:
    print(f"Fehler: {e}")
finally:
    cv2.destroyAllWindows()
    print("Anwendung beendet.")