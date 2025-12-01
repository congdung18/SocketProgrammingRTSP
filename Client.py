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

    # Initiation..
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

        # Create RTP UDP socket (will bind when opening RTP port)
        self.rtpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Reassembly buffer & control
        self.current_buffer = None  # bytearray() when building a frame
        self.buffer_lock = threading.Lock()
        self.last_rendered_frame_id = 0  # monotonic counter for frames rendered
        self.playing_display_thread = None
        self.display_event = threading.Event()

    def createWidgets(self):
        """Build GUI."""
        # Create Setup button
        self.setup = Button(self.master, width=20, padx=3, pady=3)
        self.setup["text"] = "Setup"
        self.setup["command"] = self.setupMovie
        self.setup.grid(row=1, column=0, padx=2, pady=2)

        # Create Play button
        self.start = Button(self.master, width=20, padx=3, pady=3)
        self.start["text"] = "Play"
        self.start["command"] = self.playMovie
        self.start.grid(row=1, column=1, padx=2, pady=2)

        # Create Pause button
        self.pause = Button(self.master, width=20, padx=3, pady=3)
        self.pause["text"] = "Pause"
        self.pause["command"] = self.pauseMovie
        self.pause.grid(row=1, column=2, padx=2, pady=2)

        # Create Teardown button
        self.teardown = Button(self.master, width=20, padx=3, pady=3)
        self.teardown["text"] = "Teardown"
        self.teardown["command"] =  self.exitClient
        self.teardown.grid(row=1, column=3, padx=2, pady=2)

        # Create a label to display the movie
        self.label = Label(self.master, height=19)
        self.label.grid(row=0, column=0, columnspan=4, sticky=W+E+N+S, padx=5, pady=5)

    def setupMovie(self):
        """Setup button handler."""
        if self.state == self.INIT:
            self.sendRtspRequest(self.SETUP)

    def exitClient(self):
        """Teardown button handler."""
        self.sendRtspRequest(self.TEARDOWN)
        # Close GUI window
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
            # Start listening thread for RTP packets
            threading.Thread(target=self.listenRtp, daemon=True).start()
            self.playEvent = threading.Event()
            self.playEvent.clear()
            # Start display worker to show frames at regular pacing (uses display_event)
            self.display_event.clear()
            self.playing_display_thread = threading.Thread(target=self.displayWorker, daemon=True)
            self.playing_display_thread.start()
            self.sendRtspRequest(self.PLAY)

    def listenRtp(self):
        """Listen for RTP packets and reassemble fragments into JPEG frames."""
        while True:
            try:
                data = self.rtpSocket.recv(65536)
                if data:
                    rtpPacket = RtpPacket()
                    rtpPacket.decode(data)

                    payload = rtpPacket.getPayload()

                    # Append payload to current buffer, handling start-of-JPEG if necessary
                    with self.buffer_lock:
                        if self.current_buffer is None:
                            # try to detect SOI in payload
                            if payload.startswith(b'\xff\xd8'):
                                self.current_buffer = bytearray(payload)
                            else:
                                # try to find SOI inside payload
                                idx = payload.find(b'\xff\xd8')
                                if idx != -1:
                                    self.current_buffer = bytearray(payload[idx:])
                                else:
                                    # no SOI -> discard until SOI arrives
                                    continue
                        else:
                            # already building a frame -> append entire payload
                            self.current_buffer.extend(payload)

                        # If buffer ends with EOI (FFD9), complete frame
                        if len(self.current_buffer) >= 2 and self.current_buffer[-2:] == b'\xff\xd9':
                            # Write frame to cache and schedule display
                            frame_bytes = bytes(self.current_buffer)
                            self.current_buffer = None
                            # write frame to file and display
                            imgfile = self.writeFrame(frame_bytes)
                            # update frame number and render immediately (displayWorker will pick it up)
                            self.frameNbr += 1
                            # store path to last cached frame for display
                            self._last_frame_file = imgfile
                            # notify display worker
                            self.display_event.set()
            except socket.timeout:
                # continue loop
                pass
            except OSError:
                # socket closed
                break
            except Exception as e:
                # On any other error, print and continue
                traceback.print_exc()
                continue

            # Stop listening upon requesting PAUSE or TEARDOWN
            if hasattr(self, 'playEvent') and self.playEvent.isSet():
                break

            # Upon receiving ACK for TEARDOWN request, close the RTP socket
            if self.teardownAcked == 1:
                try:
                    self.rtpSocket.shutdown(socket.SHUT_RDWR)
                except:
                    pass
                try:
                    self.rtpSocket.close()
                except:
                    pass
                break

    def writeFrame(self, data):
        """Write the received frame bytes to a temp image file. Return the image file path."""
        cachename = CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT
        with open(cachename, "wb") as file:
            file.write(data)
        return cachename

    def updateMovie(self, imageFile):
        """Update the image file as video frame in the GUI."""
        try:
            photo = ImageTk.PhotoImage(Image.open(imageFile))
            # set a fixed display height (maintain aspect via ImageTk)
            self.label.configure(image = photo, height=288)
            self.label.image = photo
        except Exception:
            traceback.print_exc()

    def displayWorker(self):
        """
        Display worker: waits for frame arrival (display_event) and renders latest frame.
        This decouples network arrival from GUI display and allows simple smoothing.
        """
        while True:
            # wait until a frame available or stop requested
            self.display_event.wait(timeout=1.0)
            # if playEvent set (pause) -> exit display worker
            if hasattr(self, 'playEvent') and self.playEvent.isSet():
                break

            # show last frame file if exists
            if hasattr(self, '_last_frame_file'):
                self.updateMovie(self._last_frame_file)
                # small sleep to control display rate (approx frame pacing)
                time.sleep(0.033)  # ~30 fps

            # clear event until next frame arrives
            self.display_event.clear()

    def connectToServer(self):
        """Connect to the Server. Start a new RTSP/TCP session."""
        self.rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.rtspSocket.connect((self.serverAddr, self.serverPort))
        except:
            tkMessageBox.showwarning('Connection Failed', 'Connection to \'%s\' failed.' %self.serverAddr)

    def sendRtspRequest(self, requestCode):
        """Send RTSP request to the server."""
        # Setup request
        if requestCode == self.SETUP and self.state == self.INIT:
            threading.Thread(target=self.recvRtspReply, daemon=True).start()
            # Update RTSP sequence number.
            self.rtspSeq = 1

            request = (
                f"SETUP {self.fileName} RTSP/1.0\r\n"
                f"CSeq: {self.rtspSeq}\r\n"
                f"Transport: RTP/UDP;client_port={self.rtpPort}\r\n\r\n"
            )

            self.rtspSocket.send(request.encode())
            self.requestSent = self.SETUP

        # Play request
        elif requestCode == self.PLAY and self.state == self.READY:
            self.rtspSeq = self.rtspSeq + 1
            request = (
                f"PLAY {self.fileName} RTSP/1.0\r\n"
                f"CSeq: {self.rtspSeq}\r\n"
                f"Session: {self.sessionId}\r\n\r\n"
            )

            self.rtspSocket.send(request.encode("utf-8"))
            print ('-'*60 + "\nPLAY request sent to Server...\n" + '-'*60)
            self.requestSent = self.PLAY

        # Pause request
        elif requestCode == self.PAUSE and self.state == self.PLAYING:
            self.rtspSeq = self.rtspSeq + 1
            request = (
                f"PAUSE {self.fileName} RTSP/1.0\r\n"
                f"CSeq: {self.rtspSeq}\r\n"
                f"Session: {self.sessionId}\r\n\r\n"
            )

            self.rtspSocket.send(request.encode("utf-8"))
            print ('-'*60 + "\nPAUSE request sent to Server...\n" + '-'*60)
            self.requestSent = self.PAUSE

        # Teardown request
        elif requestCode == self.TEARDOWN and not self.state == self.INIT:
            self.rtspSeq = self.rtspSeq + 1
            request = (
                f"TEARDOWN {self.fileName} RTSP/1.0\r\n"
                f"CSeq: {self.rtspSeq}\r\n"
                f"Session: {self.sessionId}\r\n\r\n"
            )

            self.rtspSocket.send(request.encode("utf-8"))
            print ('-'*60 + "\nTEARDOWN request sent to Server...\n" + '-'*60)
            self.requestSent = self.TEARDOWN
        else:
            return

        print('\nData sent:\n' + request)

    def recvRtspReply(self):
        """Receive RTSP reply from the server."""
        while True:
            reply = self.rtspSocket.recv(1024)

            if reply:
                self.parseRtspReply(reply.decode("utf-8"))

            # Close the RTSP socket upon requesting Teardown
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
        lines = data.split('\n')
        seqNum = int(lines[1].split(' ')[1])

        # Process only if the server reply's sequence number is the same as the request's
        if seqNum == self.rtspSeq:
            session = int(lines[2].split(' ')[1])
            # New RTSP session ID
            if self.sessionId == 0:
                self.sessionId = session

            # Process only if the session ID is the same
            if self.sessionId == session:
                if int(lines[0].split(' ')[1]) == 200:
                    if self.requestSent == self.SETUP:
                        # Update RTSP state.
                        print ("Updating RTSP state...")
                        self.state = self.READY
                        # Open RTP port.
                        print ("Setting Up RtpPort for Video Stream")
                        self.openRtpPort()

                    elif self.requestSent == self.PLAY:
                        self.state = self.PLAYING
                        print ('-'*60 + "\nClient is PLAYING...\n" + '-'*60)

                    elif self.requestSent == self.PAUSE:
                        self.state = self.READY
                        # The play thread exits. A new thread is created on resume.
                        if hasattr(self, 'playEvent'):
                            self.playEvent.set()
                        # stop display worker
                        self.display_event.set()

                    elif self.requestSent == self.TEARDOWN:
                        # Flag the teardownAcked to close the socket.
                        self.teardownAcked = 1

    def openRtpPort(self):
        """Open RTP socket binded to a specified port."""
        # Set the timeout value of the socket to 0.5sec
        self.rtpSocket.settimeout(0.5)

        try:
            # Bind to all interfaces on the RTP port so server can send to client
            self.rtpSocket.bind(('', self.rtpPort))
            print ("Bind RtpPort Success")
        except Exception as e:
            tkMessageBox.showwarning('Unable to Bind', 'Unable to bind PORT=%d (%s)' % (self.rtpPort, e))

    def handler(self):
        """Handler on explicitly closing the GUI window."""
        self.pauseMovie()
        if tkMessageBox.askokcancel("Quit?", "Are you sure you want to quit?"):
            self.exitClient()
        else: # When the user presses cancel, resume playing.
            self.playMovie()
