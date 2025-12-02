class VideoStream:
    def __init__(self, filename):
        self.filename = filename
        try:
            self.file = open(filename, 'rb')
        except:
            raise IOError
        self.frameNum = 0
        self.mode = None
        
        # Detect format
        first_bytes = self.file.read(5)
        self.file.seek(0)
        
        if len(first_bytes) >= 2 and first_bytes[:2] == b'\xff\xd8':
            self.mode = 'MJPEG_STANDARD'
            print(f"[VIDEO] Detected MJPEG_STANDARD format")
        else:
            self.mode = 'LAB_PROPRIETARY'
            print(f"[VIDEO] Detected LAB_PROPRIETARY format")

    def nextFrame(self):
        """Return next frame as bytes, or None at EOF."""
        if self.mode == 'LAB_PROPRIETARY':
            # Original lab format
            length_bytes = self.file.read(5)
            if not length_bytes or len(length_bytes) < 5:
                return None
            
            try:
                framelength_str = length_bytes.decode('ascii')
                framelength = int(framelength_str)
            except:
                framelength = int.from_bytes(length_bytes, 'big')
            
            if framelength <= 0:
                return None
            
            data = self.file.read(framelength)
            if not data or len(data) < framelength:
                return None
            
            self.frameNum += 1
            if self.frameNum % 30 == 0:
                print(f"[VIDEO] Read frame {self.frameNum}, size: {len(data)} bytes")
            return data

        else:  # MJPEG_STANDARD
            # Improved MJPEG reader
            data_buf = bytearray()
            found_soi = False
            bytes_read = 0
            max_bytes_per_frame = 500000  # 500KB max
            
            while True:
                chunk = self.file.read(4096)  # Read in chunks for efficiency
                if not chunk:
                    # EOF
                    if data_buf and len(data_buf) >= 2 and data_buf[:2] == b'\xff\xd8':
                        self.frameNum += 1
                        frame_bytes = bytes(data_buf)
                        print(f"[VIDEO] Read frame {self.frameNum}, size: {len(frame_bytes)} bytes")
                        return frame_bytes
                    return None
                
                # Append chunk to buffer
                data_buf.extend(chunk)
                bytes_read += len(chunk)
                
                # Safety check
                if bytes_read > max_bytes_per_frame:
                    print(f"[VIDEO WARN] Frame too large, resetting")
                    return None
                
                # Check for EOI in new chunk
                if len(data_buf) >= 4:
                    # Find SOI if not found
                    if not found_soi:
                        soi_pos = data_buf.find(b'\xff\xd8')
                        if soi_pos != -1:
                            found_soi = True
                            # Keep only from SOI onward
                            data_buf = data_buf[soi_pos:]
                    
                    # Check for EOI
                    if found_soi:
                        eoi_pos = data_buf.find(b'\xff\xd9')
                        if eoi_pos != -1:
                            # Complete frame found
                            frame_end = eoi_pos + 2
                            frame_data = bytes(data_buf[:frame_end])
                            
                            # Keep remaining data for next frame
                            remaining = data_buf[frame_end:]
                            
                            self.frameNum += 1
                            frame_bytes = frame_data
                            print(f"[VIDEO] Read frame {self.frameNum}, size: {len(frame_bytes)} bytes")
                            
                            # Reset buffer with remaining data
                            self.file.seek(self.file.tell() - len(remaining))
                            return frame_bytes  