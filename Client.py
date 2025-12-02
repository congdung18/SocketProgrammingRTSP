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
        self.createWidgets()
        self.serverAddr = serveraddr
        self.serverPort = int(serverport)
        self.rtpPort = int(rtpport)
        self.fileName = filename
        self.rtspSeq = 0
        self.sessionId = 0
        self.requestSent = -1
        self.teardownAcked = 0
        self.connectToServer()
        self.frameNbr = 0

        # Video display properties
        self.target_width = 1280  # 720p width
        self.target_height = 720  # 720p height
        
        # Current display size
        self.display_width = 1280
        self.display_height = 720
        
        # Create RTP UDP socket
        self.rtpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Reassembly buffer & control
        self.current_buffer = None
        self.buffer_lock = threading.Lock()
        self.last_rendered_frame_id = 0
        self.playing_display_thread = None
        self.display_event = threading.Event()
        
        # Track current photo to prevent garbage collection
        self.current_photo = None

    def createWidgets(self):
        """Build responsive GUI."""
        # Configure grid weights for responsive design
        self.master.grid_rowconfigure(0, weight=1)  # Video label expands
        self.master.grid_rowconfigure(1, weight=0)  # Button row fixed
        self.master.grid_columnconfigure(0, weight=1)
        self.master.grid_columnconfigure(1, weight=1)
        self.master.grid_columnconfigure(2, weight=1)
        self.master.grid_columnconfigure(3, weight=1)

        # Create a label to display the movie (resizable)
        self.label = Label(self.master, bg='black')
        self.label.grid(row=0, column=0, columnspan=4, sticky='nsew', padx=5, pady=5)
        
        # Bind resize event
        self.master.bind('<Configure>', self.on_window_resize)

        # Create Setup button
        self.setup = Button(self.master, width=15, padx=3, pady=3, font=('Arial', 10))
        self.setup["text"] = "Setup"
        self.setup["command"] = self.setupMovie
        self.setup.grid(row=1, column=0, padx=10, pady=10, sticky='ew')

        # Create Play button
        self.start = Button(self.master, width=15, padx=3, pady=3, font=('Arial', 10))
        self.start["text"] = "Play"
        self.start["command"] = self.playMovie
        self.start.grid(row=1, column=1, padx=10, pady=10, sticky='ew')

        # Create Pause button
        self.pause = Button(self.master, width=15, padx=3, pady=3, font=('Arial', 10))
        self.pause["text"] = "Pause"
        self.pause["command"] = self.pauseMovie
        self.pause.grid(row=1, column=2, padx=10, pady=10, sticky='ew')

        # Create Teardown button
        self.teardown = Button(self.master, width=15, padx=3, pady=3, font=('Arial', 10))
        self.teardown["text"] = "Teardown"
        self.teardown["command"] = self.exitClient
        self.teardown.grid(row=1, column=3, padx=10, pady=10, sticky='ew')

    def on_window_resize(self, event):
        """Handle window resize events."""
        if event.widget == self.master:
            # Get new window size
            new_width = event.width
            new_height = event.height
            
            # Update display dimensions (account for button row ~50px)
            self.display_width = new_width - 20  # Account for padding
            self.display_height = new_height - 120  # Account for button row and padding
            
            # Keep aspect ratio for 720p (16:9)
            if self.display_width > 0 and self.display_height > 0:
                # Calculate target size maintaining 16:9 aspect ratio
                target_ratio = 16/9
                current_ratio = self.display_width / self.display_height
                
                if current_ratio > target_ratio:
                    # Too wide, adjust width
                    self.display_width = int(self.display_height * target_ratio)
                else:
                    # Too tall, adjust height
                    self.display_height = int(self.display_width / target_ratio)
                
                # Ensure minimum size
                self.display_width = max(320, self.display_width)
                self.display_height = max(180, self.display_height)

    def setupMovie(self):
        """Setup button handler."""
        if self.state == self.INIT:
            self.sendRtspRequest(self.SETUP)

    def exitClient(self):
        """Teardown button handler."""
        self.sendRtspRequest(self.TEARDOWN)
        try:
            os.remove(CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT)
        except:
            pass
        self.master.destroy()

    def pauseMovie(self):
        """Pause button handler."""
        if self.state == self.PLAYING:
            self.sendRtspRequest(self.PAUSE)

    def playMovie(self):
        """Play button handler."""
        if self.state == self.READY:
            threading.Thread(target=self.listenRtp, daemon=True).start()
            self.playEvent = threading.Event()
            self.playEvent.clear()
            self.display_event.clear()
            self.playing_display_thread = threading.Thread(target=self.displayWorker, daemon=True)
            self.playing_display_thread.start()
            self.sendRtspRequest(self.PLAY)

    def listenRtp(self):
        """Optimized RTP listener."""
        BUFFER_SIZE = 65536 * 2
        try:
            self.rtpSocket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, BUFFER_SIZE)
        except:
            print("[DEBUG] Could not set socket buffer size")
        
        self.current_seq = 0
        packet_count = 0
        frame_count = 0
        
        print("[DEBUG] RTP listener started")
        
        while True:
            try:
                data = self.rtpSocket.recv(BUFFER_SIZE)
                packet_count += 1
                
                if packet_count % 100 == 0:
                    print(f"[DEBUG] Received {packet_count} packets")
                
                if not data or len(data) < 12:
                    continue
                        
                rtpPacket = RtpPacket()
                rtpPacket.decode(data)
                
                seq_num = rtpPacket.seqNum()
                marker = rtpPacket.getMarker()
                payload = rtpPacket.getPayload()
                payload_size = len(payload)
                
                if packet_count % 50 == 0:
                    print(f"[DEBUG] Packet {packet_count}: seq={seq_num}, marker={marker}, payload_size={payload_size}")
                
                with self.buffer_lock:
                    if self.current_buffer is None:
                        soi_pos = payload.find(b'\xff\xd8')
                        if soi_pos != -1:
                            self.current_buffer = bytearray(payload[soi_pos:])
                            self.current_seq = seq_num
                            if packet_count % 20 == 0:
                                print(f"[DEBUG] Started new frame buffer at seq {seq_num}")
                        else:
                            if packet_count % 100 == 0:
                                print(f"[DEBUG] No SOI found in payload")
                    else:
                        expected_seq = (self.current_seq + 1) % 65536
                        if seq_num != expected_seq and seq_num != self.current_seq:
                            print(f"[WARN] Packet loss: expected {expected_seq}, got {seq_num}")
                        
                        self.current_buffer.extend(payload)
                        self.current_seq = seq_num
                    
                    if marker == 1 and self.current_buffer:
                        buffer_len = len(self.current_buffer)
                        eoi_pos = self.current_buffer.find(b'\xff\xd9')
                        if eoi_pos != -1:
                            frame_data = bytes(self.current_buffer[:eoi_pos + 2])
                            
                            if frame_data[:2] == b'\xff\xd8':
                                frame_count += 1
                                print(f"[DEBUG] Completed frame {frame_count}, size: {len(frame_data)} bytes")
                                
                                imgfile = self.writeFrame(frame_data)
                                self.frameNbr += 1
                                self._last_frame_file = imgfile
                                self.display_event.set()
                            else:
                                print(f"[WARN] Frame doesn't start with SOI")
                            
                            if eoi_pos + 2 < buffer_len:
                                remaining = self.current_buffer[eoi_pos + 2:]
                                soi_pos = remaining.find(b'\xff\xd8')
                                if soi_pos != -1:
                                    self.current_buffer = bytearray(remaining[soi_pos:])
                                else:
                                    self.current_buffer = None
                            else:
                                self.current_buffer = None
                        else:
                            print(f"[WARN] Marker=1 but no EOI found in buffer")
                            
            except socket.timeout:
                continue
            except Exception as e:
                print(f"[ERROR] in listenRtp: {e}")
                traceback.print_exc()
                continue

    def displayWorker(self):
        """Display worker with adaptive frame rate."""
        TARGET_FPS = 30
        FRAME_TIME = 1.0 / TARGET_FPS
        last_display_time = 0
        
        while True:
            current_time = time.time()
            time_to_wait = max(0, last_display_time + FRAME_TIME - current_time)
            
            signaled = self.display_event.wait(timeout=time_to_wait)
            
            if hasattr(self, 'playEvent') and self.playEvent.isSet():
                break
            
            if signaled or (current_time - last_display_time >= FRAME_TIME):
                if hasattr(self, '_last_frame_file'):
                    try:
                        threading.Thread(
                            target=self.updateMovieAsync,
                            args=(self._last_frame_file,),
                            daemon=True
                        ).start()
                    except Exception:
                        traceback.print_exc()
                
                last_display_time = time.time()
                self.display_event.clear()

    def updateMovieAsync(self, imageFile):
        """Async image update with high-quality resizing."""
        try:
            image = Image.open(imageFile)
            
            # Resize to fit display area while maintaining aspect ratio
            if self.display_width > 0 and self.display_height > 0:
                # Use LANCZOS for high-quality downsampling
                image.thumbnail((self.display_width, self.display_height), Image.Resampling.LANCZOS)
            
            # Convert to PhotoImage
            photo = ImageTk.PhotoImage(image)
            
            # Update GUI in main thread
            self.master.after(0, lambda: self.updateImage(photo))
        except Exception as e:
            print(f"Error loading image: {e}")

    def updateImage(self, photo):
        """Thread-safe GUI update with 720p display."""
        # Store reference to prevent garbage collection
        self.current_photo = photo
        
        # Update label with proper sizing
        self.label.configure(
            image=photo,
            width=self.display_width,
            height=self.display_height
        )
        self.label.image = photo

    def writeFrame(self, data):
        """Write frame to cache file."""
        cachename = CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT
        with open(cachename, "wb") as file:
            file.write(data)
        return cachename

    def connectToServer(self):
        """Connect to the Server."""
        print(f"[CLIENT] Connecting to {self.serverAddr}:{self.serverPort}")
        self.rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.rtspSocket.settimeout(5.0)
        
        try:
            self.rtspSocket.connect((self.serverAddr, self.serverPort))
            print(f"[CLIENT] Connected successfully to server")
            self.rtspSocket.settimeout(None)
        except socket.timeout:
            tkMessageBox.showerror('Connection Timeout', f'Connection to {self.serverAddr}:{self.serverPort} timed out.')
            return
        except ConnectionRefusedError:
            tkMessageBox.showerror('Connection Refused', f'Server at {self.serverAddr}:{self.serverPort} refused connection.')
            return
        except Exception as e:
            tkMessageBox.showwarning('Connection Failed', f'Connection to {self.serverAddr}:{self.serverPort} failed: {e}')
    
    def sendRtspRequest(self, requestCode):
        """Send RTSP request to the server."""
        print(f"[CLIENT] Sending request code: {requestCode}")
        
        if requestCode == self.SETUP and self.state == self.INIT:
            print("[CLIENT] Starting RTSP reply thread...")
            threading.Thread(target=self.recvRtspReply, daemon=True).start()
            self.rtspSeq = 1

            request = (
                f"SETUP {self.fileName} RTSP/1.0\r\n"
                f"CSeq: {self.rtspSeq}\r\n"
                f"Transport: RTP/UDP;client_port={self.rtpPort}\r\n\r\n"
            )

            print(f"[CLIENT] Sending SETUP request:")
            print(request)
            
            try:
                sent = self.rtspSocket.send(request.encode())
                print(f"[CLIENT] Sent {sent} bytes")
                self.requestSent = self.SETUP
            except Exception as e:
                print(f"[CLIENT ERROR] Failed to send SETUP: {e}")

        elif requestCode == self.PLAY and self.state == self.READY:
            print("[CLIENT] Sending PLAY request...")
            self.rtspSeq = self.rtspSeq + 1
            request = (
                f"PLAY {self.fileName} RTSP/1.0\r\n"
                f"CSeq: {self.rtspSeq}\r\n"
                f"Session: {self.sessionId}\r\n\r\n"
            )

            print(f"[CLIENT] Sending PLAY request:")
            print(request)
            
            try:
                self.rtspSocket.send(request.encode("utf-8"))
                self.requestSent = self.PLAY
            except Exception as e:
                print(f"[CLIENT ERROR] Failed to send PLAY: {e}")

        elif requestCode == self.PAUSE and self.state == self.PLAYING:
            print("[CLIENT] Sending PAUSE request...")
            self.rtspSeq = self.rtspSeq + 1
            request = (
                f"PAUSE {self.fileName} RTSP/1.0\r\n"
                f"CSeq: {self.rtspSeq}\r\n"
                f"Session: {self.sessionId}\r\n\r\n"
            )

            print(f"[CLIENT] Sending PAUSE request:")
            print(request)
            
            try:
                self.rtspSocket.send(request.encode("utf-8"))
                self.requestSent = self.PAUSE
            except Exception as e:
                print(f"[CLIENT ERROR] Failed to send PAUSE: {e}")

        elif requestCode == self.TEARDOWN and not self.state == self.INIT:
            print("[CLIENT] Sending TEARDOWN request...")
            self.rtspSeq = self.rtspSeq + 1
            request = (
                f"TEARDOWN {self.fileName} RTSP/1.0\r\n"
                f"CSeq: {self.rtspSeq}\r\n"
                f"Session: {self.sessionId}\r\n\r\n"
            )

            print(f"[CLIENT] Sending TEARDOWN request:")
            print(request)
            
            try:
                self.rtspSocket.send(request.encode("utf-8"))
                self.requestSent = self.TEARDOWN
            except Exception as e:
                print(f"[CLIENT ERROR] Failed to send TEARDOWN: {e}")
        else:
            print(f"[CLIENT] Invalid request: code={requestCode}, state={self.state}")
            return

    def recvRtspReply(self):
        """Receive RTSP reply from the server."""
        while True:
            reply = self.rtspSocket.recv(1024)

            if reply:
                self.parseRtspReply(reply.decode("utf-8"))

            if self.requestSent == self.TEARDOWN:
                try:
                    self.rtspSocket.shutdown(socket.SHUT_RDWR)
                except:
                    pass
                try:
                    self.rtspSocket.close()
                except:
                    pass
                break

    def parseRtspReply(self, data):
        """Parse the RTSP reply from the server."""
        print(f"[CLIENT] Received RTSP reply:")
        print(data)
        print("-" * 60)
        
        lines = data.split('\n')
        
        if len(lines) < 2:
            print(f"[CLIENT ERROR] Malformed RTSP reply: {data}")
            return
        
        try:
            status_line = lines[0]
            status_code = int(status_line.split(' ')[1])
            print(f"[CLIENT] Status code: {status_code}")
            
            cseq_line = lines[1]
            seqNum = int(cseq_line.split(' ')[1])
            print(f"[CLIENT] Server CSeq: {seqNum}, Client CSeq: {self.rtspSeq}")
            
            if seqNum == self.rtspSeq:
                if len(lines) > 2 and lines[2].startswith('Session:'):
                    session = int(lines[2].split(' ')[1])
                    print(f"[CLIENT] Session ID: {session}")
                    
                    if self.sessionId == 0:
                        self.sessionId = session
                        print(f"[CLIENT] Set session ID to: {self.sessionId}")

                    if self.sessionId == session:
                        if status_code == 200:
                            if self.requestSent == self.SETUP:
                                print("[CLIENT] SETUP successful, changing state to READY")
                                self.state = self.READY
                                print("[CLIENT] Setting Up RtpPort for Video Stream")
                                self.openRtpPort()

                            elif self.requestSent == self.PLAY:
                                self.state = self.PLAYING
                                print('[CLIENT] PLAY successful, changing state to PLAYING')

                            elif self.requestSent == self.PAUSE:
                                self.state = self.READY
                                print('[CLIENT] PAUSE successful, changing state to READY')
                                if hasattr(self, 'playEvent'):
                                    self.playEvent.set()
                                self.display_event.set()

                            elif self.requestSent == self.TEARDOWN:
                                self.teardownAcked = 1
                                print('[CLIENT] TEARDOWN successful')
                        else:
                            print(f"[CLIENT ERROR] Server returned error: {status_line}")
                else:
                    print(f"[CLIENT] No session line in reply")
            else:
                print(f"[CLIENT WARN] Sequence mismatch: server={seqNum}, client={self.rtspSeq}")
                
        except Exception as e:
            print(f"[CLIENT ERROR] Failed to parse RTSP reply: {e}")
            traceback.print_exc()

    def openRtpPort(self):
        """Open RTP socket."""
        self.rtpSocket.settimeout(0.5)

        try:
            self.rtpSocket.bind(('', self.rtpPort))
            print("Bind RtpPort Success")
        except Exception as e:
            tkMessageBox.showwarning('Unable to Bind', 'Unable to bind PORT=%d (%s)' % (self.rtpPort, e))

    def handler(self):
        """Handler on closing the GUI window."""
        self.pauseMovie()
        if tkMessageBox.askokcancel("Quit?", "Are you sure you want to quit?"):
            self.exitClient()
        else:
            self.playMovie()


if __name__ == "__main__":
    try:
        serverAddr = sys.argv[1]
        serverPort = sys.argv[2]
        rtpPort = sys.argv[3]
        fileName = sys.argv[4]
    except:
        print("[Usage: ClientLauncher.py Server_name Server_port RTP_port Video_file]\n")
    
    root = Tk()
    
    # Set initial window size for 720p
    root.geometry("1280x800")  # Extra height for buttons
    root.minsize(640, 480)     # Minimum size
    
    app = Client(root, serverAddr, serverPort, rtpPort, fileName)
    app.master.title("RTPClient - 720p Stream")
    root.mainloop()