# class VideoStream:
# 	def __init__(self, filename):
# 		self.filename = filename
# 		try:
# 			self.file = open(filename, 'rb')
# 		except:
# 			raise IOError
# 		self.frameNum = 0
		
# 	def nextFrame(self):
# 		"""Get next frame."""
# 		data = self.file.read(5) # Get the framelength from the first 5 bits
# 		if data: 
# 			framelength = int(data)
							
# 			# Read the current frame
# 			data = self.file.read(framelength)
# 			self.frameNum += 1
# 		return data
		
# 	def frameNbr(self):
# 		"""Get frame number."""
# 		return self.frameNum
	
# VideoStream.py
class VideoStream:
    """
    VideoStream supports two formats:
    - LAB_PROPRIETARY: each frame preceded by 5-byte ASCII decimal length (lab format)
    - MJPEG_STANDARD: standard MJPEG stream of concatenated JPEGs using 0xFFD8..0xFFD9 markers
    """
    def __init__(self, filename):
        self.filename = filename
        try:
            self.file = open(filename, 'rb')
        except:
            raise IOError
        self.frameNum = 0
        self.mode = None

        # Detect mode by reading first bytes
        first_bytes = self.file.read(5)
        self.file.seek(0)
        # If file begins with JPEG SOI marker 0xFFD8 => standard MJPEG
        if len(first_bytes) >= 2 and first_bytes[:2] == b'\xff\xd8':
            self.mode = 'MJPEG_STANDARD'
        else:
            # default to lab proprietary (5-byte length header)
            self.mode = 'LAB_PROPRIETARY'

    def nextFrame(self):
        """Return next frame as bytes, or None at EOF."""
        if self.mode == 'LAB_PROPRIETARY':
            # Read 5 bytes length header (ASCII or raw digits)
            length_bytes = self.file.read(5)
            if not length_bytes:
                return None
            # Attempt to parse as ascii decimal (as lab spec often uses)
            try:
                framelength = int(length_bytes)
            except:
                # fallback: if cannot parse, treat as zero / EOF
                return None
            if framelength <= 0:
                return None
            data = self.file.read(framelength)
            if not data:
                return None
            self.frameNum += 1
            return data

        else:  # MJPEG_STANDARD
            # Scan stream from current position for SOI..EOI marker pair
            # We'll accumulate until we find an EOI (0xFFD9)
            data_buf = bytearray()
            found_soi = False

            while True:
                b = self.file.read(1)
                if not b:
                    # EOF
                    if data_buf:
                        # return last partial if any
                        self.frameNum += 1
                        return bytes(data_buf)
                    return None

                data_buf.append(b[0])

                # detect SOI if not yet found
                if not found_soi and len(data_buf) >= 2:
                    if data_buf[-2:] == b'\xff\xd8':
                        found_soi = True
                        # keep accumulating from SOI -- but keep entire buffer

                # detect EOI
                if found_soi and len(data_buf) >= 2:
                    if data_buf[-2:] == b'\xff\xd9':
                        self.frameNum += 1
                        return bytes(data_buf)

    def frameNbr(self):
        return self.frameNum