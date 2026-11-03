# HƯỚNG DẪN VẬN HÀNH MININGMACHINE AUTO BOT

Tài liệu hướng dẫn vận hành hệ thống bot tự động cày [MiningMachine.io](https://miningmachine.io) bao gồm 2 file chính:
1. **`miningmachine_reg.py`**: Chuyên đăng ký ví EVM, lọc X sống, bind Ref sạch (không tạo ref ảo).
2. **`miningmachine_task.py`**: Chuyên làm nhiệm vụ (tasks), kích hoạt máy đào và tự động Schedule lặp phiên 24/7.

---

## 📁 CÁC FILE DỮ LIỆU ĐẦU VÀO & ĐẦU RA

| Tên file | Mục đích |
| :--- | :--- |
| **`x.txt`** | Danh sách tài khoản Twitter/X (chứa `auth_token` & `ct0`). Nick die sẽ tự động bị xóa khỏi file này. |
| **`proxy.txt`** | Danh sách proxy (định dạng `user:pass@ip:port` hoặc `ip:port:user:pass`). |
| **`account.txt`** | Danh sách tài khoản đã bind X thành công (ví live). |
| **`x_die.txt`** | Tự động lưu lại các nick X bị lỗi/die để kiểm tra lại nếu cần. |

---

## 🚀 1. ĐĂNG KÝ TÀI KHOẢN: `miningmachine_reg.py`

### Cơ chế hoạt động:
* **Ví ở hàng chờ (Standby Wallet):** Bot sinh ví EVM mới nhưng **CHƯA GỌI BIND REF NGAY**.
* Lần lượt rút nick X từ `x.txt` để thử liên kết:
  * **Nếu X die:** Tự động lưu vào `x_die.txt`, xóa sạch khỏi `x.txt`, và **KHÔNG BIND REF** (không tạo ref ảo).
  * **Nếu X sống:** Liên kết OAuth thành công $\rightarrow$ Mới gọi `bind_referral` $\rightarrow$ Xuất ví vào `account.txt`.
* **Kết quả:** Đảm bảo **100% lượt Ref phát sinh đều là ref thật, hoạt động**, không bị hệ thống gắn cờ gian lận.

### Lệnh chạy mẫu:
```bash
# 1. Chạy mặc định (tạo 10 acc live, chạy 3 luồng):
python miningmachine_reg.py

# 2. Tùy chỉnh số lượng tài khoản Live cần tạo và số luồng:
python miningmachine_reg.py --count 50 --threads 5

# 3. Đổi mã giới thiệu (Ref code) khác:
python miningmachine_reg.py --count 100 --threads 10 --ref JeS5fG7_
```

---

## ⛏️ 2. LÀM NHIỆM VỤ & KHAI THÁC 24/7: `miningmachine_task.py`

### Cơ chế hoạt động:
* Đọc danh sách tài khoản hợp lệ từ `account.txt`.
* Tự động đăng nhập lại bằng Private Key (SIWE EIP-191) để refresh token.
* **Hoàn thành full 4/4 Tasks:**
  * Auto Follow RigGrid trên Twitter (tự động đổi proxy nếu gặp lỗi kết nối 502).
  * Kích hoạt tracking link và chờ đúng dwell time cho nhiệm vụ đọc tin tức.
  * Tự động bypass các nhiệm vụ like/repost.
* **Khai thác máy đào (Auto Farm):**
  * Tự động kích hoạt Free Miner (đưa công suất lên **27.5 MP**).
* **Schedule 24/7:**
  * Canh mốc `sessionEndsAt` của tất cả các tài khoản.
  * Hiển thị đồng hồ đếm ngược sinh động trên màn hình console.
  * Khi hết phiên, bot tự động thức dậy claim phần thưởng và bật lại chu kỳ đào tiếp theo.

