# from random import randint
# import sys, traceback, threading, socket

# from VideoStream import VideoStream
# from RtpPacket import RtpPacket

# class ServerWorker:
#     SETUP = 'SETUP'
#     PLAY = 'PLAY'
#     PAUSE = 'PAUSE'
#     TEARDOWN = 'TEARDOWN'
    
#     INIT = 0
#     READY = 1
#     PLAYING = 2
#     state = INIT

#     OK_200 = 0
#     FILE_NOT_FOUND_404 = 1
#     CON_ERR_500 = 2
    
#     clientInfo = {}
    
#     def __init__(self, clientInfo):
#         self.clientInfo = clientInfo
        
#     def run(self):
#         threading.Thread(target=self.recvRtspRequest).start()
    
#     def recvRtspRequest(self):
#         connSocket = self.clientInfo['rtspSocket'][0]
#         while True:            
#             data = connSocket.recv(256)
#             if data:
#                 print("Data received:\n" + data.decode("utf-8"))
#                 self.processRtspRequest(data.decode("utf-8"))
    
#     # ---------------------------
#     # CHỈNH SỬA CHÍNH NẰM Ở ĐÂY
#     # ---------------------------
#     def processRtspRequest(self, data):
#         request = data.split('\n')

#         # Dòng 1: "SETUP movie.Mjpeg RTSP/1.0"
#         line1 = request[0].split(" ")
#         requestType = line1[0]
#         filename = line1[1]

#         # Dòng 2: "CSeq: 1"
#         seq = request[1].split(" ")[1]

#         if requestType == self.SETUP:
#             if self.state == self.INIT:
#                 print("processing SETUP\n")
                
#                 try:
#                     self.clientInfo['videoStream'] = VideoStream(filename)
#                     self.state = self.READY
#                 except IOError:
#                     self.replyRtsp(self.FILE_NOT_FOUND_404, seq)
#                     return

#                 # Parse cổng RTP từ dòng Transport
#                 # "Transport: RTP/UDP;client_port=8999"
#                 transportLine = request[2].strip()
#                 if "client_port=" in transportLine:
#                     self.clientInfo['rtpPort'] = transportLine.split("client_port=")[1].strip()
#                 else:
#                     print("ERROR: cannot parse client_port")
#                     return

#                 print("RTP port from client =", self.clientInfo['rtpPort'])

#                 # Tạo session ID
#                 self.clientInfo['session'] = randint(100000, 999999)

#                 # Gửi phản hồi
#                 self.replyRtsp(self.OK_200, seq)

#         elif requestType == self.PLAY:
#             if self.state == self.READY:
#                 print("processing PLAY\n")
#                 self.state = self.PLAYING

#                 # Mở socket gửi RTP
#                 self.clientInfo["rtpSocket"] = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

#                 self.replyRtsp(self.OK_200, seq)

#                 # Thread gửi frame
#                 self.clientInfo['event'] = threading.Event()
#                 self.clientInfo['worker'] = threading.Thread(target=self.sendRtp)
#                 self.clientInfo['worker'].start()

#         elif requestType == self.PAUSE:
#             if self.state == self.PLAYING:
#                 print("processing PAUSE\n")
#                 self.state = self.READY
#                 self.clientInfo['event'].set()
#                 self.replyRtsp(self.OK_200, seq)

#         elif requestType == self.TEARDOWN:
#             print("processing TEARDOWN\n")

#             if 'event' in self.clientInfo:
#                 self.clientInfo['event'].set()

#             self.replyRtsp(self.OK_200, seq)

#             if "rtpSocket" in self.clientInfo:
#                 self.clientInfo['rtpSocket'].close()
    
#     # ------------------------
#     # KHÔNG CHỈNH LOGIC DƯỚI
#     # ------------------------
#     def sendRtp(self):
#         while True:
#             self.clientInfo['event'].wait(0.05)
#             if self.clientInfo['event'].isSet():
#                 break 
                
