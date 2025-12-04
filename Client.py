from tkinter import *
import tkinter.messagebox as tkMessageBox
from PIL import Image, ImageTk
import socket, threading, sys, traceback, os, time
from RtpPacket import RtpPacket

CACHE_FILE_NAME = "cache-"
CACHE_FILE_EXT = ".jpg"

class Client:
    INIT = 0
    READY = 1
    PLAYING = 2
    state = INIT

    SETUP = 0
    PLAY = 1
    PAUSE = 2
    TEARDOWN = 3
    CHANGE_RESOLUTION = 4  # THÊM DÒNG NÀY

    def __init__(self, master, serveraddr, serverport, rtpport, filename):
        self.master = master
        self.master.protocol("WM_DELETE_WINDOW", self.handler)
        self.serverAddr = serveraddr
        self.serverPort = int(serverport)
        self.rtpPort = int(rtpport)
        self.fileName = filename
        self.rtspSeq = 0
        self.sessionId = 0
        self.requestSent = -1
        self.teardownAcked = 0
        
        # Resolution properties
        self.resolution = "720p"
        self.target_width = 1280
        self.target_height = 720
        
        # Current display size
        self.display_width = 1280
        self.display_height = 720
        
        # Sockets
        self.rtpSocket = None
        self.rtspSocket = None
        
        # Thread control
        self.listening_thread = None
        self.display_thread = None
        self.reply_thread = None
        self.playEvent = threading.Event()
        self.display_event = threading.Event()
        self.stop_listening = threading.Event()
        self.running = True
        
        # Buffer for frame reassembly
        self.current_buffer = None
        self.buffer_lock = threading.Lock()
        self.frameNbr = 0
        
        # Cache and display
        self.current_photo = None
        self._last_frame_file = None
        
        # Statistics
        self.packets_received = 0
        self.frames_received = 0
        
        # Create GUI first
        self.createWidgets()
        
        # Connect to server
        self.connectToServer()

    def createWidgets(self):
        """Build responsive GUI with resolution selector and change button."""
        # Configure grid
        self.master.grid_rowconfigure(0, weight=0)  # Resolution selector
        self.master.grid_rowconfigure(1, weight=1)  # Video label
        self.master.grid_rowconfigure(2, weight=0)  # Button row
        self.master.grid_rowconfigure(3, weight=0)  # Status row
        for i in range(4):
            self.master.grid_columnconfigure(i, weight=1)

        # Resolution selection frame
        resolution_frame = Frame(self.master, bg='#f0f0f0')
        resolution_frame.grid(row=0, column=0, columnspan=4, sticky='ew', padx=5, pady=5)
        
        # Resolution label
        Label(resolution_frame, text="Resolution:", font=('Arial', 10, 'bold'), 
            bg='#f0f0f0').pack(side=LEFT, padx=5)
        
        # Resolution dropdown
        self.resolution_var = StringVar(value=self.resolution)
        self.resolution_menu = OptionMenu(resolution_frame, self.resolution_var, 
                                        "720p", "1080p", 
                                        command=self.on_resolution_change)
        self.resolution_menu.config(width=10, font=('Arial', 9))
        self.resolution_menu.pack(side=LEFT, padx=5)
        
        # Change resolution button
        self.change_res_btn = Button(resolution_frame, text="Change Resolution", 
                                    command=self.changeResolution,
                                    font=('Arial', 9), width=15,
                                    bg='#4CAF50', fg='white',
                                    activebackground='#45a049',
                                    state='disabled')
        self.change_res_btn.pack(side=LEFT, padx=10)
        
        # Current resolution label
        self.resolution_label = Label(resolution_frame, 
                                    text=f"Current: {self.resolution}", 
                                    font=('Arial', 9, 'bold'), 
                                    fg='blue', bg='#f0f0f0')
        self.resolution_label.pack(side=LEFT, padx=10)

        # Video display label
        self.label = Label(self.master, bg='black', 
                        text="Connect to server first\nClick 'Setup' to begin", 
                        font=('Arial', 12), fg='white', justify='center')
        self.label.grid(row=1, column=0, columnspan=4, sticky='nsew', padx=5, pady=5)

        # Control buttons frame
        button_frame = Frame(self.master, bg='#e0e0e0')
        button_frame.grid(row=2, column=0, columnspan=4, sticky='ew', padx=5, pady=5)
        
        # Setup button
        self.setup = Button(button_frame, width=15, padx=3, pady=3, 
                        font=('Arial', 10, 'bold'))
        self.setup["text"] = "Setup"
        self.setup["command"] = self.setupMovie
        self.setup["bg"] = "#2196F3"  # Blue
        self.setup["fg"] = "white"
        self.setup["activebackground"] = "#1976D2"
        self.setup.grid(row=0, column=0, padx=10, pady=10, sticky='ew')

        # Play button
        self.start = Button(button_frame, width=15, padx=3, pady=3, 
                        font=('Arial', 10, 'bold'))
        self.start["text"] = "Play"
        self.start["command"] = self.playMovie
        self.start["bg"] = "#4CAF50"  # Green
        self.start["fg"] = "white"
        self.start["activebackground"] = "#45a049"
        self.start["state"] = "disabled"
        self.start.grid(row=0, column=1, padx=10, pady=10, sticky='ew')

        # Pause button
        self.pause = Button(button_frame, width=15, padx=3, pady=3, 
                        font=('Arial', 10, 'bold'))
        self.pause["text"] = "Pause"
        self.pause["command"] = self.pauseMovie
        self.pause["bg"] = "#FF9800"  # Orange
        self.pause["fg"] = "white"
        self.pause["activebackground"] = "#F57C00"
        self.pause["state"] = "disabled"
        self.pause.grid(row=0, column=2, padx=10, pady=10, sticky='ew')

        # Teardown button
        self.teardown = Button(button_frame, width=15, padx=3, pady=3, 
                            font=('Arial', 10, 'bold'))
        self.teardown["text"] = "Teardown"
        self.teardown["command"] = self.exitClient
        self.teardown["bg"] = "#f44336"  # Red
        self.teardown["fg"] = "white"
        self.teardown["activebackground"] = "#d32f2f"
        self.teardown["state"] = "disabled"
        self.teardown.grid(row=0, column=3, padx=10, pady=10, sticky='ew')

        # Status frame
        status_frame = Frame(self.master, bg='#f8f8f8', height=30)
        status_frame.grid(row=3, column=0, columnspan=4, sticky='ew', padx=5, pady=2)
        status_frame.grid_propagate(False)
        
        # Status label
        self.status_label = Label(status_frame, text="Status: Not connected to server", 
                                font=('Arial', 9), fg='gray', bg='#f8f8f8')
        self.status_label.pack(side=LEFT, padx=10, pady=5)
        
        # Stats label
        self.stats_label = Label(status_frame, text="Packets: 0 | Frames: 0", 
                                font=('Arial', 9), fg='blue', bg='#f8f8f8')
        self.stats_label.pack(side=RIGHT, padx=10, pady=5)

        # Configure button frame columns
        for i in range(4):
            button_frame.grid_columnconfigure(i, weight=1)

        # Bind resize event
        self.master.bind('<Configure>', self.on_window_resize)

    def updateButtonStates(self):
        """Update button states based on current state."""
        if self.state == self.INIT:
            self.setup["state"] = "normal"
            self.start["state"] = "disabled"
            self.pause["state"] = "disabled"
            self.teardown["state"] = "normal"
            self.change_res_btn["state"] = "disabled"
            self.change_res_btn["bg"] = "#A5D6A7"
            self.change_res_btn["text"] = "Change Resolution"
            self.status_label.config(text="Status: Ready to Setup", fg='blue', font=('Arial', 9, 'bold'))
            
        elif self.state == self.READY:
            self.setup["state"] = "disabled"
            self.start["state"] = "normal"
            self.pause["state"] = "disabled"
            self.teardown["state"] = "normal"
            self.change_res_btn["state"] = "normal"
            self.change_res_btn["bg"] = "#4CAF50"
            
            # Update button text based on selected resolution
            selected_res = self.resolution_var.get()
            if selected_res != self.resolution:
                self.change_res_btn["text"] = f"Change to {selected_res}"
            else:
                self.change_res_btn["text"] = "Change Resolution"
                
            self.status_label.config(text=f"Status: Ready to Play ({self.resolution})", 
                                fg='green', font=('Arial', 9, 'bold'))
            
        elif self.state == self.PLAYING:
            self.setup["state"] = "disabled"
            self.start["state"] = "disabled"
            self.pause["state"] = "normal"
            self.teardown["state"] = "normal"
            self.change_res_btn["state"] = "normal"
            self.change_res_btn["bg"] = "#4CAF50"
            
            # Update button text based on selected resolution
            selected_res = self.resolution_var.get()
            if selected_res != self.resolution:
                self.change_res_btn["text"] = f"Change to {selected_res}"
            else:
                self.change_res_btn["text"] = "Change Resolution"
                
            self.status_label.config(text=f"Status: Playing ({self.resolution})", 
                                fg='green', font=('Arial', 9, 'bold'))
        
        # Update resolution label
        self.resolution_label.config(text=f"Current: {self.resolution}", 
                                font=('Arial', 9, 'bold'), fg='blue')
        
        # Update window title
        self.master.title(f"RTP Video Client - {self.resolution}")
        
        self.master.update_idletasks()

    def updateStats(self):
        """Update statistics display."""
        self.stats_label.config(text=f"Packets: {self.packets_received} | Frames: {self.frames_received}")

    def on_resolution_change(self, value):
        """Handle resolution change dropdown selection."""
        print(f"[CLIENT] Resolution dropdown changed to: {value}")
        
        # Update button text
        if self.change_res_btn["state"] == "normal":
            if value != self.resolution:
                self.change_res_btn["text"] = f"Change to {value}"
            else:
                self.change_res_btn["text"] = "Change Resolution"
        
        # Update resolution label
        if value != self.resolution:
            self.resolution_label.config(text=f"Current: {self.resolution} → Selected: {value}", 
                                    fg='orange', font=('Arial', 9, 'bold'))
        else:
            self.resolution_label.config(text=f"Current: {self.resolution}", 
                                    fg='blue', font=('Arial', 9, 'bold'))
        
        # Update target dimensions
        if value == "720p":
            self.target_width = 1280
            self.target_height = 720
        elif value == "1080p":
            self.target_width = 1920
            self.target_height = 1080
    
    def on_window_resize(self, event):
        """Handle window resize events."""
        if event.widget == self.master:
            new_width = event.width - 20
            new_height = event.height - 180
            
            if new_width > 0 and new_height > 0:
                target_ratio = 16/9
                current_ratio = new_width / new_height
                
                if current_ratio > target_ratio:
                    self.display_width = int(new_height * target_ratio)
                else:
                    self.display_height = int(new_width / target_ratio)
                
                self.display_width = max(320, self.display_width)
                self.display_height = max(180, self.display_height)

    def setupMovie(self):
        """Setup button handler."""
        if self.state == self.INIT:
            print("[CLIENT] Setup button clicked")
            self.label.configure(text="Setting up video stream...")
            self.status_label.config(text="Status: Setting up...", fg='orange')
            self.sendRtspRequest(self.SETUP)

    def exitClient(self):
        """Teardown button handler."""
        print("[CLIENT] ExitClient called")
        
        self.running = False
        self.stop_listening.set()
        self.playEvent.set()
        self.display_event.set()
        
        if self.state != self.INIT and self.rtspSocket:
            try:
                self.sendRtspRequest(self.TEARDOWN)
                time.sleep(0.5)
            except:
                pass
        
        # Clean up cache file
        if self.sessionId > 0:
            try:
                cache_file = CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT
                if os.path.exists(cache_file):
                    os.remove(cache_file)
                    print(f"[CLIENT] Removed cache file: {cache_file}")
            except Exception as e:
                print(f"[CLIENT] Error removing cache: {e}")
        
        # Close sockets
        if self.rtpSocket:
            try:
                self.rtpSocket.close()
                print("[CLIENT] Closed RTP socket")
            except:
                pass
        
        if self.rtspSocket:
            try:
                self.rtspSocket.close()
                print("[CLIENT] Closed RTSP socket")
            except:
                pass
        
        self.master.destroy()
        print("[CLIENT] Window destroyed")

    def pauseMovie(self):
        """Pause button handler."""
        if self.state == self.PLAYING:
            print("[CLIENT] Pause button clicked")
            self.sendRtspRequest(self.PAUSE)

    def playMovie(self):
        """Play button handler."""
        if self.state == self.READY:
            print("[CLIENT] Play button clicked")
            self.label.configure(text="Starting video playback...")
            
            self.stop_listening.clear()
            
            # Reset statistics
            self.packets_received = 0
            self.frames_received = 0
            self.updateStats()
            
            # Create RTP socket if needed
            if not self.rtpSocket:
                self.openRtpPort()
            
            print("[CLIENT] Sending PLAY request...")
            self.sendRtspRequest(self.PLAY)
            
            time.sleep(0.5)
            
            # Start RTP listener thread
            if not self.listening_thread or not self.listening_thread.is_alive():
                self.listening_thread = threading.Thread(target=self.listenRtp, daemon=True)
                self.listening_thread.start()
                print("[CLIENT] Started RTP listener thread")
            
            # Start display thread
            if not self.display_thread or not self.display_thread.is_alive():
                self.display_thread = threading.Thread(target=self.displayWorker, daemon=True)
                self.display_thread.start()
                print("[CLIENT] Started display worker thread")

    def listenRtp(self):
        """RTP listener."""
        print("[CLIENT] RTP listener started")
        
        if not self.rtpSocket:
            return
        
        BUFFER_SIZE = 65536
        current_frame = bytearray()
        expecting_frame = False
        packet_count = 0
        frame_count = 0
        last_seq = -1
        last_report_time = time.time()
        
        self.rtpSocket.settimeout(0.5)
        
        try:
            while not self.stop_listening.is_set() and self.state == self.PLAYING:
                try:
                    data, addr = self.rtpSocket.recvfrom(BUFFER_SIZE)
                    
                    if not data or len(data) < 12:
                        continue
                    
                    packet_count += 1
                    self.packets_received += 1
                    
                    # Parse RTP header
                    marker = (data[1] >> 7) & 0x01
                    seq_num = (data[2] << 8) | data[3]
                    payload = data[12:]
                    
                    # Check sequence continuity
                    if last_seq != -1 and seq_num != (last_seq + 1) % 65536:
                        gap = (seq_num - last_seq - 1) % 65536
                        if gap > 0:
                            print(f"[CLIENT] Sequence gap: {last_seq} -> {seq_num} (gap: {gap})")
                    
                    last_seq = seq_num
                    
                    # Frame assembly
                    if not expecting_frame:
                        soi_pos = payload.find(b'\xff\xd8')
                        if soi_pos != -1:
                            current_frame = bytearray(payload[soi_pos:])
                            expecting_frame = True
                        else:
                            continue
                    else:
                        current_frame.extend(payload)
                    
                    # Check if frame is complete
                    if marker == 1 and expecting_frame:
                        eoi_pos = current_frame.find(b'\xff\xd9')
                        if eoi_pos != -1:
                            jpeg_data = bytes(current_frame[:eoi_pos + 2])
                            
                            if jpeg_data[:2] == b'\xff\xd8' and jpeg_data[-2:] == b'\xff\xd9':
                                frame_count += 1
                                self.frames_received += 1
                                
                                # Save to cache
                                cache_file = self.writeFrame(jpeg_data)
                                if cache_file:
                                    self._last_frame_file = cache_file
                                    self.display_event.set()
                                
                                # Update stats every 10 frames
                                if frame_count % 10 == 0:
                                    self.updateStats()
                            
                            # Reset for next frame
                            expecting_frame = False
                            current_frame = bytearray()
                    
                    # Progress reporting
                    current_time = time.time()
                    if current_time - last_report_time >= 2.0:
                        fps = frame_count / (current_time - last_report_time)
                        print(f"[CLIENT] Receiving: {fps:.1f} FPS, {packet_count} packets")
                        last_report_time = current_time
                        frame_count = 0
                        packet_count = 0
                    
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"[CLIENT] Listen error: {e}")
                    continue
        
        except Exception as e:
            print(f"[CLIENT] Fatal: {e}")
        
        print(f"[CLIENT] RTP listener stopped")
        
    def displayWorker(self):
        """Display worker thread."""
        print("[CLIENT] Display worker started")
        
        frame_count = 0
        
        while not self.stop_listening.is_set() and self.state == self.PLAYING:
            try:
                if self.display_event.wait(timeout=1.0):
                    if self._last_frame_file and os.path.exists(self._last_frame_file):
                        try:
                            self.updateMovie(self._last_frame_file)
                            frame_count += 1
                            if frame_count % 5 == 0:
                                print(f"[CLIENT] Displayed frame {frame_count}")
                        except Exception as e:
                            print(f"[CLIENT] Display error: {e}")
                    self.display_event.clear()
                else:
                    if self.state != self.PLAYING:
                        break
            except Exception as e:
                print(f"[CLIENT] Display worker error: {e}")
        
        print(f"[CLIENT] Display worker stopped. Displayed {frame_count} frames.")

    def updateMovie(self, imageFile):
        """Update movie display."""
        try:
            image = Image.open(imageFile)
            
            if self.display_width > 0 and self.display_height > 0:
                image.thumbnail((self.display_width, self.display_height), Image.Resampling.LANCZOS)
            
            photo = ImageTk.PhotoImage(image)
            
            self.master.after(0, lambda p=photo: self.updateImage(p))
            
        except Exception as e:
            print(f"[CLIENT] Error updating movie: {e}")

    def updateImage(self, photo):
        """Update image in GUI."""
        self.current_photo = photo
        self.label.configure(image=photo, text="")
        self.label.image = photo

    def writeFrame(self, data):
        """Write frame to cache file with verification."""
        cache_file = CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT
        
        if not self.isValidJpeg(data):
            print(f"[CLIENT] WARNING: Invalid JPEG data")
            print(f"  Start: {data[:2].hex() if len(data) >= 2 else 'N/A'}")
            print(f"  End: {data[-2:].hex() if len(data) >= 2 else 'N/A'}")
            print(f"  Size: {len(data)} bytes")
            return None
        
        try:
            with open(cache_file, "wb") as f:
                f.write(data)
            
            file_size = os.path.getsize(cache_file)
            print(f"[CLIENT] Wrote frame to {cache_file} ({file_size} bytes)")
            
            return cache_file
        except Exception as e:
            print(f"[CLIENT] Error writing frame: {e}")
            return None

    def connectToServer(self):
        """Connect to the Server."""
        print(f"[CLIENT] Connecting to {self.serverAddr}:{self.serverPort}")
        try:
            self.rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.rtspSocket.settimeout(5.0)
            self.rtspSocket.connect((self.serverAddr, self.serverPort))
            self.rtspSocket.settimeout(None)
            print("[CLIENT] Connected to server")
            self.label.configure(text="Connected to server. Click Setup.", fg='green')
            self.status_label.config(text="Status: Connected to server", fg='green')
            
            self.updateButtonStates()
            return True
        except Exception as e:
            error_msg = f'Connection failed: {e}'
            print(f"[CLIENT] {error_msg}")
            self.label.configure(text=error_msg, fg='red')
            self.status_label.config(text=f"Status: Connection failed - {e}", fg='red')
            return False

    def sendRtspRequest(self, requestCode):
        """Send RTSP request to the server - UPDATED WITH CHANGE_RESOLUTION."""
        print(f"[CLIENT] Sending request: {requestCode}")
        
        if not self.rtspSocket:
            print("[CLIENT] ERROR: No RTSP socket connection")
            return
        
        if requestCode == self.SETUP and self.state == self.INIT:
            self.rtspSeq = 1
            request = (
                f"SETUP {self.fileName} RTSP/1.0\r\n"
                f"CSeq: {self.rtspSeq}\r\n"
                f"Transport: RTP/UDP;client_port={self.rtpPort}\r\n"
                f"Resolution: {self.resolution}\r\n\r\n"
            )
            self.requestSent = self.SETUP
            
        elif requestCode == self.PLAY and self.state == self.READY:
            self.rtspSeq += 1
            request = (
                f"PLAY {self.fileName} RTSP/1.0\r\n"
                f"CSeq: {self.rtspSeq}\r\n"
                f"Session: {self.sessionId}\r\n\r\n"
            )
            self.requestSent = self.PLAY
            
        elif requestCode == self.PAUSE and self.state == self.PLAYING:
            self.rtspSeq += 1
            request = (
                f"PAUSE {self.fileName} RTSP/1.0\r\n"
                f"CSeq: {self.rtspSeq}\r\n"
                f"Session: {self.sessionId}\r\n\r\n"
            )
            self.requestSent = self.PAUSE
            
        elif requestCode == self.TEARDOWN and self.state != self.INIT:
            self.rtspSeq += 1
            request = (
                f"TEARDOWN {self.fileName} RTSP/1.0\r\n"
                f"CSeq: {self.rtspSeq}\r\n"
                f"Session: {self.sessionId}\r\n\r\n"
            )
            self.requestSent = self.TEARDOWN
            
        # THÊM CASE CHO CHANGE_RESOLUTION
        elif requestCode == self.CHANGE_RESOLUTION and self.state in [self.READY, self.PLAYING]:
            self.rtspSeq += 1
            new_resolution = self.resolution_var.get()
            request = (
                f"CHANGE_RESOLUTION {self.fileName} RTSP/1.0\r\n"
                f"CSeq: {self.rtspSeq}\r\n"
                f"Session: {self.sessionId}\r\n"
                f"Resolution: {new_resolution}\r\n\r\n"
            )
            self.requestSent = self.CHANGE_RESOLUTION
            print(f"[CLIENT] CHANGE_RESOLUTION request to: {new_resolution}")
            
        else:
            print(f"[CLIENT] Invalid request in current state: {requestCode}, state={self.state}")
            return
        
        print(f"[CLIENT] Sending request (CSeq: {self.rtspSeq}):\n{request}")
        
        try:
            self.rtspSocket.send(request.encode())
            print(f"[CLIENT] Request sent successfully")
            
            if requestCode == self.SETUP:
                if not self.reply_thread or not self.reply_thread.is_alive():
                    self.reply_thread = threading.Thread(target=self.recvRtspReply, daemon=True)
                    self.reply_thread.start()
                    
        except Exception as e:
            print(f"[CLIENT] Error sending request: {e}")

    def recvRtspReply(self):
        """Receive RTSP reply from the server."""
        print("[CLIENT] RTSP reply thread started")
        
        try:
            while self.running:
                try:
                    reply = self.rtspSocket.recv(1024)
                    if not reply:
                        print("[CLIENT] Server disconnected")
                        self.label.configure(text="Server disconnected", fg='red')
                        break
                    
                    reply_str = reply.decode("utf-8", errors='ignore')
                    self.parseRtspReply(reply_str)
                    
                    if self.requestSent == self.TEARDOWN and self.teardownAcked:
                        break
                        
                except socket.timeout:
                    continue
                except ConnectionAbortedError:
                    print("[CLIENT] Connection aborted")
                    break
                except Exception as e:
                    print(f"[CLIENT] RTSP reply thread error: {e}")
                    break
        except Exception as e:
            print(f"[CLIENT] RTSP reply thread fatal error: {e}")
        
        print("[CLIENT] RTSP reply thread stopped")

    def parseRtspReply(self, data):
        """Parse RTSP reply - UPDATED WITH CHANGE_RESOLUTION."""
        print(f"[CLIENT] Received reply:\n{data}")
        
        lines = data.strip().split('\n')
        
        if len(lines) < 2:
            return
        
        # Parse status line
        status_line = lines[0]
        if '200 OK' not in status_line:
            print(f"[CLIENT] Server error: {status_line}")
            error_msg = status_line.replace('RTSP/1.0 ', '')
            self.label.configure(text=f"Server error: {error_msg}", fg='red')
            return
        
        # Parse headers
        cseq = 0
        session = 0
        new_resolution = self.resolution
        
        for line in lines[1:]:
            line = line.strip()
            if line.startswith('CSeq:'):
                try:
                    cseq = int(line.split(':')[1].strip())
                except:
                    cseq = 0
            elif line.startswith('Session:'):
                try:
                    session = int(line.split(':')[1].strip())
                except:
                    session = 0
            elif line.startswith('Resolution:'):
                new_resolution = line.split(':')[1].strip()
                print(f"[CLIENT] Server reports resolution: {new_resolution}")
        
        # Update session ID
        if session and self.sessionId == 0:
            self.sessionId = session
            print(f"[CLIENT] Session ID set to: {self.sessionId}")
        
        # Check if resolution changed
        resolution_changed = False
        if new_resolution and new_resolution != self.resolution:
            old_resolution = self.resolution
            self.resolution = new_resolution
            self.resolution_var.set(new_resolution)
            self.resolution_label.config(text=f"Current: {new_resolution}", 
                                    font=('Arial', 9, 'bold'), fg='blue')
            resolution_changed = True
            
            # Update target dimensions
            if new_resolution == "720p":
                self.target_width = 1280
                self.target_height = 720
            elif new_resolution == "1080p":
                self.target_width = 1920
                self.target_height = 1080
            
            print(f"[CLIENT] Resolution updated from {old_resolution} to {new_resolution}")
        
        # Update state based on request
        if self.requestSent == self.SETUP:
            self.state = self.READY
            print("[CLIENT] SETUP successful, state=READY")
            self.label.configure(text="Setup complete!\nClick 'Play' to start.", fg='green')
            self.updateButtonStates()
            
        elif self.requestSent == self.PLAY:
            self.state = self.PLAYING
            print("[CLIENT] PLAY successful, state=PLAYING")
            self.label.configure(text="Playing video...", fg='green')
            self.updateButtonStates()
            
        elif self.requestSent == self.PAUSE:
            self.state = self.READY
            print("[CLIENT] PAUSE successful, state=READY")
            self.label.configure(text="Video paused", fg='blue')
            self.stop_listening.set()
            self.updateButtonStates()
            
        elif self.requestSent == self.CHANGE_RESOLUTION:
            print(f"[CLIENT] CHANGE_RESOLUTION successful to {self.resolution}")
            
            # Clear old cache
            if self.sessionId > 0:
                try:
                    cache_file = CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT
                    if os.path.exists(cache_file):
                        os.remove(cache_file)
                        print(f"[CLIENT] Cleared old cache file")
                except:
                    pass
            
            # Reset counters
            self.frameNbr = 0
            self.frames_received = 0
            self.packets_received = 0
            self.updateStats()
            
            # Update UI
            self.label.configure(text=f"Resolution changed to {self.resolution}!\nVideo will resume shortly...", 
                            fg='green')
            self.status_label.config(text=f"Status: Playing at {self.resolution}", 
                                fg='green', font=('Arial', 9, 'bold'))
            
            # Re-enable change button
            self.change_res_btn["state"] = "normal"
            self.change_res_btn["text"] = "Change Resolution"
            
            # If we were playing, update button states
            if self.state == self.PLAYING:
                print("[CLIENT] Resuming playback at new resolution")
                self.master.after(1000, lambda: self.label.configure(
                    text=f"Playing at {self.resolution}...", 
                    fg='green'
                ))
            
            self.updateButtonStates()
            
        elif self.requestSent == self.TEARDOWN:
            self.teardownAcked = 1
            print("[CLIENT] TEARDOWN acknowledged")
            self.state = self.INIT
            self.label.configure(text="Disconnected from server", fg='black')
            self.stop_listening.set()
            self.updateButtonStates()
            
            if self.rtpSocket:
                try:
                    self.rtpSocket.close()
                    self.rtpSocket = None
                except:
                    pass
    
    def openRtpPort(self):
        """Open RTP port."""
        try:
            self.rtpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            
            self.rtpSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.rtpSocket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536 * 4)
            
            bind_ip = '0.0.0.0'
            
            print(f"[CLIENT] Binding RTP socket to {bind_ip}:{self.rtpPort}")
            self.rtpSocket.bind((bind_ip, self.rtpPort))
            
            self.rtpSocket.settimeout(2.0)
            
            sockname = self.rtpSocket.getsockname()
            print(f"[CLIENT] RTP port {self.rtpPort} opened and bound to {sockname}")
            
            # Test connection
            test_msg = b"RTP_TEST"
            self.rtpSocket.sendto(test_msg, ('127.0.0.1', self.rtpPort))
            print(f"[CLIENT] Sent test packet to 127.0.0.1:{self.rtpPort}")
            
            try:
                data, addr = self.rtpSocket.recvfrom(1024)
                print(f"[CLIENT] Received test packet: {data} from {addr}")
            except socket.timeout:
                print("[CLIENT] WARNING: Could not receive test packet (timeout)")
            
            return True
        except Exception as e:
            print(f"[CLIENT] Error opening RTP port: {e}")
            import traceback
            traceback.print_exc()
            return False

    def handler(self):
        """Handle window close."""
        if tkMessageBox.askokcancel("Quit", "Are you sure you want to quit?"):
            self.exitClient()

    def isValidJpeg(self, data):
        """Check if data is a valid JPEG."""
        if not data or len(data) < 4:
            return False
        return data[:2] == b'\xff\xd8' and data[-2:] == b'\xff\xd9'
    
    def changeResolution(self):
        """Handle resolution change mid-stream."""
        new_resolution = self.resolution_var.get()
        
        # Validate selection
        if new_resolution not in ["720p", "1080p"]:
            tkMessageBox.showerror("Error", f"Invalid resolution: {new_resolution}")
            return
        
        # Check if already at this resolution
        if new_resolution == self.resolution:
            tkMessageBox.showinfo("Info", f"Already streaming at {new_resolution}")
            return
        
        # Check if in valid state
        if self.state not in [self.READY, self.PLAYING]:
            tkMessageBox.showerror("Error", "Cannot change resolution in current state")
            return
        
        # Confirm with user
        confirm_msg = f"Change resolution from {self.resolution} to {new_resolution}?"
        if self.state == self.PLAYING:
            confirm_msg += "\n\nVideo will pause briefly during the change."
        
        response = tkMessageBox.askyesno("Change Resolution", confirm_msg)
        
        if response:
            print(f"[CLIENT] Requesting resolution change to {new_resolution}")
            
            # Update UI to show change in progress
            self.status_label.config(text=f"Changing to {new_resolution}...", 
                                fg='orange', font=('Arial', 9, 'bold'))
            self.label.configure(text=f"Changing resolution to {new_resolution}...\nPlease wait...", 
                            fg='orange', font=('Arial', 12))
            
            # Disable change button during transition
            self.change_res_btn["state"] = "disabled"
            self.change_res_btn["text"] = "Changing..."
            
            # Disable other control buttons temporarily
            if self.state == self.PLAYING:
                self.pause["state"] = "disabled"
                self.pause["bg"] = "#FFE0B2"
            self.start["state"] = "disabled"
            self.start["bg"] = "#C8E6C9"
            
            self.master.update()
            
            # Send CHANGE_RESOLUTION request
            self.sendRtspRequest(self.CHANGE_RESOLUTION)
            
            # Set timeout to re-enable button if no response
            def reenable_button():
                if self.change_res_btn["state"] == "disabled":
                    self.change_res_btn["state"] = "normal"
                    self.change_res_btn["text"] = "Change Resolution"
                    self.status_label.config(text="Change request timed out", fg='red')
            
            self.master.after(10000, reenable_button)

if __name__ == "__main__":
    try:
        serverAddr = sys.argv[1]
        serverPort = sys.argv[2]
        rtpPort = sys.argv[3]
        fileName = sys.argv[4]
    except:
        print("[Usage: ClientLauncher.py Server_name Server_port RTP_port Video_file]\n")
        sys.exit(1)
    
    root = Tk()
    root.geometry("1280x800")
    root.minsize(640, 480)
    
    app = Client(root, serverAddr, serverPort, rtpPort, fileName)
    app.master.title("RTPClient")
    root.mainloop()