# P02 / P01.5-HF License & SBOM notes

| Component | License posture |
|-----------|-----------------|
| OpenCV Zoo YuNet / SFace ONNX | Apache-2.0 (opencv_zoo); weights gitignored; SHA256 pinned in manifest |
| OpenCV (cv2) | Apache-2.0 |
| FFmpeg (system / OpenCV CAP_FFMPEG) | Verify local Windows build flags (LGPL vs GPL) before redistribution |
| FastAPI / SQLAlchemy / cryptography | BSD / Apache / Apache |
| React / Vite | MIT |
| Person detector YOLOX-Nano | **Not bundled** — candidate only after exact weight license + SHA256 audit |
| Ultralytics YOLO | **Not used** (AGPL default risk) |

Do not commit proprietary EZVIZ SDK blobs. Do not redistribute ONNX weights in public audit ZIPs unless redistribution policy allows.
