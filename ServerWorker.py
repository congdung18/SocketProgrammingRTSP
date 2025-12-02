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
        print(f"[SERVER] New connection from {self.clientInfo['rtspSocket'][1]}")
        
        while True:
            try:
                data = connSocket.recv(256)
                if data:
                    data_str = data.decode("utf-8")
                    print(f"[SERVER] Received data ({len(data)} bytes):")
                    print("=" * 50)
                    print(data_str)
                    print("=" * 50)
                    self.processRtspRequest(data_str)
                else:
                    print("[SERVER] Client disconnected")
                    break
            except UnicodeDecodeError:
                print(f"[SERVER] Received binary data: {data[:50]}...")
            except Exception as e:
                print(f"[SERVER ERROR] in recvRtspRequest: {e}")
                break

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
        print("[SERVER] === STARTING ENHANCED RTP STREAM ===")
        
        client_addr = self.clientInfo['rtspSocket'][1][0]
        client_port = int(self.clientInfo['rtpPort'])
        
        print(f"[SERVER] Client: {client_addr}:{client_port}")
        
        # Test UDP
        try:
            self.clientInfo['rtpSocket'].sendto(b"TEST", (client_addr, client_port))
            print("[SERVER] UDP test successful")
        except Exception as e:
            print(f"[SERVER] UDP error: {e}")
            return
        
        frame_count = 0
        max_frames = 1000  # Tăng số frame tối đa
        
        try:
            while frame_count < max_frames:
                if self.clientInfo['event'].isSet():
                    print("[SERVER] Stream stopped by event")
                    break
                
                print(f"\n[SERVER] Attempting to read frame {frame_count + 1}...")
                
                # Đọc frame
                try:
                    frame_data = self.clientInfo['videoStream'].nextFrame()
                    
                    if frame_data is None:
                        print("[SERVER] No frame data returned")
                        
                        # Thử đọc lại 3 lần
                        for retry in range(3):
                            print(f"[SERVER] Retry {retry + 1}...")
                            frame_data = self.clientInfo['videoStream'].nextFrame()
                            if frame_data:
                                print(f"[SERVER] Success on retry {retry + 1}")
                                break
                            time.sleep(0.01)  # Chờ một chút
                        
                        if frame_data is None:
                            print("[SERVER] Giving up after retries - END OF STREAM")
                            break
                    
                except Exception as e:
                    print(f"[SERVER] Error reading frame: {e}")
                    import traceback
                    traceback.print_exc()
                    break
                
                frame_count += 1
                
                # DEBUG thông tin frame
                print(f"[SERVER] Frame {frame_count}: {len(frame_data)} bytes")
                print(f"[SERVER] JPEG starts with: {frame_data[:4].hex() if len(frame_data) >= 4 else 'N/A'}")
                
                # Tạo và gửi RTP packet
                self.packetSeq = (self.packetSeq + 1) % 65536
                
                try:
                    # Chia frame nếu lớn
                    max_payload = 1400
                    
                    if len(frame_data) <= max_payload:
                        # Gửi 1 packet
                        packet = RtpPacket.create(
                            seqnum=self.packetSeq,
                            payload=frame_data,
                            marker=True
                        )
                        self.clientInfo['rtpSocket'].sendto(packet, (client_addr, client_port))
                        print(f"[SERVER] Sent packet {self.packetSeq}")
                    else:
                        # Chia thành nhiều packet
                        offset = 0
                        packet_count = 0
                        
                        while offset < len(frame_data):
                            chunk_size = min(max_payload, len(frame_data) - offset)
                            chunk = frame_data[offset:offset + chunk_size]
                            marker = (offset + chunk_size >= len(frame_data))
                            
                            packet = RtpPacket.create(
                                seqnum=self.packetSeq,
                                payload=chunk,
                                marker=marker
                            )
                            self.clientInfo['rtpSocket'].sendto(packet, (client_addr, client_port))
                            
                            packet_count += 1
                            self.packetSeq = (self.packetSeq + 1) % 65536
                            offset += chunk_size
                        
                        print(f"[SERVER] Sent {packet_count} packets for frame {frame_count}")
                    
                except Exception as e:
                    print(f"[SERVER] Error creating/sending packet: {e}")
                    import traceback
                    traceback.print_exc()
                    continue
                
                # Điều chỉnh framerate
                time.sleep(0.033)  # ~30fps
        
        except Exception as e:
            print(f"[SERVER] Fatal error: {e}")
            import traceback
            traceback.print_exc()
        
        print(f"\n[SERVER] Stream finished. Sent {frame_count} frames.")

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

