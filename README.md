# AuraGesture - Real-Time AI Hand Gesture Controller

[![Live Demo](https://img.shields.io/badge/🌐_Live_Demo-Portfolio_Page-00f0ff?style=for-the-badge)](https://gunashree2007.github.io/AIFE/)
[![GitHub](https://img.shields.io/badge/GitHub-Gunashree2007%2FAIFE-181717?style=for-the-badge&logo=github)](https://github.com/Gunashree2007/AIFE)
[![Python](https://img.shields.io/badge/Python-3.8+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![MediaPipe](https://img.shields.io/badge/MediaPipe-0.10+-00B0FF?style=for-the-badge)](https://mediapipe.dev)

> 🌐 **[View Portfolio Page →](https://gunashree2007.github.io/AIFE/)** &nbsp;|&nbsp; ⭐ Star this repo if you found it useful!

AuraGesture is an AI-powered system volume, media, and presentation controller that runs in real-time using a web camera. It leverages computer vision and machine learning (MediaPipe Hands) to track hand coordinates, recognize geometric patterns, and execute local OS shortcuts (volume controls, playback toggles, and slide switching).

The project includes a sleek **glassmorphism-style dashboard** that displays:
- The live webcam feed with MediaPipe annotations.
- Interactive custom gesture mappings.
- Current system stats and master volume level.
- Dynamic scrolling logs of executed keyboard simulations.

---

## 🚀 Portfolio Showcase: How the AI Works

### 1. MediaPipe Hand Landmarks Model
The backend uses **MediaPipe Hands**, a state-of-the-art machine learning model that tracks **21 3D landmarks** on a single hand.
- It operates as a pipeline: a **palm detector** finds the hand bounding box, and a **hand landmark model** performs coordinate regression within the box.
- All landmarks are returned as coordinates $(x, y, z)$ normalized to the image width and height (`[0.0, 1.0]`).

```
                    ⚠️ Hand Landmark Index Chart ⚠️

                 8 (Index Tip)    12 (Middle Tip)
                   *                 *
                7  *              11 *
                   *                 *
             6     *          10     *          16 (Ring Tip)
    4 (Thumb)*     *             *   *             *              20 (Pinky Tip)
             \     *            /    *          15 *                 *
           3  *----+----5------9-----+----13       *              19 *
               \      Index  Middle  Ring  \    14 *                 *
             2  *                           +------*              18 *
                 \                                 \                 *
               1  *                                 * 17             * 17 (Pinky Base)
                   \                               /
                    \                             /
                     +-------------0-------------+
                                (Wrist)
```

### 2. Geometric Heuristics for Gestures (`gesture_engine.py`)
Rather than training a heavy deep learning classifier (which requires large datasets and slows down execution), the system calculates gesture classes on-the-fly using **geometric constraints** on the coordinates.

Here is the logic implemented in `detect_gesture()`:

1. **Finger Extension Check (Index, Middle, Ring, Pinky)**:
   A finger is classified as **Extended (Up)** if its tip coordinate $y$ is higher on the screen than its PIP joint (which has a smaller $y$ coordinate value, since screen coordinates measure $0.0$ at the top and $1.0$ at the bottom):
   $$\text{Finger Up} = y_{\text{tip}} < y_{\text{pip}}$$
   - **Index Up:** `y[8] < y[6]`
   - **Middle Up:** `y[12] < y[10]`
   - **Ring Up:** `y[16] < y[14]`
   - **Pinky Up:** `y[20] < y[18]`

2. **Thumb Extension Check**:
   The thumb's orientation is highly flexible. To check if it is extended, we measure the Euclidean distance between the **Thumb Tip (4)** and the **Index Knuckle (5)**, normalized by the scale of the palm (distance between knuckle 5 and knuckle 17):
   $$\text{Scale Ratio} = \frac{\text{Distance}(P_4, P_5)}{\text{Distance}(P_5, P_{17})}$$
   - If the ratio is $> 0.8$, the thumb is extended outward. If the ratio is small, the thumb is tucked in.

3. **Thumbs Up & Thumbs Down Check**:
   - If all four fingers are folded (fist shape):
     - **Thumbs Up:** If the thumb tip $y$ is higher than the lower joint IP ($y_4 < y_3 < y_2$).
     - **Thumbs Down:** If the thumb tip $y$ is lower than the lower joint IP ($y_4 > y_3 > y_2$).
     - **Fist:** Otherwise, standard folded fist configuration.

4. **Peace Sign Check**:
   - Only the Index and Middle fingers are extended. The Ring and Pinky are folded.

---

## 🛠️ Installation & Setup (Local Host)

Since Python needs to interact directly with your operating system's kernel to change volume and press keys, AuraGesture runs as a local server on your computer.

### Prerequisites
Make sure you have **Python 3.8+** installed.

### Step 1: Install Dependencies
Open your terminal inside the project directory and run:
```bash
pip install -r requirements.txt
```

### Step 2: Run the Web Server
Launch the Flask backend:
```bash
python app.py
```

### Step 3: Open the Interface
Navigate to the following address in your browser:
```
http://localhost:5000
```

---

## 🎮 Default Gesture Mappings

| Hand Gesture | Visual Shape | Mapped PC Action |
| :--- | :---: | :---: |
| **Point Up** | Index finger pointing up, others closed | **Volume Up (+5%)** |
| **Open Palm** | All 5 fingers extended outward | **Volume Down (-5%)** |
| **Fist** | All fingers closed tightly | **Toggle Mute** |
| **Peace Sign** | Index & Middle fingers up, others closed | **Play / Pause Media** |
| **Thumbs Up** | Thumb pointing up, other fingers closed | **Next Slide (Right Arrow)** |
| **Thumbs Down**| Thumb pointing down, other fingers closed | **Previous Slide (Left Arrow)** |

*You can change any of these configurations dynamically from the web panel.*

---

## 🎨 Technology Stack
- **AI Core:** MediaPipe Hands Model (Google AI Edge)
- **Computer Vision:** OpenCV-Python (Webcam stream acquisition, image warping, HUD drawing)
- **System Automation:** `pycaw` (Windows Core Audio Control), `pyautogui` (Direct keyboard driver inputs)
- **Web Dashboard:** Flask (Python Server), Vanilla CSS (Responsive Layout & Custom Glassmorphism Styles), Vanilla JS (Fetch API and polling)
