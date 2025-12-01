import sys, traceback

def check_mjpeg(filename):
    try:
        with open(filename, 'rb') as f:
            frame_num = 0
            while True:
                header = f.read(5)
                if not header or len(header) < 5:
                    break
                frame_len = int.from_bytes(header, byteorder='big')
                data = f.read(frame_len)
                frame_num += 1
                if len(data) < frame_len:
                    print(f"Frame {frame_num}: không đủ dữ liệu! Chỉ đọc được {len(data)} / {frame_len} bytes")
                else:
                    print(f"Frame {frame_num}: length = {frame_len} bytes ✅")
    except Exception as e:
        print("Lỗi:", e)
        traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python check.py <filename.Mjpeg>")
    else:
        check_mjpeg(sys.argv[1])
