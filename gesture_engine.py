import cv2
import mediapipe as mp
import time
import math
import threading
import os
import urllib.request
import numpy as np

# Check if running in cloud demo mode (no webcam/audio hardware available)
DEMO_MODE = os.environ.get('DEMO_MODE', 'false').lower() == 'true'

# Only import pyautogui if not in demo mode
if not DEMO_MODE:
    try:
        import pyautogui
        pyautogui.FAILSAFE = False
    except Exception:
        pyautogui = None
else:
    pyautogui = None

# Platform-specific volume control (Windows pycaw)
try:
    import comtypes
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    HAS_PYCAW = True
except ImportError:
    HAS_PYCAW = False

class VolumeController:
    """Manages system volume using pycaw on Windows, falling back to pyautogui controls."""
    def __init__(self):
        self.volume = None
        if HAS_PYCAW:
            try:
                comtypes.CoInitialize()
                devices = AudioUtilities.GetSpeakers()
                if hasattr(devices, "EndpointVolume"):
                    self.volume = devices.EndpointVolume
                else:
                    from ctypes import cast, POINTER
                    from comtypes import CLSCTX_ALL
                    from pycaw.pycaw import IAudioEndpointVolume
                    interface = devices.Activate(
                        IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                    self.volume = cast(interface, POINTER(IAudioEndpointVolume))
            except Exception as e:
                print(f"[VolumeController] Failed to initialize pycaw: {e}")
                self.volume = None

    def change_volume(self, delta):
        """delta is positive (up) or negative (down) float, e.g. +0.05 or -0.05."""
        if HAS_PYCAW and self.volume:
            try:
                comtypes.CoInitialize()
                current_vol = self.volume.GetMasterVolumeLevelScalar()
                new_vol = max(0.0, min(1.0, current_vol + delta))
                self.volume.SetMasterVolumeLevelScalar(new_vol, None)
                return int(new_vol * 100), f"Volume set to {int(new_vol * 100)}%"
            except Exception as e:
                print(f"[VolumeController] pycaw error: {e}")
        
        # Fallback to pyautogui simulation
        if delta > 0:
            pyautogui.press("volumeup")
            return None, "Volume Up (Key Sim)"
        else:
            pyautogui.press("volumedown")
            return None, "Volume Down (Key Sim)"

    def toggle_mute(self):
        if HAS_PYCAW and self.volume:
            try:
                comtypes.CoInitialize()
                is_muted = self.volume.GetMute()
                self.volume.SetMute(not is_muted, None)
                status = "Muted" if not is_muted else "Unmuted"
                return status
            except Exception as e:
                print(f"[VolumeController] pycaw mute error: {e}")
        
        # Fallback
        pyautogui.press("volumemute")
        return "Mute Toggled (Key Sim)"

    def get_current_volume(self):
        if HAS_PYCAW and self.volume:
            try:
                comtypes.CoInitialize()
                return int(self.volume.GetMasterVolumeLevelScalar() * 100)
            except Exception:
                pass
        return 50

class GestureEngine:
    """Processes webcam frames in a background thread, tracks hand landmarks, and maps gestures to actions."""
    def __init__(self):
        self.volume_ctrl = VolumeController()
        
        # Default gesture-to-action mappings
        self.mappings = {
            "fist": "mute",
            "peace": "play_pause",
            "point_up": "volume_up",
            "open_palm": "volume_down",
            "thumbs_up": "next_slide",
            "thumbs_down": "prev_slide"
        }
        
        # Action labels dictionary for cleaner display
        self.action_labels = {
            "mute": "Toggle Mute",
            "play_pause": "Play / Pause",
            "volume_up": "Volume Up (+5%)",
            "volume_down": "Volume Down (-5%)",
            "next_slide": "Next Slide (Right Arrow)",
            "prev_slide": "Previous Slide (Left Arrow)",
            "none": "No Action"
        }
        
        # Logging history
        self.logs = []
        self.max_logs = 30
        
        # Status and Thread variables
        self.is_running = False
        self.last_gesture = "None"
        self.cooldown_seconds = 0.8
        self.last_action_time = 0
        
        self.cap = None
        self.thread = None
        self.lock = threading.Lock()
        self.latest_frame = None
        self.detector = None

        # Check and download model asset if missing
        self.model_path = "hand_landmarker.task"
        self.model_url = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
        self._ensure_model_downloaded()

    def _ensure_model_downloaded(self):
        """Downloads the hand landmarker tasks file if not present locally."""
        if not os.path.exists(self.model_path):
            self.add_log("System", "Downloading hand landmarker model...")
            try:
                print(f"Downloading model to {self.model_path}...")
                urllib.request.urlretrieve(self.model_url, self.model_path)
                self.add_log("System", "Model downloaded successfully")
            except Exception as e:
                self.add_log("System", f"Model download failed: {str(e)}")
                print(f"Error downloading model: {e}")

    def _init_detector(self):
        """Initializes the MediaPipe Tasks HandLandmarker."""
        if self.detector is not None:
            return True
            
        try:
            from mediapipe.tasks import python
            from mediapipe.tasks.python import vision
            
            base_options = python.BaseOptions(model_asset_path=self.model_path)
            options = vision.HandLandmarkerOptions(
                base_options=base_options,
                num_hands=1,
                min_hand_detection_confidence=0.7,
                min_hand_presence_confidence=0.7,
                min_tracking_confidence=0.7
            )
            self.detector = vision.HandLandmarker.create_from_options(options)
            return True
        except Exception as e:
            self.add_log("System", f"Failed to load MediaPipe Tasks detector: {str(e)}")
            print(f"[GestureEngine] Detector init error: {e}")
            return False

    def add_log(self, action_name, detail=""):
        timestamp = time.strftime("%H:%M:%S")
        self.logs.append({
            "time": timestamp,
            "action": action_name,
            "detail": detail
        })
        if len(self.logs) > self.max_logs:
            self.logs.pop(0)

    def update_mappings(self, new_mappings):
        """Update active mappings dynamically from client input."""
        with self.lock:
            for gesture, action in new_mappings.items():
                if gesture in self.mappings:
                    self.mappings[gesture] = action
            self.add_log("System", "Updated gesture mappings")

    def detect_gesture(self, landmarks, handedness):
        """
        Analyzes 21 3D hand landmarks to recognize standard gestures.
        Returns a string gesture label or 'None'.
        """
        # 4 Standard fingers: index, middle, ring, pinky
        # A finger is extended if tip is higher than PIP joint (y of tip < y of PIP)
        index_up = landmarks[8].y < landmarks[6].y
        middle_up = landmarks[12].y < landmarks[10].y
        ring_up = landmarks[16].y < landmarks[14].y
        pinky_up = landmarks[20].y < landmarks[18].y
        
        # Check if palm is open or in a fist
        fingers_folded = not index_up and not middle_up and not ring_up and not pinky_up
        
        # Calculate horizontal and vertical thumb movements
        # Using pinky MCP (17) to index MCP (5) as a hand size scale reference
        dx_hand = landmarks[5].x - landmarks[17].x
        dy_hand = landmarks[5].y - landmarks[17].y
        palm_width = math.sqrt(dx_hand**2 + dy_hand**2)
        if palm_width == 0:
            palm_width = 0.1
            
        thumb_index_dist = math.sqrt((landmarks[4].x - landmarks[5].x)**2 + (landmarks[4].y - landmarks[5].y)**2)
        
        # Thumbs up or Thumbs down detection
        if fingers_folded:
            # Thumb tip is significantly higher than MCP/IP (y is lower)
            if landmarks[4].y < landmarks[3].y < landmarks[2].y:
                return "thumbs_up"
            elif landmarks[4].y > landmarks[3].y > landmarks[2].y:
                return "thumbs_down"
            else:
                return "fist"
                
        # Open Palm
        if index_up and middle_up and ring_up and pinky_up:
            return "open_palm"
            
        # Point Up (only index finger is up)
        if index_up and not middle_up and not ring_up and not pinky_up:
            return "point_up"
            
        # Peace Sign (index and middle are up, others folded)
        if index_up and middle_up and not ring_up and not pinky_up:
            return "peace"
            
        return "None"

    def execute_action(self, action):
        """Simulates keypresses or changes system volume using pycaw."""
        now = time.time()
        if now - self.last_action_time < self.cooldown_seconds:
            return False  # Cooldown active
            
        self.last_action_time = now
        
        if action == "volume_up":
            vol, details = self.volume_ctrl.change_volume(0.05)
            self.add_log("Volume Up", details)
            
        elif action == "volume_down":
            vol, details = self.volume_ctrl.change_volume(-0.05)
            self.add_log("Volume Down", details)
            
        elif action == "mute":
            details = self.volume_ctrl.toggle_mute()
            self.add_log("Toggle Mute", details)
            
        elif action == "play_pause":
            pyautogui.press("playpause")
            self.add_log("Play / Pause", "Simulated Space/PlayPause Key")
            
        elif action == "next_slide":
            pyautogui.press("right")
            self.add_log("Next Slide", "Simulated Right Arrow Key")
            
        elif action == "prev_slide":
            pyautogui.press("left")
            self.add_log("Previous Slide", "Simulated Left Arrow Key")
            
        elif action == "none" or action is None:
            return False
            
        return True

    def draw_landmarks(self, frame, landmarks):
        """Manually draws 21 landmarks and line connections for MediaPipe Hands."""
        h, w, _ = frame.shape
        
        # Connection indices mapping
        connections = [
            (0, 1), (1, 2), (2, 3), (3, 4),      # Thumb
            (5, 6), (6, 7), (7, 8),              # Index finger
            (9, 10), (10, 11), (11, 12),         # Middle finger
            (13, 14), (14, 15), (15, 16),         # Ring finger
            (17, 18), (18, 19), (19, 20),         # Pinky finger
            (0, 5), (5, 9), (9, 13), (13, 17), (0, 17) # Palm connections
        ]
        
        # Draw connections (lines) in neon pink
        for start, end in connections:
            if start < len(landmarks) and end < len(landmarks):
                p1 = landmarks[start]
                p2 = landmarks[end]
                cx1, cy1 = int(p1.x * w), int(p1.y * h)
                cx2, cy2 = int(p2.x * w), int(p2.y * h)
                cv2.line(frame, (cx1, cy1), (cx2, cy2), (255, 0, 180), 2)
                
        # Draw joints (points) in neon cyan
        for p in landmarks:
            cx, cy = int(p.x * w), int(p.y * h)
            cv2.circle(frame, (cx, cy), 4, (0, 255, 230), -1)

    def _run_loop(self):
        """Webcam frame capturing and MediaPipe processing background thread loop."""
        while True:
            # Check is_running safely
            with self.lock:
                if not self.is_running:
                    break
                    
            if self.cap is None or not self.cap.isOpened():
                time.sleep(0.1)
                continue
                
            success, frame = self.cap.read()
            if not success:
                time.sleep(0.03)
                continue
                
            # Flip horizontally for mirrored selfie-camera view
            frame = cv2.flip(frame, 1)
            h, w, c = frame.shape
            
            # Convert frame to RGB for MediaPipe
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Convert OpenCV frame to MediaPipe Image object
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
            
            # Run vision landmarker
            gesture_detected = "None"
            
            if self.detector is not None:
                try:
                    results = self.detector.detect(mp_image)
                    
                    if results.hand_landmarks:
                        for idx, hand_landmarks in enumerate(results.hand_landmarks):
                            # Handedness info
                            hand_label = "Right"
                            if results.handedness and idx < len(results.handedness):
                                hand_label = results.handedness[idx][0].category_name
                                
                            gesture_detected = self.detect_gesture(hand_landmarks, hand_label)
                            
                            with self.lock:
                                self.last_gesture = gesture_detected
                            
                            # Draw annotations manually
                            self.draw_landmarks(frame, hand_landmarks)
                            
                            # Trigger system actions
                            if gesture_detected != "None":
                                with self.lock:
                                    mapped_action = self.mappings.get(gesture_detected)
                                if mapped_action and mapped_action != "none":
                                    triggered = self.execute_action(mapped_action)
                                    if triggered:
                                        # Overlay flash circle indicator on frame for positive feedback
                                        cv2.circle(frame, (w - 30, 30), 12, (0, 255, 0), -1)
                            
                            # Add text overlay near wrist
                            wrist = hand_landmarks[0]
                            cx, cy = int(wrist.x * w), int(wrist.y * h)
                            cv2.putText(frame, gesture_detected.upper(), (cx - 40, cy - 20),
                                        cv2.FONT_HERSHEY_DUPLEX, 0.7, (0, 255, 255), 2)
                    else:
                        with self.lock:
                            self.last_gesture = "None"
                except Exception as e:
                    print(f"[GestureEngine] Error during detection loop: {e}")
                    with self.lock:
                        self.last_gesture = "None"
            else:
                with self.lock:
                    self.last_gesture = "None"
                    
            # Overlay status and gesture text HUD
            cv2.putText(frame, "STATUS: RUNNING", (20, 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 100), 2)
            
            with self.lock:
                mapped_action = self.mappings.get(gesture_detected, "none")
            
            action_label = self.action_labels.get(mapped_action, "none").upper()
            
            if gesture_detected != "None":
                cv2.putText(frame, f"GESTURE: {gesture_detected.upper()} ({action_label})", (20, 60), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
            else:
                cv2.putText(frame, "GESTURE: NONE", (20, 60), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

            ret, jpeg = cv2.imencode('.jpg', frame)
            if ret:
                with self.lock:
                    self.latest_frame = jpeg.tobytes()
                    
            # Cap the thread cycle rate to limit CPU consumption
            time.sleep(0.03)

    def _run_demo_loop(self):
        """Generates synthetic demo frames cycling through gestures. Used on cloud deployments."""
        gestures_cycle = [
            ("open_palm",  "🖐",  "OPEN PALM",  "Volume Down"),
            ("point_up",   "☝",  "POINT UP",   "Volume Up"),
            ("peace",      "✌",  "PEACE SIGN", "Play / Pause"),
            ("fist",       "✊",  "FIST",        "Toggle Mute"),
            ("thumbs_up",  "👍", "THUMBS UP",  "Next Slide"),
            ("thumbs_down","👎", "THUMBS DOWN","Prev Slide"),
        ]
        idx = 0
        gesture_hold = 0
        HOLD_FRAMES = 60  # ~2 seconds per gesture at 30fps

        while True:
            with self.lock:
                if not self.is_running:
                    break

            gesture_key, emoji, label, action_label = gestures_cycle[idx]

            # Build a dark synthetic frame
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            frame[:] = (12, 16, 28)  # Dark navy background

            # Gradient overlay
            for y in range(480):
                alpha = y / 480
                frame[y] = np.clip(
                    frame[y] + np.array([int(8*alpha), int(4*alpha), int(20*alpha)]),
                    0, 255
                ).astype(np.uint8)

            # Draw a glowing circle representing the "hand"
            cx, cy = 320, 240
            for r, alpha_val in [(90, 0.04), (70, 0.08), (50, 0.15)]:
                overlay = frame.copy()
                cv2.circle(overlay, (cx, cy), r, (0, 240, 255), -1)
                cv2.addWeighted(overlay, alpha_val, frame, 1 - alpha_val, 0, frame)
            cv2.circle(frame, (cx, cy), 48, (0, 200, 220), 2)

            # Animated pulse ring
            pulse_r = 55 + int(10 * abs(math.sin(time.time() * 3)))
            cv2.circle(frame, (cx, cy), pulse_r, (0, 255, 200), 1)

            # Gesture label in center
            text_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_DUPLEX, 0.8, 2)[0]
            cv2.putText(frame, label, (cx - text_size[0]//2, cy + 8),
                        cv2.FONT_HERSHEY_DUPLEX, 0.8, (0, 255, 255), 2)

            # Action label below
            action_text = f"-> {action_label}"
            asize = cv2.getTextSize(action_text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)[0]
            cv2.putText(frame, action_text, (cx - asize[0]//2, cy + 45),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 200, 0), 1)

            # DEMO MODE badge (top-left)
            cv2.rectangle(frame, (10, 10), (170, 38), (40, 20, 80), -1)
            cv2.rectangle(frame, (10, 10), (170, 38), (120, 60, 200), 1)
            cv2.putText(frame, "DEMO MODE", (18, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (180, 100, 255), 1)

            # Status HUD
            cv2.putText(frame, "STATUS: RUNNING", (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 100), 2)
            cv2.putText(frame, f"GESTURE: {label}", (10, 85),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 0), 1)

            # Progress bar at bottom
            progress = gesture_hold / HOLD_FRAMES
            bar_w = int(620 * progress)
            cv2.rectangle(frame, (10, 465), (630, 472), (30, 30, 50), -1)
            cv2.rectangle(frame, (10, 465), (10 + bar_w, 472), (0, 200, 255), -1)
            cv2.putText(frame, "Next gesture in...", (10, 460),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (100, 120, 160), 1)

            with self.lock:
                self.last_gesture = gesture_key

            # Trigger a simulated action at the start of each gesture
            if gesture_hold == 5:
                self.add_log(action_label, f"Demo: {label} gesture detected")

            ret, jpeg = cv2.imencode('.jpg', frame)
            if ret:
                with self.lock:
                    self.latest_frame = jpeg.tobytes()

            gesture_hold += 1
            if gesture_hold >= HOLD_FRAMES:
                gesture_hold = 0
                idx = (idx + 1) % len(gestures_cycle)

            time.sleep(0.033)

    def start(self):
        if DEMO_MODE:
            # Cloud/demo deployment — no webcam or audio hardware needed
            with self.lock:
                if not self.is_running:
                    self.is_running = True
                    self.thread = threading.Thread(target=self._run_demo_loop, daemon=True)
                    self.thread.start()
                    self.add_log("System", "Demo Mode Started — Cycling gestures automatically")
                    return True
            return False

        # Local mode — real webcam + MediaPipe
        self._ensure_model_downloaded()
        if not self._init_detector():
            self.add_log("System", "Could not initialize MediaPipe detector")
            return False

        with self.lock:
            if not self.is_running:
                self.cap = cv2.VideoCapture(0)
                if not self.cap.isOpened():
                    self.add_log("System", "Failed to access webcam")
                    return False
                self.is_running = True
                self.thread = threading.Thread(target=self._run_loop, daemon=True)
                self.thread.start()
                self.add_log("System", "Gesture Controller Started")
                return True
        return False

    def stop(self):
        with self.lock:
            if self.is_running:
                self.is_running = False
                if self.cap:
                    self.cap.release()
                    self.cap = None
                self.latest_frame = None
                self.last_gesture = "None"
                self.add_log("System", "Gesture Controller Stopped")
                # Release the detector to free memory
                self.detector = None

    def get_frame(self):
        with self.lock:
            if not self.is_running or self.latest_frame is None:
                return None
            return self.latest_frame
