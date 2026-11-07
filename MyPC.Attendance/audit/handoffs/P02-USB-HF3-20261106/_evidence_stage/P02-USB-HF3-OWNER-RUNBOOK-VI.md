# P02-USB-HF3 — Runbook chủ sở hữu (DirectShow COM + DevicePath)

**Cổng:** `127.0.0.1:18878` · DataDir **mới** `p02-usb-hf3-candidate` · **KHÔNG** đụng 18876/18877 / HF2 DataDir.

## Root cause đã sửa

**Identity patch (PR #27):** khớp DevicePath↔PnP chỉ khi bằng nhau tuyệt đối VID+PID+MI+toàn bộ instance token — không dùng substring / bỏ qua MI.

**ProgID:** `Dispatch('SystemDeviceEnum')` → `CO_E_CLASSSTRING` (0x800401F3).  
Đúng: `CoCreateInstance(CLSID_SystemDeviceEnum, IID_ICreateDevEnum)` rồi
`CreateClassEnumerator(CLSID_VideoInputDeviceCategory)` và đọc **DevicePath**.

**COM release (PR #27 corrective):** không gọi thủ công `Release()` trên pointer do comtypes sở hữu
(finalizer gọi đúng một lần); gán `COM_RELEASE_WARNING_COUNT` **sau** cleanup/`CoUninitialize`.

**CoInitializeEx (PR #27 corrective):** comtypes 1.4.17 nhận **một** arg `flags`
(`CoInitializeEx(COINIT_APARTMENTTHREADED)`). Lỗi init → `DSHOW_COINIT_FAILED` (không nhầm
`DSHOW_COCREATE_FAILED`). `COM_RELEASE_WARNING_COUNT=0` lúc fail sớm **không** phải physical PASS.

**IPropertyBag.Read (PR #27 corrective):** `var.vt = VT_BSTR` rồi `Read(name, var, None)`
(VARIANT trực tiếp, không `byref`). Owner chứng minh byref/VT_EMPTY → `0x80070057`.
`0x80070002` trên moniker không phải target = thiếu DevicePath (unverified), không chặn cặp khớp duy nhất.

**Update PS 5.1:** `Rename-Item -NewName` chỉ nhận leaf cùng thư mục cha; validate ZIP/layout trước
khi đổi `src`; rollback nếu promote/pip lỗi; từ chối khi cổng 18878 bị process lạ giữ.

## Ứng viên HF3

```powershell
cd <extract>\MyPC.Attendance\scripts\windows
# Lần đầu:
.\p02_usb_hf3_candidate_18878.ps1 -Mode Prepare `
  -FullSourceZip <FULL.zip> -ExpectedSha256 <hex> `
  -ModelsSourceDir <thư-mục-onnx-đã-PIN>
# Đã Prepare sẵn — chỉ vá source (KHÔNG xóa DataDir/venv/models):
.\p02_usb_hf3_candidate_18878.ps1 -Mode Update `
  -FullSourceZip <FULL.zip> -ExpectedSha256 <hex>
.\p02_usb_hf3_candidate_18878.ps1 -Mode Preflight
.\p02_usb_hf3_candidate_18878.ps1 -Mode Diagnose
# Chỉ Start khi CAPTURE_MAPPING_VERIFIED=true
.\p02_usb_hf3_candidate_18878.ps1 -Mode Start
.\p02_usb_hf3_candidate_18878.ps1 -Mode SafeExport
.\p02_usb_hf3_candidate_18878.ps1 -Mode Stop
```

Diagnose (không cần admin) in redacted stage counters:
`DSHOW_ENUM_OK`, `PROPERTY_BAG_BIND_OK_COUNT`, `FRIENDLY_NAME_READ_OK_COUNT`,
`DEVICE_PATH_READ_OK_COUNT`, `DEVICE_PATH_CANONICAL_OK_COUNT`,
`VIDEO_DEVICE_PATH_MATCH_COUNT`, `CAPTURE_MAPPING_VERIFIED`, `DSHOW_FIRST_BLOCKER_CODE`,
`COM_RELEASE_WARNING_COUNT`. Không in raw PnP / DevicePath / frame.

## Smoke vật lý (sau khi Diagnose PASS)

1. Enumerate → chỉ chọn `trusted_live_eligible` / CAPTURE_MAPPING_VERIFIED.
2. Capture thật 1920x1080; index ephemeral; không kết luận 4K từ tên SP.
3. Unplug/replug → index có thể đổi; cùng DevicePath/PnP; không tái dùng index cũ.
4. Hai tab / một capture loop.
5. Soak 30 phút.
6. **Chỉ sau đó** ký CAMERA_LAB USB mới — không tái dùng HMAC EZVIZ.

## Gates

| Gate | Status |
|------|--------|
| CODE_FIX (0x800401F3 ProgID) | CI |
| USB_WINDOWS_PHYSICAL | BLOCKED đến owner PASS |
| USB_STABILITY_30_MIN | BLOCKED |
| USB_CAMERA_LAB_OWNER_SIGN | BLOCKED |
| FACE_PILOT / INSTALLER / PRODUCTION | BLOCKED |

Rollback: PR #26 tip `146d04c`. Không đụng DataDir owner.
