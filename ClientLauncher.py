import sys
from tkinter import Tk, messagebox
from Client import Client

if __name__ == "__main__":
    print("=== RTP Client Launcher ===")
    
    try:
        if len(sys.argv) >= 5:
            serverAddr = sys.argv[1]
            serverPort = sys.argv[2]
            rtpPort = sys.argv[3]
            fileName = sys.argv[4]
            
            # Optional resolution parameter
            if len(sys.argv) > 5:
                resolution = sys.argv[5]
                if resolution not in ["720p", "1080p"]:
                    print(f"Warning: Invalid resolution '{resolution}'. Using default 720p.")
                    resolution = "720p"
            else:
                resolution = "720p"
                
            print(f"Parameters:")
            print(f"  Server: {serverAddr}:{serverPort}")
            print(f"  RTP Port: {rtpPort}")
            print(f"  File: {fileName}")
            print(f"  Resolution: {resolution}")
            
        else:
            print("[Usage: ClientLauncher.py Server_name Server_port RTP_port Video_file [resolution]]\n")
            print("Arguments:")
            print("  Server_name: IP address or hostname of the server")
            print("  Server_port: Port number of the RTSP server (e.g., 8554)")
            print("  RTP_port: Port number for RTP packets (e.g., 25000)")
            print("  Video_file: Name of the video file (e.g., movie.Mjpeg)")
            print("  resolution: Optional - '720p' or '1080p' (default: 720p)")
            sys.exit(1)
            
    except Exception as e:
        print(f"Error parsing arguments: {e}")
        print("[Usage: ClientLauncher.py Server_name Server_port RTP_port Video_file [resolution]]")
        sys.exit(1)
    
    # Create main window
    root = Tk()
    
    # Set initial window size based on resolution
    if resolution == "1080p":
        root.geometry("1920x1000")
        root.minsize(960, 600)
    else:  # 720p
        root.geometry("1280x800")
        root.minsize(640, 480)
    
    # Create a new client
    try:
        app = Client(root, serverAddr, serverPort, rtpPort, fileName)
        
        # Set initial resolution if provided via command line
        if hasattr(app, 'resolution_var'):
            app.resolution_var.set(resolution)
            app.resolution = resolution
            
            # Update target dimensions
            if resolution == "720p":
                app.target_width = 1280
                app.target_height = 720
            elif resolution == "1080p":
                app.target_width = 1920
                app.target_height = 1080
            
            # Update label
            if hasattr(app, 'resolution_label'):
                app.resolution_label.config(text=f"Selected: {resolution}")
        
        app.master.title(f"RTPClient - {resolution} Stream")
        
    except Exception as e:
        messagebox.showerror("Client Error", f"Failed to create client: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Start main loop
    print("Starting GUI main loop...")
    root.mainloop()
    print("GUI main loop ended.")