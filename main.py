import os
import cv2
from tqdm import tqdm
from google.cloud import vision
import pyautogui

# Set your Google Cloud Vision API credentials
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = r"C:\Users\liams\Downloads\gocr_key.json"

def load_vision_client():
    return vision.ImageAnnotatorClient()

def extract_text_from_image(image_bytes, client):
    image = vision.Image(content=image_bytes)
    response = client.text_detection(image=image)
    texts = response.text_annotations
    if texts:
        return texts[0].description.strip()
    return ""

import pyautogui

def select_roi_with_mouse(frame, label="Select ROI"):
    # Get screen resolution dynamically
    screen_width, screen_height = pyautogui.size()
    frame_height, frame_width = frame.shape[:2]

    # Only scale down if the frame is bigger than the screen
    scale_x = screen_width / frame_width
    scale_y = screen_height / frame_height
    scale = min(scale_x, scale_y, 1.0)  # Only scale if needed

    if scale < 1.0:
        resized_frame = cv2.resize(frame, (int(frame_width * scale), int(frame_height * scale)))
    else:
        resized_frame = frame.copy()

    cv2.namedWindow(label, cv2.WINDOW_NORMAL)  # Make window resizable
    roi_resized = cv2.selectROI(label, resized_frame, fromCenter=False, showCrosshair=True)
    cv2.destroyWindow(label)

    # Map ROI back to original resolution
    if scale < 1.0:
        x, y, w, h = [int(coord / scale) for coord in roi_resized]
    else:
        x, y, w, h = roi_resized

    return (x, y, w, h)

def analyze_video_with_dual_rois(video_path, roi1, roi2):
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    step = 0.5  # seconds
    interval_frames = int(step * fps)

    x1, y1, w1, h1 = roi1
    x2, y2, w2, h2 = roi2
    client = load_vision_client()

    results1 = []
    results2 = []
    current_frame = 0

    progress_bar = tqdm(total=total_frames, desc="Analyzing frames", unit="frame")

    while current_frame < total_frames:
        cap.set(cv2.CAP_PROP_POS_FRAMES, current_frame)
        success, frame = cap.read()
        if not success:
            break

        timestamp = round(current_frame / fps, 1)

        # ROI 1
        roi_img1 = frame[y1:y1+h1, x1:x1+w1]
        _, encoded1 = cv2.imencode('.jpg', roi_img1)
        text1 = extract_text_from_image(encoded1.tobytes(), client)
        if text1:
            results1.append(f"{timestamp}: {text1}")

        # ROI 2
        roi_img2 = frame[y2:y2+h2, x2:x2+w2]
        _, encoded2 = cv2.imencode('.jpg', roi_img2)
        text2 = extract_text_from_image(encoded2.tobytes(), client)
        if text2:
            results2.append(f"{timestamp}: {text2}")

        current_frame += interval_frames
        progress_bar.update(interval_frames)

    cap.release()
    progress_bar.close()

    base = os.path.splitext(video_path)[0]
    out1 = base + "_roi1_output.txt"
    out2 = base + "_roi2_output.txt"

    with open(out1, 'w', encoding='utf-8') as f1:
        f1.writelines(line + '\n' for line in results1)

    with open(out2, 'w', encoding='utf-8') as f2:
        f2.writelines(line + '\n' for line in results2)

    print(f"\n✅ Text extraction complete.\nSaved to:\n- {out1}\n- {out2}")

if __name__ == "__main__":
    video_file = input("Enter the video filename (e.g., 'video.mp4'): ").strip()
    if not os.path.exists(video_file):
        print("❌ Video not found.")
        exit()

    cap = cv2.VideoCapture(video_file)
    success, frame = cap.read()
    cap.release()

    if not success:
        print("❌ Failed to read video.")
        exit()

    roi1 = select_roi_with_mouse(frame, "ROI 1")
    roi2 = select_roi_with_mouse(frame, "ROI 2")
    analyze_video_with_dual_rois(video_file, roi1, roi2)
