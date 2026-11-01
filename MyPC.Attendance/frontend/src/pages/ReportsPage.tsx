export function ReportsPage() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-display">Báo cáo</h1>
      <p className="text-sm text-muted max-w-3xl">
        Xuất XLSX/PDF tháng (không có bảng lương) sẽ hoàn thiện ở P05. Cột chiều sẽ gồm: lần đầu
        xuất hiện, giờ nhận diện chiều (mẫu gần 18:00), mốc 18:00, ảnh đại diện lúc, nghỉ phép đã
        duyệt, ra về đã xác minh.
      </p>
      <div className="rounded-xl border border-line bg-panel p-6 text-sm">
        <ul className="space-y-2 text-muted">
          <li>• Không có trường lương / bảo hiểm / phạt.</li>
          <li>• Cửa sổ chiều theo v1.5: 17:00–23:55.</li>
          <li>• openpyxl đã có trong backend; PDF chờ font Unicode được kiểm tra giấy phép.</li>
        </ul>
      </div>
    </div>
  );
}
