class VideoStream:
	def __init__(self, filename):
		self.filename = filename
		try:
			self.file = open(filename, 'rb')
		except:
			raise IOError
		self.frameNum = 0
		self.cache = []
		self.cache_load = False
		self.load_cache()
  
	def load_cache(self):
		"""Load all frames into cache."""
		if not self.cache_load:
			while True:
				length_data = self.file.read(5)
				if not length_data:
					break
				frame_len = int(length_data)
				frame = self.file.read(frame_len)
				self.cache.append(frame)
			self.cache_load = True
			self.file.close()
   
	def setFrame(self, index):
		"""Jump to frame index."""
		if index < 0:
			index = 0
		elif index >= len(self.cache):
			index = len(self.cache) - 1
		self.frameNum = index
		return True
		
	def nextFrame(self):
		"""Get next frame."""
		if self.frameNum < len(self.cache):
			frame = self.cache[self.frameNum]
			self.frameNum += 1
		return frame
		
	def frameNbr(self):
		"""Get frame number."""
		return self.frameNum
	
	