# 📖 HƯỚNG DẪN SỬ DỤNG BOT 4DLABS (DÀNH CHO NGƯỜI MỚI / TESTER)

Tài liệu hướng dẫn từng bước để cài đặt, thiết lập và chạy tool tự động tương tác dApp **4Dlabs** ([dapp.4dlabs.space](https://dapp.4dlabs.space)) trên mạng **BNB Smart Chain (BSC Mainnet)**.

---

## 📌 1. CƠ CHẾ HOẠT ĐỘNG CHÍNH CỦA BOT

* **Đăng nhập dApp**: Tự động ký chữ ký điện tử Privy SIWE (không tốn gas) để lấy phiên đăng nhập.
* **Tự động rút Gas từ sàn Binance (Chống Sybil 100%)**:
  - Tự động quét các ví trong danh sách. Nếu phát hiện ví nào có số dư `0 BNB`, bot sẽ kết nối trực tiếp với **Binance API** để rút BNB về ví đó.
  - Nguồn tiền gửi trên BSCScan là **Hot Wallet của sàn Binance**, giúp dàn ví sạch hoàn toàn trên đồ thị On-chain (không bị dính chùm Sybil).
  - Số lượng BNB rút được **random ngẫu nhiên vượt mức tối thiểu của sàn từ 5% – 50%**, giúp mỗi ví nhận một lượng tiền lẻ khác nhau.
* **Daily Check-in On-chain**:
  - Gửi giao dịch `checkIn(location)` trực tiếp lên hợp đồng thông minh BSC.
  - Phí gas cực rẻ: chỉ khoảng `~0.0000014 BNB` (~0.001$).
  - **Mẹo tối ưu điểm thưởng**: Duy trì check-in liên tục **7 ngày** để kích hoạt thưởng chuỗi (**x3 điểm**: từ 5 điểm lên **15 điểm/ngày**).
* **Cơ chế Chống Phát Hiện Bot Toàn Diện**:
  - **Random Continent**: Mỗi ví tự động chọn ngẫu nhiên 1 trong 6 châu lục (`AFR`, `ASN`, `EUR`, `NAM`, `OCE`, `SAM`).
  - **Random Time (UTC+7)**: Tự động lên lịch giờ check-in ngẫu nhiên mỗi ngày trong khung giờ sinh hoạt tự nhiên (07:00 – 22:00 giờ Việt Nam).
  - **Random Delay**: Giãn cách ngẫu nhiên giữa các ví (55s – 95s) để các giao dịch on-chain không bị dính chùm cùng một block.

---

## 🛠️ 2. CHUẨN BỊ MÔI TRƯỜNG & CÀI ĐẶT

### Bước 1: Cài đặt Python
* Cài đặt **Python 3.10 trở lên** (Tải tại [python.org](https://www.python.org/downloads/)).
* *Lưu ý quan trọng*: Lúc cài đặt, nhớ tích chọn ô **`Add Python to PATH`**.

### Bước 2: Cài đặt các thư viện cần thiết
Mở cửa sổ dòng lệnh (**CMD** hoặc **PowerShell**) tại thư mục chứa bot và chạy lệnh:

```bash
pip install requests eth-account eth-abi eth-utils
```

---

## 📂 3. CÁC FILE CẦN THIẾT TRONG THƯ MỤC

| Tên File | Vai trò | Cách điền dữ liệu |
| :--- | :--- | :--- |
| **`4dlabs.py`** | File mã nguồn bot chính | Đã tối ưu sẵn, có thể mở chỉnh thời gian nghỉ hoặc số luồng nếu muốn. |
| **`account.txt`** | Danh sách các ví tham gia test | Mỗi dòng một ví theo định dạng: `ĐịaChỉVí\|PrivateKey` hoặc chỉ cần `PrivateKey`. |
| **`binance.txt`** | API Key & Secret của sàn Binance | Dòng 1: API Key, Dòng 2: Secret Key (Yêu cầu bật quyền `Enable Withdrawals`). |
| **`proxy.txt`** | Danh sách Proxy (Tùy chọn) | Mỗi dòng một proxy (hỗ trợ `IP:Port` hoặc `IP:Port:User:Pass`). Nếu không dùng proxy có thể để file trống. |

---

## ⚙️ 4. TÙY CHỈNH CẤU HÌNH (FILE `4dlabs.py`)

Mở file [`4dlabs.py`](file:///d:/IEB/2026/4dlabs/4dlabs.py), tại phần đầu file (từ dòng 17) bạn có thể tùy chỉnh nếu cần:

```python
def get_config():
    return {
        "THREADS": 10,                        # Số luồng chạy (1 = tuần tự từng ví, 10 = song song)
        "INVITATION_CODE": "",                # Mã Ref (để trống nếu test độc lập, hoặc điền mã ref nếu muốn)
        "AUTO_WITHDRAW_BINANCE": True,        # Tự động rút BNB từ sàn Binance vào ví có balance = 0
        "BINANCE_KEY_FILE": "binance.txt",    # File chứa Binance API Key & Secret
        "BINANCE_WITHDRAW_MIN_PCT": 5,        # Tối thiểu ngẫu nhiên vượt mức min sàn (> min 5%)
        "BINANCE_WITHDRAW_MAX_PCT": 50,       # Tối đa ngẫu nhiên vượt mức min sàn (> min 50%)
        "BINANCE_WITHDRAW_DELAY_MIN": 20,     # Độ trễ ngẫu nhiên giữa các lần rút sàn (giây)
        "BINANCE_WITHDRAW_DELAY_MAX": 45,     # Độ trễ ngẫu nhiên giữa các lần rút sàn (giây)
        "PREFERRED_CONTINENT": "RANDOM",      # "RANDOM" (an toàn nhất) hoặc "ASN", "AFR", "EUR",...
        "WALLET_DELAY_MIN_SECONDS": 55,       # Giãn cách tối thiểu giữa các ví (giây)
        "WALLET_DELAY_MAX_SECONDS": 95,       # Giãn cách tối đa giữa các ví (giây)
        "RANDOM_DAILY_SCHEDULE_UTC7": True,   # Tự động chọn giờ ngẫu nhiên mỗi ngày (giờ VN)
        "SCHEDULE_HOUR_START_UTC7": 7,        # Khung giờ sớm nhất chạy bot (7h sáng)
        "SCHEDULE_HOUR_END_UTC7": 22,         # Khung giờ muộn nhất chạy bot (22h tối)
    }
```

---

## 🔑 5. HƯỚNG DẪN TẠO API KEY TRÊN BINANCE

1. Đăng nhập vào tài khoản **Binance**, vào mục **API Management (Quản lý API)**.
2. Chọn **Create API (Tạo API)** (chọn loại System Generated).
3. Đặt tên gợi nhớ (ví dụ: `4dlabs-withdraw`).
4. Tại mục **API Restrictions (Phân quyền API)**:
   - Tích chọn **`Enable Reading`** (Đọc thông tin cấu hình).
   - Tích chọn **`Enable Withdrawals`** (Cho phép rút tiền).
   - *(Khuyên dùng)*: Tích chọn **Restrict access to trusted IPs only** và điền IP máy tính của bạn để đảm bảo an toàn tuyệt đối.
5. Sao chép **API Key** và **Secret Key** dán vào file [`binance.txt`](file:///d:/IEB/2026/4dlabs/binance.txt):
   - Dòng 1: API Key
   - Dòng 2: Secret Key

---

## 🚀 6. HƯỚNG DẪN CHẠY BOT

Mở **PowerShell** hoặc **Command Prompt (CMD)** tại thư mục `4dlabs` và chạy lệnh:

```bash
python 4dlabs.py
```

### Các bước bot sẽ tự động thực hiện:
1. **Kiểm tra số dư các ví**: Quét toàn bộ ví trong `account.txt`.
2. **Tự động rút từ Binance**: Nếu phát hiện ví nào có balance = 0, bot tự gửi lệnh rút một lượng BNB lẻ ngẫu nhiên từ Binance về ví đó (kèm delay an toàn giữa các lệnh rút).
3. **Thực hiện Check-in**: Các ví lần lượt đăng nhập Privy và gửi lệnh check-in lên Smart Contract BSC.
4. **Ghi log & Lên lịch ngày mai**:
   - Ghi lại bảng xếp hạng, điểm số, trạng thái check-in vào file **`log_4dlabs.txt`**.
   - Tự động tính toán mốc giờ ngẫu nhiên ngày tiếp theo (theo giờ Việt Nam UTC+7) và bật đồng hồ đếm ngược.

---

## ❓ 7. MỘT SỐ CÂU HỎI THƯỜNG GẶP (FAQ)

### Q: Tôi muốn dừng bot thì làm sao?
> Bấm tổ hợp phím **`Ctrl + C`** trên màn hình Terminal/CMD là bot sẽ dừng an toàn ngay lập tức.

### Q: File `log_4dlabs.txt` xem cái gì?
> File này tự động làm mới ở mỗi chu kỳ, lưu lại bảng thống kê chi tiết theo thời gian thực:
> `Địa chỉ ví | Mã Ref riêng | Tổng điểm (Checkin/Social/Ref) | Rank | Trạng thái Check-in hôm nay`

### Q: Tại sao rút tiền từ Binance lại chống Sybil an toàn nhất?
> Vì nguồn gửi trên blockchain hiển thị là **Binance Hot Wallet** (hàng triệu người cùng rút từ đây). Thuật toán của các quỹ (Binance Labs, YZi Labs, LayerZero...) không thể liên kết các ví này lại với nhau, cắt đứt 100% mối quan hệ on-chain giữa các ví.