#             data = self.clientInfo['videoStream'].nextFrame()
#             if data: 
#                 frameNumber = self.clientInfo['videoStream'].frameNbr()
#                 try:
#                     address = self.clientInfo['rtspSocket'][1][0]
#                     port = int(self.clientInfo['rtpPort'])
#                     self.clientInfo['rtpSocket'].sendto(
#                         self.makeRtp(data, frameNumber), 
#                         (address, port)
#                     )
#                 except:
#                     print("Connection Error")

#     def makeRtp(self, payload, frameNbr):
#         version = 2
#         padding = 0
#         extension = 0
#         cc = 0
#         marker = 0
#         pt = 26 
#         seqnum = frameNbr
#         ssrc = 0 
        
#         rtpPacket = RtpPacket()
#         rtpPacket.encode(
#             version, padding, extension, cc,
#             seqnum, marker, pt, ssrc, payload
#         )
#         return rtpPacket.getPacket()
        
#     def replyRtsp(self, code, seq):
#         if code == self.OK_200:
#             reply = (
#                 "RTSP/1.0 200 OK\n"
#                 f"CSeq: {seq}\n"
#                 f"Session: {self.clientInfo['session']}"
#             )
#             connSocket = self.clientInfo['rtspSocket'][0]
#             connSocket.send(reply.encode())

#         elif code == self.FILE_NOT_FOUND_404:
#             print("404 NOT FOUND")
#         elif code == self.CON_ERR_500:
#             print("500 CONNECTION ERROR")

# ServerWorker.py
# ServerWorker.py
from random import randint
import sys, traceback, threading, socket, time

from VideoStream import VideoStream
from RtpPacket import RtpPacket

