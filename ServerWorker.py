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

    CHANGE_RESOLUTION = 'CHANGE_RESOLUTION'

    def __init__(self, clientInfo):
        self.clientInfo = clientInfo
        self.packetSeq = randint(0, 65535)
        self.streaming = False
        self.stream_thread = None
        self.lock = threading.Lock()
        self.keep_alive = True

    def run(self):
        threading.Thread(target=self.recvRtspRequest).start()

    def recvRtspRequest(self):
        """Receive RTSP requests."""
        connSocket, client_address = self.clientInfo['rtspSocket']
        print(f"[SERVER] Handling connection from {client_address}")
        
        try:
            while True:
                try:
                    data = connSocket.recv(256)
                    if not data:
                        print(f"[SERVER] Client {client_address} disconnected")
                        break
                    
                    data_str = data.decode("utf-8", errors='ignore')
                    print(f"[SERVER] Received from {client_address}:\n{data_str}")
                    
                    if self.processRtspRequest(data_str):
                        break
                        
                except socket.timeout:
                    # Check if streaming is still active
                    with self.lock:
                        if not self.streaming:
                            print(f"[SERVER] Timeout, no streaming activity")
                    continue
                except Exception as e:
                    print(f"[SERVER] Error receiving from {client_address}: {e}")
                    break
                    
        except Exception as e:
            print(f"[SERVER] Connection error with {client_address}: {e}")
        finally:
            # Clean up
            self.stop_streaming()
            try:
                connSocket.close()
            except:
                pass
            print(f"[SERVER] Connection closed for {client_address}")

    def processRtspRequest(self, data):
        """Process RTSP request - UPDATED FOR CHANGE_RESOLUTION."""
        request = data.strip().split('\n')
        
        if not request or len(request) < 2:
            return False
        
        # Parse request line
        request_line = request[0].split(' ')
        if len(request_line) < 2:
            return False
        
        requestType = request_line[0]
        filename = request_line[1]
        
        # Parse headers
        seq = '0'
        resolution = self.clientInfo.get('resolution', '720p')  # Default to current
        client_port = None
        new_resolution = None  # For CHANGE_RESOLUTION
        
        for line in request[1:]:
            line = line.strip()
            if line.startswith('CSeq:'):
                seq = line.split(':')[1].strip()
            elif line.startswith('Resolution:'):
                # For SETUP or CHANGE_RESOLUTION
                resolution = line.split(':')[1].strip()
                new_resolution = resolution
            elif line.startswith('Transport:'):
                if 'client_port=' in line:
                    client_port = line.split('client_port=')[1].strip()
                    if ';' in client_port:
                        client_port = client_port.split(';')[0]
        
        print(f"[SERVER] Processing {requestType} for {filename}")
        
        if requestType == self.SETUP:
            if self.state == self.INIT:
                print(f"[SERVER] SETUP requested for {resolution}")
                
                if not client_port:
                    return False
                
                self.clientInfo['rtpPort'] = client_port
                self.clientInfo['resolution'] = resolution
                
                try:
                    self.clientInfo['videoStream'] = VideoStream(filename, resolution)
                    self.state = self.READY
                except Exception as e:
                    print(f"[SERVER] Error: {e}")
                    self.replyRtsp(self.FILE_NOT_FOUND_404, seq)
                    return False
                
                # Create session ID
                self.clientInfo['session'] = randint(100000, 999999)
                
                self.replyRtsp(self.OK_200, seq)
                print(f"[SERVER] SETUP complete")
        
        elif requestType == self.PLAY:
            if self.state == self.READY:
                print(f"[SERVER] PLAY requested")
                self.state = self.PLAYING
                
                # Create RTP socket if needed
                if 'rtpSocket' not in self.clientInfo:
                    self.clientInfo['rtpSocket'] = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    self.clientInfo['rtpSocket'].settimeout(1.0)
                
                # Start streaming thread if not already running
                with self.lock:
                    self.streaming = True
                
                if not self.stream_thread or not self.stream_thread.is_alive():
                    self.stream_thread = threading.Thread(target=self.sendRtp, daemon=True)
                    self.stream_thread.start()
                    print("[SERVER] Streaming thread started")
                else:
                    print("[SERVER] Resuming streaming from paused state")
                
                self.replyRtsp(self.OK_200, seq)
        
        elif requestType == self.PAUSE:
            if self.state == self.PLAYING:
                print("[SERVER] PAUSE requested")
                self.state = self.READY
                
                # Pause streaming but keep thread alive
                with self.lock:
                    self.streaming = False
                
                print("[SERVER] Streaming paused (thread keeps running)")
                self.replyRtsp(self.OK_200, seq)
        
        elif requestType == self.CHANGE_RESOLUTION:
            if self.state in [self.READY, self.PLAYING] and new_resolution:
                print(f"[SERVER] CHANGE_RESOLUTION requested: {new_resolution}")
                
                # Store old state to restore after resolution change
                old_state = self.state
                was_playing = (old_state == self.PLAYING)
                
                # Pause streaming temporarily if playing
                if was_playing:
                    with self.lock:
                        self.streaming = False
                    time.sleep(0.1)  # Small delay to ensure pause
                    print("[SERVER] Paused streaming for resolution change")
                
                # Update client info
                old_resolution = self.clientInfo.get('resolution', '720p')
                self.clientInfo['resolution'] = new_resolution
                
                # Change resolution in video stream
                video_stream = self.clientInfo.get('videoStream')
                if video_stream:
                    success = video_stream.change_resolution(new_resolution)
                    if success:
                        print(f"[SERVER] Resolution changed from {old_resolution} to {new_resolution}")
                        
                        # Restore previous state
                        if was_playing:
                            time.sleep(0.1)  # Small delay
                            with self.lock:
                                self.streaming = True
                            print("[SERVER] Resumed streaming after resolution change")
                        
                        # Send success reply
                        self.replyRtsp(self.OK_200, seq)
                    else:
                        print("[SERVER] Failed to change resolution")
                        # Revert to old resolution
                        self.clientInfo['resolution'] = old_resolution
                        self.replyRtsp(self.CON_ERR_500, seq)
                else:
                    print("[SERVER] No video stream available")
                    self.replyRtsp(self.CON_ERR_500, seq)
            else:
                print("[SERVER] Invalid CHANGE_RESOLUTION request")
                self.replyRtsp(self.CON_ERR_500, seq)
        
        elif requestType == self.TEARDOWN:
            print("[SERVER] TEARDOWN requested")
            self.state = self.INIT
            
            # Stop thread completely
            self.keep_alive = False
            
            # Wait for thread to finish
            if self.stream_thread and self.stream_thread.is_alive():
                print("[SERVER] Stopping streaming thread...")
                self.stream_thread.join(timeout=2.0)
                print("[SERVER] Streaming thread stopped")
            
            # Close RTP socket
            if 'rtpSocket' in self.clientInfo:
                try:
                    self.clientInfo['rtpSocket'].close()
                    del self.clientInfo['rtpSocket']
                except:
                    pass
            
            # Reset video stream for next session
            if 'videoStream' in self.clientInfo:
                self.clientInfo['videoStream'].reset()
            
            self.replyRtsp(self.OK_200, seq)
            return True  # Signal to close connection
        
        return False
    
    def stop_streaming(self):
        """Stop streaming - MODIFIED VERSION."""
        with self.lock:
            self.streaming = False
        
        # **KHÔNG join thread ở đây nữa**
        # Thread sẽ tự kiểm tra streaming flag
        
        # Close RTP socket
        if 'rtpSocket' in self.clientInfo:
            try:
                self.clientInfo['rtpSocket'].close()
                del self.clientInfo['rtpSocket']
            except:
                pass

    def sendRtp(self):
        """Continuous RTP streaming thread - OPTIMIZED."""
        print("[SERVER] ===== RTP STREAMING THREAD STARTED =====")
        
        # Setup
        target_ip = '127.0.0.1'
        client_port = int(self.clientInfo['rtpPort'])
        
        # Get video stream reference
        video_stream = self.clientInfo['videoStream']
        
        frame_count = 0
        packet_count = 0
        last_report_time = time.time()
        
        try:
            while self.keep_alive:
                # Check if we should send frames
                with self.lock:
                    should_stream = self.streaming
                
                if not should_stream:
                    time.sleep(0.05)  # Giảm CPU usage khi pause
                    continue
                
                # Get next frame
                frame_data = video_stream.nextFrame()
                if frame_data is None:
                    video_stream.reset()
                    frame_data = video_stream.nextFrame()
                    if frame_data is None:
                        continue
                
                frame_count += 1
                
                # Validate frame
                if len(frame_data) < 4:
                    continue
                
                # Split and send frame
                MAX_PAYLOAD = 1400
                frame_size = len(frame_data)
                offset = 0
                
                while offset < frame_size:
                    chunk_size = min(MAX_PAYLOAD, frame_size - offset)
                    chunk = frame_data[offset:offset + chunk_size]
                    
                    is_last_packet = (offset + chunk_size >= frame_size)
                    
                    self.packetSeq = (self.packetSeq + 1) % 65536
                    
                    packet = RtpPacket.create(
                        seqnum=self.packetSeq,
                        payload=chunk,
                        marker=is_last_packet,
                        pt=26,
                        ssrc=0x12345678
                    )
                    
                    packet_count += 1
                    
                    # Send packet
                    try:
                        self.clientInfo['rtpSocket'].sendto(packet, (target_ip, client_port))
                    except Exception as e:
                        print(f"[SERVER] Send error: {e}")
                        break
                    
                    offset += chunk_size
                    
                    # Small delay between packets
                    if not is_last_packet:
                        time.sleep(0.0005)  # Giảm delay để tăng performance
                
                # Progress reporting mỗi 5 giây
                current_time = time.time()
                if current_time - last_report_time >= 5.0:
                    fps = frame_count / (current_time - last_report_time)
                    print(f"[SERVER] Sent {frame_count} frames, {packet_count} packets, FPS: {fps:.1f}")
                    last_report_time = current_time
                    frame_count = 0
                
                # Frame rate control (~25 FPS)
                time.sleep(0.04)
        
        except Exception as e:
            print(f"[SERVER] Streaming thread error: {e}")
        
        finally:
            print(f"[SERVER] ===== STREAMING THREAD ENDED =====")
            
    def replyRtsp(self, code, seq):
        """Send RTSP reply."""
        connSocket, client_address = self.clientInfo['rtspSocket']
        
        if code == self.OK_200:
            session = self.clientInfo.get('session', 0)
            resolution = self.clientInfo.get('resolution', '720p')
            
            reply = (
                f"RTSP/1.0 200 OK\r\n"
                f"CSeq: {seq}\r\n"
                f"Session: {session}\r\n"
                f"Resolution: {resolution}\r\n\r\n"
            )
            
            try:
                connSocket.send(reply.encode())
                print(f"[SERVER] Sent 200 OK for CSeq {seq}, session {session}")
            except Exception as e:
                print(f"[SERVER] Error sending reply: {e}")
        
        elif code == self.FILE_NOT_FOUND_404:
            reply = (
                f"RTSP/1.0 404 File Not Found\r\n"
                f"CSeq: {seq}\r\n\r\n"
            )
            try:
                connSocket.send(reply.encode())
                print(f"[SERVER] Sent 404 Not Found for CSeq {seq}")
            except Exception as e:
                print(f"[SERVER] Error sending 404: {e}")
                
        elif code == self.CON_ERR_500:
            reply = (
                f"RTSP/1.0 500 Connection Error\r\n"
                f"CSeq: {seq}\r\n\r\n"
            )
            try:
                connSocket.send(reply.encode())
                print(f"[SERVER] Sent 500 Error for CSeq {seq}")
            except Exception as e:
                print(f"[SERVER] Error sending 500: {e}")