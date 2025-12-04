from PIL import Image
import io

class VideoStream:
    def __init__(self, filename, resolution="720p"):
        self.filename = filename
        self.resolution = resolution
        self.frames = []
        self.current_index = 0  # **CHỈ DÙNG 1 biến đếm**
        
        print(f"[VIDEO] Loading {filename} at {resolution}")
        self.load_frames()
    
    def load_frames(self):
        """Load and resize frames."""
        # Target size based on resolution
        if self.resolution == "720p":
            target_size = (1280, 720)
        elif self.resolution == "1080p":
            target_size = (1920, 1080)
        else:
            target_size = (1280, 720)
        
        try:
            with open(self.filename, 'rb') as f:
                data = f.read()
            
            print(f"[VIDEO] File size: {len(data):,} bytes")
            
            # Simple MJPEG parsing
            frames = []
            pos = 0
            loaded_count = 0
            
            while pos < len(data):
                # Find JPEG start
                soi_pos = data.find(b'\xff\xd8', pos)
                if soi_pos == -1:
                    break
                
                # Find JPEG end
                eoi_pos = data.find(b'\xff\xd9', soi_pos)
                if eoi_pos == -1:
                    break
                
                # Extract frame
                frame_end = eoi_pos + 2
                frame_data = data[soi_pos:frame_end]
                loaded_count += 1
                
                # Resize if needed
                try:
                    img = Image.open(io.BytesIO(frame_data))
                    original_size = img.size
                    
                    if img.size != target_size:
                        img = img.resize(target_size, Image.Resampling.LANCZOS)
                        if loaded_count % 100 == 0:
                            print(f"[VIDEO] Resized frame {loaded_count}: {original_size} -> {target_size}")
                    
                    # Save as JPEG
                    buffer = io.BytesIO()
                    quality = 85 if self.resolution == "720p" else 80
                    img.save(buffer, format='JPEG', quality=quality)
                    frame_data = buffer.getvalue()
                except Exception as e:
                    # Keep original frame if resize fails
                    pass
                
                frames.append(frame_data)
                pos = frame_end
                
                if loaded_count % 100 == 0:
                    print(f"[VIDEO] Loaded {loaded_count} frames...")
            
            self.frames = frames
            print(f"[VIDEO] Successfully loaded {len(frames)} frames at {self.resolution}")
            
            # Calculate average frame size
            if frames:
                avg_size = sum(len(f) for f in frames) / len(frames)
                print(f"[VIDEO] Average frame size: {avg_size:,.0f} bytes")
            
        except Exception as e:
            print(f"[VIDEO] Error loading video: {e}")
            self.frames = []
    
    def nextFrame(self):
        """Get next frame - FIXED VERSION."""
        if not self.frames:
            print("[VIDEO] No frames available")
            return None
        
        # Loop back if at end
        if self.current_index >= len(self.frames):
            self.current_index = 0
            print("[VIDEO] Looping back to start")
        
        frame = self.frames[self.current_index]
        
        # Debug every 30 frames
        if self.current_index % 30 == 0:
            print(f"[VIDEO] Serving frame {self.current_index + 1}/{len(self.frames)} ({len(frame):,} bytes)")
        
        # **QUAN TRỌNG: Tăng current_index SAU KHI lấy frame**
        self.current_index += 1
        
        return frame
    
    def reset(self):
        """Reset to beginning."""
        self.current_index = 0
        print("[VIDEO] Reset to beginning")
    
    def get_position(self):
        """Get current position (0-based index)."""
        return self.current_index
    
    def get_total_frames(self):
        """Get total number of frames."""
        return len(self.frames)
    
    def seek(self, frame_index):
        """Seek to specific frame index (0-based)."""
        if 0 <= frame_index < len(self.frames):
            self.current_index = frame_index
            print(f"[VIDEO] Seek to frame {frame_index + 1}/{len(self.frames)}")
            return True
        return False