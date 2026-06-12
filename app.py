from flask import Flask, render_template, Response, jsonify, request, send_from_directory
from gesture_engine import GestureEngine
import time

app = Flask(__name__)

# Initialize the gesture detection engine
engine = GestureEngine()

@app.route('/')
def index():
    return render_template('index.html')

def gen_frames():
    """Generates camera frames with real-time gesture annotations."""
    last_frame = None
    while True:
        frame_bytes = engine.get_frame()
        if frame_bytes is None:
            # If engine is stopped, read a local placeholder frame or generate a blank frame
            import cv2
            import numpy as np
            blank_image = np.zeros((480, 640, 3), dtype=np.uint8)
            # Modern, stylish dark blue background instead of black
            blank_image[:] = (20, 15, 10)  # Dark slate color
            
            # Subtle glow design for placeholder
            cv2.putText(blank_image, "CAMERA OFFLINE", (170, 210), 
                        cv2.FONT_HERSHEY_DUPLEX, 1.0, (150, 80, 255), 2)
            cv2.putText(blank_image, "Click 'Start Controller' below to launch", (120, 270), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (180, 180, 180), 1)
            
            ret, jpeg = cv2.imencode('.jpg', blank_image)
            frame_bytes = jpeg.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            time.sleep(0.1)
            continue
            
        if frame_bytes != last_frame:
            last_frame = frame_bytes
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        
        time.sleep(0.01)

@app.route('/video_feed')
def video_feed():
    """Video streaming route. Put this in the src attribute of an img tag."""
    return Response(gen_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/status')
def status():
    """Endpoint for UI polling. Returns controller details."""
    return jsonify({
        "running": engine.is_running,
        "active_gesture": engine.last_gesture,
        "volume": engine.volume_ctrl.get_current_volume()
    })

@app.route('/api/start', methods=['POST'])
def start_controller():
    """Starts the gesture controller background thread."""
    success = engine.start()
    return jsonify({
        "success": success,
        "message": "Controller started" if success else "Failed to start camera. Check connection."
    })

@app.route('/api/stop', methods=['POST'])
def stop_controller():
    """Stops the gesture controller."""
    engine.stop()
    return jsonify({
        "success": True,
        "message": "Controller stopped"
    })

@app.route('/api/mappings', methods=['GET', 'POST'])
def mappings():
    """Handles getting and setting user-configured gesture mappings."""
    if request.method == 'POST':
        new_mappings = request.json
        engine.update_mappings(new_mappings)
        return jsonify({"success": True, "mappings": engine.mappings})
    else:
        return jsonify({
            "mappings": engine.mappings,
            "labels": engine.action_labels
        })

@app.route('/api/logs')
def get_logs():
    """Returns lists of recent control events."""
    return jsonify({
        "logs": engine.logs
    })

if __name__ == '__main__':
    # Run the Flask app locally on port 5000 (reloader disabled to prevent double webcam opening)
    app.run(debug=True, use_reloader=False, host='0.0.0.0', port=5000, threaded=True)
