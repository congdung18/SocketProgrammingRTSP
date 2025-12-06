from random import randint
import threading, socket, time

from VideoStream import VideoStream
from RtpPacket import RtpPacket

class ServerWorker:
    SETUP = 'SETUP'
    PLAY = 'PLAY'
    PAUSE = 'PAUSE'
    TEARDOWN = 'TEARDOWN'
    FORWARD = 'FORWARD'
    BACKWARD = 'BACKWARD'
    
    INIT = 0
    READY = 1
    PLAYING = 2
    state = INIT

    OK_200 = 0
    FILE_NOT_FOUND_404 = 1
    CON_ERR_500 = 2
    
    clientInfo = {}
    
    FRAME_RATE = 20.0
    FRAME_INTERVAL = 1.0 / FRAME_RATE
    
    def __init__(self, clientInfo):
        self.clientInfo = clientInfo
        
    def run(self):
        threading.Thread(target=self.recvRtspRequest).start()
  
    def resetPlay(self):
        """Stop old worker cleanly, then start a new sendRtp worker."""
        # signal old worker to stop
        if 'event' in self.clientInfo:
            try:
                self.clientInfo['event'].set()
            except Exception:
                pass

        # join the old worker if exists (short timeout to avoid blocking forever)
        if 'worker' in self.clientInfo:
            old = self.clientInfo['worker']
            try:
                if old.is_alive():
                    old.join(timeout=0.5)
            except Exception:
                pass

        # small stabilization pause to avoid immediate burst
        time.sleep(self.FRAME_INTERVAL)

        # create new event and worker
        self.clientInfo['event'] = threading.Event()
        w = threading.Thread(target=self.sendRtp, daemon=True)
        self.clientInfo['worker'] = w
        w.start()
            
    def recvRtspRequest(self):
        """Receive RTSP request from the client."""
        connSocket = self.clientInfo['rtspSocket'][0]
        while True:            
            data = connSocket.recv(256)
            if data:
                print("Data received:\n" + data.decode("utf-8"))
                self.processRtspRequest(data.decode("utf-8"))
    
    def processRtspRequest(self, data):
        """Process RTSP request sent from the client."""
        # Get the request type
        request = data.split('\n')
        line1 = request[0].split(' ')
        requestType = line1[0]
        
        # Get the media file name
        filename = line1[1]
        
        # Get the RTSP sequence number 
        seq = request[1].split(' ')
        # print(f"\n\n\nseq: {seq}\n\n\n")
        
        # Process SETUP request
        if requestType == self.SETUP:
            if self.state == self.INIT:
                # Update state
                print("processing SETUP\n")
                
                try:
                    self.clientInfo['videoStream'] = VideoStream(filename)
                    self.state = self.READY
                except IOError:
                    self.replyRtsp(self.FILE_NOT_FOUND_404, seq[1])
                
                # Generate a randomized RTSP session ID
                self.clientInfo['session'] = randint(100000, 999999)
                
                # Send RTSP reply
                self.replyRtsp(self.OK_200, seq[1])
                
                # Get the RTP/UDP port from the last line
                self.clientInfo['rtpPort'] = request[2].split(' ')[3]
        
        # Process PLAY request 		
        elif requestType == self.PLAY:
            if self.state == self.READY:
                print("processing PLAY\n")
                self.state = self.PLAYING
                
                # Create a new socket for RTP/UDP
                self.clientInfo["rtpSocket"] = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                
                self.replyRtsp(self.OK_200, seq[1])
                
                # Create a new thread and start sending RTP packets
                self.clientInfo['event'] = threading.Event()
                self.clientInfo['worker']= threading.Thread(target=self.sendRtp) 
                self.clientInfo['worker'].start()
        
        # Process PAUSE request
        elif requestType == self.PAUSE:
            if self.state == self.PLAYING:
                print("processing PAUSE\n")
                self.state = self.READY
                
                self.clientInfo['event'].set()
            
                self.replyRtsp(self.OK_200, seq[1])
    
        elif requestType == self.FORWARD:
            if self.state in [self.READY, self.PLAYING]:
                print("processing FORWARD\n")
                vs = self.clientInfo['videoStream']
                vs.setFrame(vs.frameNbr() + 30)	
    
                if self.state == self.PLAYING:
                    self.resetPlay()
     
                self.replyRtsp(self.OK_200, seq[1])
    
        elif requestType == self.BACKWARD:
            if self.state in [self.READY, self.PLAYING]:
                print("processing BACKWARD\n")
                vs = self.clientInfo['videoStream']
                vs.setFrame(vs.frameNbr() - 30)
                if self.state == self.PLAYING:
                    self.resetPlay()
                
                self.replyRtsp(self.OK_200, seq[1])
        
        # Process TEARDOWN request
        elif requestType == self.TEARDOWN:
            print("processing TEARDOWN\n")

            self.clientInfo['event'].set()
            
            self.replyRtsp(self.OK_200, seq[1])
            
            # Close the RTP socket
            self.clientInfo['rtpSocket'].close()
            
    def sendRtp(self):
        """Send RTP packets over UDP."""
        vs = self.clientInfo['videoStream']
        FRAME_INTERVAL = 0.05
        prevFrame = -1
        while True:
            time.sleep(FRAME_INTERVAL)
            
            # Stop sending if request is PAUSE or TEARDOWN
            if self.clientInfo['event'].isSet(): 
                break 
                
            data = vs.nextFrame()
            if data is None:
                break
            frameNumber = vs.frameNbr()
            try:
                address = self.clientInfo['rtspSocket'][1][0]
                port = int(self.clientInfo['rtpPort'])
                self.clientInfo['rtpSocket'].sendto(self.makeRtp(data, frameNumber),(address,port))
            except:
                print("Connection Error")
                break
                #print('-'*60)
                #traceback.print_exc(file=sys.stdout)
                #print('-'*60)

    def makeRtp(self, payload, frameNbr):
        """RTP-packetize the video data."""
        version = 2
        padding = 0
        extension = 0
        cc = 0
        marker = 0
        pt = 26 # MJPEG type
        seqnum = frameNbr
        ssrc = 0 
        
        rtpPacket = RtpPacket()
        
        rtpPacket.encode(version, padding, extension, cc, seqnum, marker, pt, ssrc, payload)
        
        return rtpPacket.getPacket()
        
    def replyRtsp(self, code, seq):
        """Send RTSP reply to the client."""
        if code == self.OK_200:
            #print("200 OK")
            reply = 'RTSP/1.0 200 OK\nCSeq: ' + seq + '\nSession: ' + str(self.clientInfo['session'])
            connSocket = self.clientInfo['rtspSocket'][0]
            connSocket.send(reply.encode())
        
        # Error messages
        elif code == self.FILE_NOT_FOUND_404:
            print("404 NOT FOUND")
        elif code == self.CON_ERR_500:
            print("500 CONNECTION ERROR")
