# P02Q Native Resolution Report

## Fact channels (do not conflate)

| Channel | Status in this environment | Value |
|---------|----------------------------|-------|
| VENDOR_SPEC | Documented claim only | EZVIZ H8 Pro / CS-H8-R100-1J5WKFL max **2880×1620** |
| ONVIF_REPORTED | **UNVERIFIED** | No safe on-LAN ONVIF probe executed here |
| FFPROBE_REPORTED | **UNVERIFIED** | Sanitizer implemented; no live URI probed |
| DECODED_MEASURED | **UNVERIFIED for LIVE** | Unit/integration used MOCK frames only (e.g. 640×360 synthetic) |
| BROWSER_PREVIEW | Derived resize | Preview capped ~960px wide — **not** native gate |
| AI_TENSOR | Geometry unit-tested | Inverse map 2880×1620→960×540 and letterbox 640×640 |

## Was real 2880×1620 observed?

**No.** This cloud agent environment has no company EZVIZ camera. Claiming 3K LIVE decode would be fabricated. Gate **CAMERA_LAB = BLOCKED**.

## Geometry unit evidence

- `tests/unit/test_p02q_native_geometry.py` maps all five landmarks + bbox under resize/letterbox/anisotropic cases.
- Native face gate rejects 80px width even if digitally upscaled elsewhere.

## Operator next step

On company Windows LAN: decode MAIN stream, record `frame.shape`, FPS measured, face width/inter-eye at marked floor-one spot; attach to Windows lab report.
