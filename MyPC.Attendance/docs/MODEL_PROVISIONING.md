# Model provisioning (YuNet + SFace)

Full-source ZIPs **exclude** ONNX binaries. Without weights, REAL mode is unavailable → `BLOCKED_MODEL` (no synthetic fallback in production).

## Approved files (pin these hashes)

| File | SHA256 | License |
|------|--------|---------|
| `face_detection_yunet_2023mar.onnx` | `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4` | MIT (OpenCV Zoo) |
| `face_recognition_sface_2021dec.onnx` | `0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79` | Apache-2.0 (OpenCV Zoo) |

Source of truth: `models/manifest.json`.

## Offline install

```powershell
# PowerShell — tải vào models/weights rồi kiểm tra SHA256
$dest = ".\models\weights"
New-Item -ItemType Directory -Force -Path $dest | Out-Null
# Dùng bản đã lưu nội bộ công ty; đối chiếu Get-FileHash -Algorithm SHA256
```

```bash
mkdir -p models/weights
# place onnx files, then:
sha256sum models/weights/*.onnx
# must match manifest exactly
```

Mismatch or missing weights → pipeline reports `weights_bundled` false and paired A/B returns `BLOCKED_MODEL`. Never treat DEMO_SYNTHETIC as physical accuracy.
