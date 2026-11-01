import { vi } from "../i18n/vi";

export function OvertimePage() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-display">Theo dõi tăng ca</h1>
      <p className="text-muted text-sm max-w-3xl">
        Phân biệt <strong className="text-ink font-medium">{vi.labels.lastSeen}</strong> và{" "}
        <strong className="text-ink font-medium">{vi.labels.verifiedExit}</strong>. Cổng xác minh
        ra về tự động đang <span className="text-warn">BLOCKED</span> cho đến khi hiệu chỉnh camera
        thực tế đạt EXIT_VERIFICATION_PASS. Dùng xác nhận thủ công của người phụ trách tính công.
      </p>
      <div className="rounded-xl border border-line bg-panel p-6 text-sm text-muted">
        Chưa có phiên tăng ca đang chạy. Engine trạng thái (NOT_STARTED → … → PENDING_REVIEW) đã có
        ở lớp domain; UI thẻ ACTIVE sẽ nối ở P04.
      </div>
    </div>
  );
}
