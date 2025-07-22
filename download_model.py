from huggingface_hub import hf_hub_download

# Achte darauf, den richtigen Dateinamen anzugeben, hier beispielhaft "yolov5n.pt"
model_path = hf_hub_download(repo_id="fcakyon/yolov5n-v7.0", filename="yolov5n.pt")
print("Modell gespeichert unter:", model_path)
