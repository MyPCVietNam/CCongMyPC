# P01.5 Recognition Quality Notes

**Not a claim of universal accuracy.** Figures below are engineering notes from the Linux agent environment with OpenCV 4.14 + Zoo ONNX weights.

## Pipeline

- Detector: YuNet 2023mar (SHA256 `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4`)
- Embedder: SFace 2021dec (SHA256 `0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79`)
- Preprocess: native-frame YuNet row → `alignCrop` → `feature` → L2
- Match: cosine, threshold 0.45, margin 0.05, **best-by-identity** aggregate

## Enrollment quality gates (starting experimental targets)

| Metric | Gate |
|--------|------|
| Face width | ≥ 120 px hard (prefer ≥ 160) |
| Inter-eye | ≥ 40 px when landmarks present |
| Laplacian variance | ≥ 40 |
| Detection score | ≥ 0.6 |
| Illumination | reject mean &lt; 40 or overexposed |
| Upscaling poor faces | **Forbidden** as pass path |

## Lab measurements still required on Windows + EZVIZ

- Native face width / inter-eye at enrollment stand positions
- Pose yaw distribution for LEFT/RIGHT slots under mirrored preview
- False match / unknown / ambiguous counts on gallery of real staff
- Inference latency + CPU/RSS under service load
- Body height px from high-angle stream (expect frequent BODY_CAPTURE_BLOCKED)

Do **not** advertise 99% recognition. Anti-spoofing via pose turns is **not** validated PAD.