class ServerWorker:
    SETUP = 'SETUP'
    PLAY = 'PLAY'
    PAUSE = 'PAUSE'
    TEARDOWN = 'TEARDOWN'

    INIT = 0
    READY = 1
    PLAYING = 2
    state = INIT

    OK_200 = 0
    FILE_NOT_FOUND_404 = 1
    CON_ERR_500 = 2

    clientInfo = {}

    def __init__(self, clientInfo):
        self.clientInfo = clientInfo

        # packet sequence counter per connection (wrap at 65535)
        self.packetSeq = randint(0, 65535)

    def run(self):
        threading.Thread(target=self.recvRtspRequest).start()

    def recvRtspRequest(self):
        connSocket = self.clientInfo['rtspSocket'][0]
        while True:
            data = connSocket.recv(256)
            if data:
                print("Data received:\n" + data.decode("utf-8"))
                self.processRtspRequest(data.decode("utf-8"))

    def processRtspRequest(self, data):
        request = data.split('\n')

        # Dòng 1: "SETUP movie.Mjpeg RTSP/1.0"
        line1 = request[0].split(" ")
        requestType = line1[0]
        filename = line1[1]

        # Dòng 2: "CSeq: 1"
        seq = request[1].split(" ")[1]

        if requestType == self.SETUP:
            if self.state == self.INIT:
                print("processing SETUP\n")

                try:
                    self.clientInfo['videoStream'] = VideoStream(filename)
                    self.state = self.READY
                except IOError:
                    self.replyRtsp(self.FILE_NOT_FOUND_404, seq)
                    return

                # Parse cổng RTP từ dòng Transport
                # "Transport: RTP/UDP;client_port=8999"
                transportLine = request[2].strip()
                if "client_port=" in transportLine:
                    self.clientInfo['rtpPort'] = transportLine.split("client_port=")[1].strip()
                else:
                    print("ERROR: cannot parse client_port")
                    return

                print("RTP port from client =", self.clientInfo['rtpPort'])

                # Tạo session ID
                self.clientInfo['session'] = randint(100000, 999999)

                # Gửi phản hồi
                self.replyRtsp(self.OK_200, seq)

        elif requestType == self.PLAY:
            if self.state == self.READY:
                print("processing PLAY\n")
                self.state = self.PLAYING

                # Mở socket gửi RTP
                self.clientInfo["rtpSocket"] = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

                self.replyRtsp(self.OK_200, seq)

                # Thread gửi frame
                self.clientInfo['event'] = threading.Event()
                self.clientInfo['worker'] = threading.Thread(target=self.sendRtp)
                self.clientInfo['worker'].start()

        elif requestType == self.PAUSE:
            if self.state == self.PLAYING:
                print("processing PAUSE\n")
                self.state = self.READY
                self.clientInfo['event'].set()
                self.replyRtsp(self.OK_200, seq)

        elif requestType == self.TEARDOWN:
            print("processing TEARDOWN\n")

            if 'event' in self.clientInfo:
                self.clientInfo['event'].set()

            self.replyRtsp(self.OK_200, seq)

            if "rtpSocket" in self.clientInfo:
                self.clientInfo['rtpSocket'].close()

    def sendRtp(self):
        """
        Send RTP packets with fragmentation for large frames.
        - Use MTU ~1400 bytes for payload per UDP packet.
        - Set marker bit = 1 on last fragment of a frame.
        - packet sequence number increments per RTP packet.
        """
        MTU = 1400
        while True:
            # wait small interval for frame pacing (non-blocking)
            self.clientInfo['event'].wait(0.01)
            if self.clientInfo['event'].isSet():
                break

            data = self.clientInfo['videoStream'].nextFrame()
            if data:
                frameNumber = self.clientInfo['videoStream'].frameNbr()

                # target address is client IP from RTSP socket tuple
                try:
                    address = self.clientInfo['rtspSocket'][1][0]
                    port = int(self.clientInfo['rtpPort'])
                except Exception as e:
                    print("Cannot get client address/port:", e)
                    continue

                # Fragment the frame payload into chunks of size MTU
                total_len = len(data)
                offset = 0
                # compute how many fragments
                fragments = []
                while offset < total_len:
                    chunk = data[offset:offset + MTU]
                    fragments.append(chunk)
                    offset += MTU

                # Send all fragments, set marker=1 on last fragment
                for i, chunk in enumerate(fragments):
                    is_last = (i == len(fragments) - 1)
                    # choose a packet sequence number and increment (wrap at 65535)
                    self.packetSeq = (self.packetSeq + 1) % 256
                    seqnum = self.packetSeq
                    marker = 1 if is_last else 0

                    # Payload is raw JPEG chunk (no extra headers) -- client will reassemble using JPEG markers
                    rtpPacket = RtpPacket()
                    # Use pt=26 as before, ssrc left as 0
                    rtpPacket.encode(2, 0, 0, 0, seqnum, marker, 26, 0, chunk)
                    try:
                        self.clientInfo['rtpSocket'].sendto(rtpPacket.getPacket(), (address, port))
                    except:
                        print("Connection Error while sending RTP packet")
                        break

                # frame pacing: short sleep to approximate frame rate (e.g., 30fps -> ~33ms)
                # The server sends all fragments of a frame quickly, then waits
                # to maintain frame rate. Adjust as needed.
                time.sleep(0.033)  # ~30 fps

    def replyRtsp(self, code, seq):
        """
        Send RTSP reply. Keeps the same behavior as original lab:
        - if code == OK_200 -> send "RTSP/1.0 200 OK" with CSeq and Session
        - other codes print error messages
        """
        if code == self.OK_200:
            # Use the session created in clientInfo (if any)
            session = self.clientInfo.get('session', 0)
            reply = (
                "RTSP/1.0 200 OK\n"
                f"CSeq: {seq}\n"
                f"Session: {session}"
            )
            try:
                connSocket = self.clientInfo['rtspSocket'][0]
                connSocket.send(reply.encode())
            except Exception as e:
                print("Error sending RTSP reply:", e)

        elif code == self.FILE_NOT_FOUND_404:
            print("404 NOT FOUND")
        elif code == self.CON_ERR_500:
            print("500 CONNECTION ERROR")

