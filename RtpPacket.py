# RtpPacket.py - Fixed, safe implementation with create(...)
import struct
import time

class RtpPacket:
    def __init__(self):
        self.header = None
        self.payload = None

    @staticmethod
    def _u32(x):
        return int(x) & 0xFFFFFFFF

    @staticmethod
    def create(seqnum, payload=b'', marker=False, pt=26, ssrc=0, version=2, padding=0, extension=0, cc=0):
        """
        Create a raw RTP packet (header + payload) and return bytes.
        - seqnum: 0..65535
        - payload: bytes
        - marker: boolean
        - pt: payload type (0..127)
        - ssrc: 32-bit int
        - version: usually 2
        """
        # Normalise values into bounds
        version = int(version) & 0x03
        padding = int(padding) & 0x01
        extension = int(extension) & 0x01
        cc = int(cc) & 0x0F
        marker_int = 1 if marker else 0
        pt_int = int(pt) & 0x7F
        seqnum_int = int(seqnum) & 0xFFFF
        timestamp = RtpPacket._u32(time.time() * 1000)  # millisecond timestamp masked to 32-bit
        ssrc_int = int(ssrc) & 0xFFFFFFFF

        first_byte = (version << 6) | (padding << 5) | (extension << 4) | (cc & 0x0F)
        second_byte = (marker_int << 7) | pt_int

        header = struct.pack('!BBHII', first_byte, second_byte, seqnum_int, timestamp, ssrc_int)
        return header + (payload if payload is not None else b'')

    def encode(self, version, padding, extension, cc, seqnum, marker, pt, ssrc, payload):
        """
        Encode RTP packet into self.header and self.payload (kept for compatibility).
        """
        version = int(version) & 0x03
        padding = int(padding) & 0x01
        extension = int(extension) & 0x01
        cc = int(cc) & 0x0F
        marker_int = 1 if marker else 0
        pt_int = int(pt) & 0x7F
        seqnum_int = int(seqnum) & 0xFFFF
        timestamp = RtpPacket._u32(time.time() * 1000)
        ssrc_int = int(ssrc) & 0xFFFFFFFF

        first_byte = (version << 6) | (padding << 5) | (extension << 4) | (cc & 0x0F)
        second_byte = (marker_int << 7) | pt_int

        self.header = struct.pack('!BBHII', first_byte, second_byte, seqnum_int, timestamp, ssrc_int)
        self.payload = payload if payload is not None else b''

    def decode(self, data):
        """Decode RTP packet: store header (first 12 bytes) and payload (rest)."""
        if len(data) >= 12:
            self.header = data[:12]
            self.payload = data[12:]
        else:
            self.header = data
            self.payload = b''

    def getPacket(self):
        """Return full packet bytes."""
        if self.header is not None:
            return self.header + (self.payload or b'')
        return b''

    def getPayload(self):
        return self.payload or b''

    def getMarker(self):
        if self.header and len(self.header) >= 2:
            return (self.header[1] >> 7) & 0x01
        return 0

    def seqNum(self):
        if self.header and len(self.header) >= 4:
            return struct.unpack('!H', self.header[2:4])[0]
        return 0
