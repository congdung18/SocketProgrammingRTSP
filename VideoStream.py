from PIL import Image
import io
import time  # THÊM DÒNG NÀY

class VideoStream:
    def __init__(self, filename, resolution="720p"):
        self.filename = filename
        self.original_frames = []  # Lưu frames gốc (chưa resize)
        self.resized_frames = {}   # Cache frames đã resize: {resolution: [frames]}
        self.current_resolution = resolution
        self.current_index = 0
        self.original_loaded = False
        
        print(f"[VIDEO] Loading {filename}")
        self.load_original_frames()  # Chỉ load frames gốc 1 lần
    
    def load_original_frames(self):
        """Load original frames without resizing."""
        try:
            with open(self.filename, 'rb') as f:
                data = f.read()
            
            print(f"[VIDEO] File size: {len(data):,} bytes")
            
            frames = []
            pos = 0
            loaded_count = 0
            
            while pos < len(data):
                # Find JPEG start/end
                soi_pos = data.find(b'\xff\xd8', pos)
                if soi_pos == -1:
                    break
                
                eoi_pos = data.find(b'\xff\xd9', soi_pos)
                if eoi_pos == -1:
                    break
                
                # Extract original frame
                frame_end = eoi_pos + 2
                frame_data = data[soi_pos:frame_end]
                
                frames.append(frame_data)
                pos = frame_end
                loaded_count += 1
                
                if loaded_count % 100 == 0:
                    print(f"[VIDEO] Loaded {loaded_count} original frames...")
            
            self.original_frames = frames
            self.original_loaded = True
            print(f"[VIDEO] Successfully loaded {len(frames)} original frames")
            
        except Exception as e:
            print(f"[VIDEO] Error loading original frames: {e}")
            self.original_frames = []
    
    def get_frames_for_resolution(self, resolution):
        """Get or create frames for specific resolution."""
        if resolution not in self.resized_frames:
            print(f"[VIDEO] Resizing frames to {resolution}...")
            
            # Target size
            if resolution == "720p":
                target_size = (1280, 720)
                quality = 85
            elif resolution == "1080p":
                target_size = (1920, 1080)
                quality = 80
            else:
                target_size = (1280, 720)
                quality = 85
            
            resized_frames = []
            
            for i, frame_data in enumerate(self.original_frames):
                try:
                    img = Image.open(io.BytesIO(frame_data))
                    
                    # Resize if needed
                    if img.size != target_size:
                        img = img.resize(target_size, Image.Resampling.LANCZOS)
                    
                    # Save with appropriate quality
                    buffer = io.BytesIO()
                    img.save(buffer, format='JPEG', quality=quality, optimize=True)
                    resized_frames.append(buffer.getvalue())
                    
                except Exception as e:
                    # Keep original if resize fails
                    resized_frames.append(frame_data)
                
                if (i + 1) % 100 == 0:
                    print(f"[VIDEO] Resized {i + 1}/{len(self.original_frames)} frames to {resolution}")
            
            self.resized_frames[resolution] = resized_frames
            print(f"[VIDEO] Resizing complete for {resolution}")
        
        return self.resized_frames[resolution]
    
    def change_resolution(self, new_resolution):
        """Change resolution dynamically - COMPLETE VERSION."""
        if new_resolution == self.current_resolution:
            print(f"[VIDEO] Already at {new_resolution}")
            return True
        
        print(f"[VIDEO] Changing resolution from {self.current_resolution} to {new_resolution}")
        
        try:
            # Check if resolution already cached
            if new_resolution in self.resized_frames:
                print(f"[VIDEO] Using cached {new_resolution} frames")
                self.current_resolution = new_resolution
                return True
            
            # Get target size and quality based on resolution
            if new_resolution == "720p":
                target_size = (1280, 720)
                quality = 85
                print(f"[VIDEO] Target: 1280x720, Quality: {quality}")
            elif new_resolution == "1080p":
                target_size = (1920, 1080)
                quality = 80
                print(f"[VIDEO] Target: 1920x1080, Quality: {quality}")
            else:
                print(f"[VIDEO] Unknown resolution: {new_resolution}")
                return False
            
            # Resize frames
            print(f"[VIDEO] Starting to resize {len(self.original_frames)} frames to {new_resolution}...")
            resized_frames = []
            total_frames = len(self.original_frames)
            start_time = time.time()
            
            for i, frame_data in enumerate(self.original_frames):
                try:
                    # Open original frame
                    img = Image.open(io.BytesIO(frame_data))
                    
                    # Resize if needed
                    if img.size != target_size:
                        img = img.resize(target_size, Image.Resampling.LANCZOS)
                    
                    # Save with appropriate quality
                    buffer = io.BytesIO()
                    img.save(buffer, format='JPEG', quality=quality, optimize=True)
                    resized_frames.append(buffer.getvalue())
                    
                except Exception as e:
                    print(f"[VIDEO] Error resizing frame {i}: {e}")
                    # Keep original if resize fails
                    resized_frames.append(frame_data)
                
                # Progress reporting
                if (i + 1) % 50 == 0 or (i + 1) == total_frames:
                    elapsed = time.time() - start_time
                    percent = ((i + 1) / total_frames) * 100
                    print(f"[VIDEO] Resized {i + 1}/{total_frames} frames ({percent:.1f}%) - {elapsed:.1f}s")
            
            # Verify frame count
            if len(resized_frames) != len(self.original_frames):
                print(f"[VIDEO] ERROR: Frame count mismatch! Original: {len(self.original_frames)}, Resized: {len(resized_frames)}")
                return False
            
            # Update cache and current resolution
            self.resized_frames[new_resolution] = resized_frames
            self.current_resolution = new_resolution
            
            total_time = time.time() - start_time
            print(f"[VIDEO] Resolution change complete: {new_resolution}")
            print(f"[VIDEO] Total time: {total_time:.2f}s, Average: {total_time/total_frames:.3f}s per frame")
            
            # Optional: Clean up old cache to save memory (keep max 2 resolutions)
            resolutions_to_keep = [new_resolution, "720p", "1080p"]
            for res in list(self.resized_frames.keys()):
                if res != new_resolution and res in resolutions_to_keep[1:]:
                    # Keep one alternative resolution
                    pass
                elif res != new_resolution:
                    print(f"[VIDEO] Cleaning cache for old resolution: {res}")
                    del self.resized_frames[res]
            
            return True
            
        except Exception as e:
            print(f"[VIDEO] Error during resolution change: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def nextFrame(self):
        """Get next frame in current resolution."""
        if not self.original_loaded:
            return None
        
        # Get frames for current resolution
        frames = self.get_frames_for_resolution(self.current_resolution)
        
        if not frames:
            return None
        
        # Loop back if at end
        if self.current_index >= len(frames):
            self.current_index = 0
        
        frame = frames[self.current_index]
        self.current_index += 1
        
        return frame
    
    def reset(self):
        """Reset to beginning."""
        self.current_index = 0
        print("[VIDEO] Reset to beginning")
    
    def get_position(self):
        return self.current_index
    
    def seek(self, frame_index):
        if 0 <= frame_index < len(self.original_frames):
            self.current_index = frame_index
            return True
        return False