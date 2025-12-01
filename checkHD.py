import os
import subprocess

# Thư mục chứa video
video_dir = r"C:\Users\Admin\Downloads\temp1\movie"

# Ngưỡng HD
HD_WIDTH = 1280
HD_HEIGHT = 720

for filename in os.listdir(video_dir):
    if filename.lower().endswith((".mjpeg", ".mjpg")):
        filepath = os.path.join(video_dir, filename)
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate,codec_name",
            "-of", "default=noprint_wrappers=1:nokey=0",
            filepath
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            info = result.stdout
            # Tách width và height
            width = height = 0
            for line in info.splitlines():
                if line.startswith("width="):
                    width = int(line.split("=")[1])
                elif line.startswith("height="):
                    height = int(line.split("=")[1])
            if width >= HD_WIDTH and height >= HD_HEIGHT:
                print(f"HD Video: {filename} ({width}x{height})")
        except subprocess.CalledProcessError as e:
            print(f"Không thể đọc file {filename}: {e}")
