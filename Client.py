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
        """Build responsive GUI with resolution selector."""
        # Configure grid
        self.master.grid_rowconfigure(0, weight=0)  # Resolution selector
        self.master.grid_rowconfigure(1, weight=1)  # Video label
        self.master.grid_rowconfigure(2, weight=0)  # Button row
        self.master.grid_rowconfigure(3, weight=0)  # Status row
        for i in range(4):
            self.master.grid_columnconfigure(i, weight=1)

        # Resolution selection
        resolution_frame = Frame(self.master)
        resolution_frame.grid(row=0, column=0, columnspan=4, sticky='ew', padx=5, pady=5)
        
        Label(resolution_frame, text="Resolution:", font=('Arial', 10)).pack(side=LEFT, padx=5)
        
        self.resolution_var = StringVar(value=self.resolution)
        self.resolution_menu = OptionMenu(resolution_frame, self.resolution_var, 
                                         "720p", "1080p", 
                                         command=self.on_resolution_change)
        self.resolution_menu.config(width=10)
        self.resolution_menu.pack(side=LEFT, padx=5)
        
        self.resolution_label = Label(resolution_frame, text=f"Selected: {self.resolution}", 
                                     font=('Arial', 9), fg='blue')
        self.resolution_label.pack(side=LEFT, padx=10)

        # Video display label
        self.label = Label(self.master, bg='black', text="Connect to server first", 
                          font=('Arial', 12), fg='white')
        self.label.grid(row=1, column=0, columnspan=4, sticky='nsew', padx=5, pady=5)

        # Control buttons
        self.setup = Button(self.master, width=15, padx=3, pady=3, font=('Arial', 10))
        self.setup["text"] = "Setup"
        self.setup["command"] = self.setupMovie
        self.setup.grid(row=2, column=0, padx=10, pady=10, sticky='ew')

        self.start = Button(self.master, width=15, padx=3, pady=3, font=('Arial', 10))
        self.start["text"] = "Play"
        self.start["command"] = self.playMovie
        self.start["state"] = "disabled"
        self.start.grid(row=2, column=1, padx=10, pady=10, sticky='ew')

        self.pause = Button(self.master, width=15, padx=3, pady=3, font=('Arial', 10))
        self.pause["text"] = "Pause"
        self.pause["command"] = self.pauseMovie
        self.pause["state"] = "disabled"
        self.pause.grid(row=2, column=2, padx=10, pady=10, sticky='ew')

        self.teardown = Button(self.master, width=15, padx=3, pady=3, font=('Arial', 10))
        self.teardown["text"] = "Teardown"
        self.teardown["command"] = self.exitClient
        self.teardown["state"] = "disabled"
        self.teardown.grid(row=2, column=3, padx=10, pady=10, sticky='ew')

        # Status frame
        status_frame = Frame(self.master)
        status_frame.grid(row=3, column=0, columnspan=4, sticky='ew', padx=5, pady=2)
        
        self.status_label = Label(status_frame, text="Status: Not connected", 
                                 font=('Arial', 9), fg='gray')
        self.status_label.pack(side=LEFT, padx=5)
        
        self.stats_label = Label(status_frame, text="Packets: 0 | Frames: 0", 
                                font=('Arial', 9), fg='blue')
        self.stats_label.pack(side=RIGHT, padx=5)

        # Bind resize event
        self.master.bind('<Configure>', self.on_window_resize)

    def updateButtonStates(self):
        """Update button states based on current state."""
        if self.state == self.INIT:
            self.setup["state"] = "normal"
            self.start["state"] = "disabled"
            self.pause["state"] = "disabled"
            self.teardown["state"] = "normal"
            self.status_label.config(text="Status: Ready to Setup", fg='blue')
        elif self.state == self.READY:
            self.setup["state"] = "disabled"
            self.start["state"] = "normal"
            self.pause["state"] = "disabled"
            self.teardown["state"] = "normal"
            self.status_label.config(text="Status: Ready to Play", fg='green')
        elif self.state == self.PLAYING:
            self.setup["state"] = "disabled"
            self.start["state"] = "disabled"
            self.pause["state"] = "normal"
            self.teardown["state"] = "normal"
            self.status_label.config(text="Status: Playing", fg='green')

    def updateStats(self):
        """Update statistics display."""
        self.stats_label.config(text=f"Packets: {self.packets_received} | Frames: {self.frames_received}")

    def on_resolution_change(self, value):
        """Handle resolution change."""
        old_resolution = self.resolution
        self.resolution = value
        
        if value == "720p":
            self.target_width = 1280
            self.target_height = 720
        elif value == "1080p":
            self.target_width = 1920
            self.target_height = 1080
        
        self.resolution_label.config(text=f"Selected: {value}")
        print(f"[CLIENT] Resolution changed from {old_resolution} to {value}")

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
        
        # Set flags to stop threads
        self.running = False
        self.stop_listening.set()
        self.playEvent.set()
        self.display_event.set()
        
        # Send TEARDOWN request if connected
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
        
        # Destroy window
        self.master.destroy()
        print("[CLIENT] Window destroyed")

    def pauseMovie(self):
        """Pause button handler."""
        if self.state == self.PLAYING:
            print("[CLIENT] Pause button clicked")
            self.sendRtspRequest(self.PAUSE)

    def playMovie(self):
        """Play button handler - FIXED VERSION."""
        if self.state == self.READY:
            print("[CLIENT] Play button clicked")
            self.label.configure(text="Starting video playback...")
            
            # **CRITICAL FIX: Clear stop flag FIRST**
            self.stop_listening.clear()
            
            # Reset statistics
            self.packets_received = 0
            self.frames_received = 0
            self.updateStats()
            
            # Create RTP socket if needed
            if not self.rtpSocket:
                self.openRtpPort()
            
            # **FIX: Send PLAY request BEFORE starting listener**
            print("[CLIENT] Sending PLAY request...")
            self.sendRtspRequest(self.PLAY)
            
            # **FIX: Wait a bit for server to start streaming**
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
        """RTP listener - FIXED for multi-packet frames."""
        print("[CLIENT] RTP listener started")
        
        if not self.rtpSocket:
            return
        
        BUFFER_SIZE = 65536
        current_frame = bytearray()
        expecting_frame = False
        packet_count = 0
        frame_count = 0
        last_seq = -1
        
        self.rtpSocket.settimeout(1.0)
        
        try:
            while not self.stop_listening.is_set() and self.state == self.PLAYING:
                try:
                    data, addr = self.rtpSocket.recvfrom(BUFFER_SIZE)
                    
                    if not data or len(data) < 12:
                        continue
                    
                    packet_count += 1
                    self.packets_received += 1
                    
                    # Parse RTP header
                    version = (data[0] >> 6) & 0x03
                    marker = (data[1] >> 7) & 0x01
                    payload_type = data[1] & 0x7F
                    seq_num = (data[2] << 8) | data[3]
                    payload = data[12:]
                    
                    # **DEBUG: First few packets**
                    if packet_count <= 10:
                        print(f"[CLIENT] Packet {packet_count}: Seq={seq_num}, Marker={marker}, Size={len(payload)}")
                    
                    # Check sequence continuity
                    if last_seq != -1 and seq_num != (last_seq + 1) % 65536:
                        print(f"[CLIENT] Sequence gap: {last_seq} -> {seq_num}")
                    
                    last_seq = seq_num
                    
                    # **FIXED FRAME ASSEMBLY LOGIC:**
                    # Look for JPEG start in payload
                    if not expecting_frame:
                        soi_pos = payload.find(b'\xff\xd8')
                        if soi_pos != -1:
                            # Start of new frame
                            print(f"[CLIENT] Starting frame at packet {packet_count}, Seq {seq_num}")
                            current_frame = bytearray(payload[soi_pos:])
                            expecting_frame = True
                        else:
                            # No JPEG start, skip
                            continue
                    else:
                        # Continue building frame
                        current_frame.extend(payload)
                    
                    # Check if frame is complete (marker=1)
                    if marker == 1 and expecting_frame:
                        # Look for JPEG end
                        eoi_pos = current_frame.find(b'\xff\xd9')
                        if eoi_pos != -1:
                            # Complete JPEG frame
                            jpeg_data = bytes(current_frame[:eoi_pos + 2])
                            
                            if jpeg_data[:2] == b'\xff\xd8' and jpeg_data[-2:] == b'\xff\xd9':
                                frame_count += 1
                                self.frames_received += 1
                                
                                print(f"\n[CLIENT] ===== FRAME COMPLETE =====")
                                print(f"[CLIENT] Frame {frame_count} from {packet_count} packets")
                                print(f"[CLIENT] Size: {len(jpeg_data)} bytes")
                                
                                # Save to cache
                                cache_file = self.writeFrame(jpeg_data)
                                if cache_file:
                                    self._last_frame_file = cache_file
                                    self.display_event.set()
                                
                                self.updateStats()
                            else:
                                print(f"[CLIENT] Invalid JPEG in completed frame")
                            
                            # Reset for next frame
                            expecting_frame = False
                            current_frame = bytearray()
                            
                            # Check if next frame starts immediately
                            if eoi_pos + 2 < len(current_frame):
                                remaining = current_frame[eoi_pos + 2:]
                                soi_pos = remaining.find(b'\xff\xd8')
                                if soi_pos != -1:
                                    current_frame = bytearray(remaining[soi_pos:])
                                    expecting_frame = True
                        else:
                            print(f"[CLIENT] WARNING: Marker=1 but no JPEG end")
                    
                    # Progress
                    if packet_count % 100 == 0:
                        print(f"[CLIENT] Received {packet_count} packets, {frame_count} frames")
                        self.updateStats()
                    
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"[CLIENT] Error: {e}")
                    continue
        
        except Exception as e:
            print(f"[CLIENT] Fatal: {e}")
        
        print(f"[CLIENT] Stopped: {packet_count} packets, {frame_count} frames")

    def displayWorker(self):
        """Display worker thread."""
        print("[CLIENT] Display worker started")
        
        frame_count = 0
        
        while not self.stop_listening.is_set() and self.state == self.PLAYING:
            try:
                # Wait for frame or timeout
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
                    # Timeout - check if we should still be running
                    if self.state != self.PLAYING:
                        break
            except Exception as e:
                print(f"[CLIENT] Display worker error: {e}")
        
        print(f"[CLIENT] Display worker stopped. Displayed {frame_count} frames.")

    def updateMovie(self, imageFile):
        """Update movie display."""
        try:
            # Load image
            image = Image.open(imageFile)
            
            if self.display_width > 0 and self.display_height > 0:
                image.thumbnail((self.display_width, self.display_height), Image.Resampling.LANCZOS)
            
            # Convert to PhotoImage
            photo = ImageTk.PhotoImage(image)
            
            # Update in main thread
            self.master.after(0, lambda p=photo: self.updateImage(p))
            
        except Exception as e:
            print(f"[CLIENT] Error updating movie: {e}")

    def updateImage(self, photo):
        """Update image in GUI."""
        self.current_photo = photo
        self.label.configure(image=photo, text="")
        self.label.image = photo
        self.status_label.config(text="Status: Playing video", fg='green')

    def writeFrame(self, data):
        """Write frame to cache file with verification."""
        cache_file = CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT
        
        # Verify JPEG before writing
        if not self.isValidJpeg(data):
            print(f"[CLIENT] WARNING: Invalid JPEG data")
            print(f"  Start: {data[:2].hex() if len(data) >= 2 else 'N/A'}")
            print(f"  End: {data[-2:].hex() if len(data) >= 2 else 'N/A'}")
            print(f"  Size: {len(data)} bytes")
            return None
        
        try:
            with open(cache_file, "wb") as f:
                f.write(data)
            
            # Verify file was written
            import os
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
            
            # Update button states
            self.updateButtonStates()
            return True
        except Exception as e:
            error_msg = f'Connection failed: {e}'
            print(f"[CLIENT] {error_msg}")
            self.label.configure(text=error_msg, fg='red')
            self.status_label.config(text=f"Status: Connection failed - {e}", fg='red')
            return False

    def sendRtspRequest(self, requestCode):
        """Send RTSP request to the server."""
        print(f"[CLIENT] Sending request: {requestCode}")
        
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
            
        else:
            print(f"[CLIENT] Invalid request in current state: {requestCode}, state={self.state}")
            return
        
        print(f"[CLIENT] Sending request:\n{request}")
        
        try:
            self.rtspSocket.send(request.encode())
            print(f"[CLIENT] Request sent successfully")
            
            # Start reply thread for SETUP
            if requestCode == self.SETUP and (not self.reply_thread or not self.reply_thread.is_alive()):
                self.reply_thread = threading.Thread(target=self.recvRtspReply, daemon=True)
                self.reply_thread.start()
                
        except Exception as e:
            print(f"[CLIENT] Error sending request: {e}")
            self.label.configure(text=f"Error sending request: {e}", fg='red')

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
                    
                    # Stop if TEARDOWN acknowledged
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
        """Parse RTSP reply."""
        print(f"[CLIENT] Received reply:\n{data}")
        
        lines = data.strip().split('\n')
        
        if len(lines) < 2:
            return
        
        # Parse status line
        status_line = lines[0]
        if '200 OK' not in status_line:
            print(f"[CLIENT] Server error: {status_line}")
            self.label.configure(text=f"Server error: {status_line}", fg='red')
            return
        
        # Parse headers
        cseq = 0
        session = 0
        for line in lines[1:]:
            if line.startswith('CSeq:'):
                cseq = int(line.split(':')[1].strip())
            elif line.startswith('Session:'):
                session = int(line.split(':')[1].strip())
        
        if cseq != self.rtspSeq:
            print(f"[CLIENT] CSeq mismatch: expected {self.rtspSeq}, got {cseq}")
            return
        
        if session and self.sessionId == 0:
            self.sessionId = session
            print(f"[CLIENT] Session ID set to: {self.sessionId}")
        
        # Update state based on request
        if self.requestSent == self.SETUP:
            self.state = self.READY
            print("[CLIENT] SETUP successful, state=READY")
            self.label.configure(text="Setup complete. Click Play to start.", fg='green')
            self.updateButtonStates()
            
        elif self.requestSent == self.PLAY:
            self.state = self.PLAYING
            print("[CLIENT] PLAY successful, state=PLAYING")
            self.label.configure(text="Playing video...", fg='green')
            self.updateButtonStates()
            
        elif self.requestSent == self.PAUSE:
            self.state = self.READY
            print("[CLIENT] PAUSE successful, state=READY")
            self.label.configure(text="Paused. Click Play to resume.", fg='blue')
            self.stop_listening.set()  # Stop RTP listener
            self.updateButtonStates()
            
        elif self.requestSent == self.TEARDOWN:
            self.teardownAcked = 1
            print("[CLIENT] TEARDOWN acknowledged")
            self.state = self.INIT
            self.label.configure(text="Disconnected. Click Setup to reconnect.", fg='black')
            self.stop_listening.set()  # Stop RTP listener
            self.updateButtonStates()
            
            # Clean up
            if self.rtpSocket:
                try:
                    self.rtpSocket.close()
                    self.rtpSocket = None
                except:
                    pass

    def openRtpPort(self):
        """Open RTP port - FIXED VERSION."""
        try:
            self.rtpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            
            # CRITICAL FIX: Set socket options BEFORE binding
            self.rtpSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # Increase receive buffer
            self.rtpSocket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536 * 4)
            
            # **FIX: Use the server's IP address or 0.0.0.0**
            # Client should bind to 0.0.0.0 to receive from ANY source
            # NOT to 10.232.4.44 (which is the server IP)
            bind_ip = '0.0.0.0'  # Listen on ALL interfaces
            
            print(f"[CLIENT] Binding RTP socket to {bind_ip}:{self.rtpPort}")
            self.rtpSocket.bind((bind_ip, self.rtpPort))
            
            # Set socket to non-blocking with timeout
            self.rtpSocket.settimeout(2.0)  # 2 second timeout
            
            sockname = self.rtpSocket.getsockname()
            print(f"[CLIENT] RTP port {self.rtpPort} opened and bound to {sockname}")
            
            # **DEBUG: Test if we can receive our own packets**
            test_msg = b"RTP_TEST"
            self.rtpSocket.sendto(test_msg, ('127.0.0.1', self.rtpPort))
            print(f"[CLIENT] Sent test packet to 127.0.0.1:{self.rtpPort}")
            
            # Try to receive the test packet
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
        # Check for JPEG start marker (FF D8) and end marker (FF D9)
        return data[:2] == b'\xff\xd8' and data[-2:] == b'\xff\xd9'

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