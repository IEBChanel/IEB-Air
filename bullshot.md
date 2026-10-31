# 📖 HƯỚNG DẪN SỬ DỤNG TOOL AUTO BULLSHOT GEM (bullshot.io)

Tool tự động hóa toàn diện cho dự án **Bull GEM trên Base Network**:
- Làm nhiệm vụ (Daily, Weekly, Social Quests) với độ trễ 5-7s.
- Điểm danh hằng ngày (**Daily Miner Sign-in**).
- Khai thác mỏ 10 phút (**Greenstone Quarry**) & tự động thu hoạch liên tục.
- Tự động hoán đổi (**Auto Swap**) toàn bộ quặng thô sang GEMS.
- Tự động nâng cấp (**Auto Upgrade**) để nhận **+100 XP/lần**, speedrun lên **Level 15**.
- Tự động nạp đá quý (**Auto Stake**) vào Staking Pool hưởng lãi **18% - 35% APY** (không khóa, rút tức thì 0s, 0% phí phạt).
- Hỗ trợ đa ví & đa proxy với cơ chế tự động nhận diện và xoay vòng failover.

---

## 1. Cấu hình file `account.txt`

Bot được tích hợp bộ phân tích thông minh, **tự động nhận diện 4 định dạng ví phổ biến**. Mỗi dòng là 1 tài khoản:

### Các định dạng được hỗ trợ:
1. **Định dạng 1 (Khuyên dùng):** `address|privatekey`
2. **Định dạng 2 (Chỉ Private Key):** `privatekey`
   *(hoặc có tiền tố `0x` đều được, bot tự động tính ra địa chỉ ví tương ứng)*
3. **Định dạng 3 (Dấu hai chấm):** `address:privatekey`
4. **Định dạng 4 (Dấu gạch nối 4 lần):** `address----privatekey`
> ⚠️ **Lưu ý:** Bot sẽ luôn dùng Private Key để ký xác thực EIP-191 và đối chiếu chuẩn xác với địa chỉ ví on-chain để không bao giờ bị lỗi `Signature verification failed`.

---

## 2. Cấu hình file `proxy.txt`

Bot hỗ trợ **4 định dạng proxy phổ biến nhất trên thị trường hiện nay**. Mỗi dòng là 1 proxy:

### Các định dạng được hỗ trợ:
1. **Định dạng 1 (Chuẩn IPV4/Datacenter):** `user:pass@host:port`
2. **Định dạng 2 (Webshare / Proxy dân cư đảo chiều):** `host:port:user:pass`
3. **Định dạng 3 (Đầy đủ giao thức Protocol):** `http://user:pass@host:port` (hoặc `socks5://...`)
4. **Định dạng 4 (Proxy tĩnh IP Whitelist / Không mật khẩu):** `host:port`

> 🔄 **Cơ chế Failover:** Nếu proxy nào bị lỗi kết nối hoặc phản hồi chậm (Timeout / 502 Bad Gateway), bot sẽ **tự động nhảy sang proxy tiếp theo trong danh sách** để quá trình cày cuốc không bao giờ bị gián đoạn.

---

## 3. Các tính năng cốt lõi của Bot

### 💎 Quy tắc Nâng cấp (Auto Upgrade) & Khai thác mỏ tối ưu:
- **Quy tắc Nâng cấp thông minh (`run_upgrades`):**
  1. **Ưu tiên số 1 — Tốc độ đào (Speed):** Tập trung mua tối đa các gói nâng cấp tốc độ đào trước tiên để rút ngắn thời gian mỗi lượt khai thác.
  2. **Giới hạn Power (`MAX_MINING_POWER = 507`):** Chỉ mua nâng cấp sức mạnh đào (Mining Power) cho đến khi đạt mốc **507** thì tự động dừng.
  3. **Giới hạn Cap Mana (`MAX_ENERGY_CAP = 1000`):** Chỉ mua nâng cấp bình năng lượng (Energy Capacity) cho đến tầm **1000** là đủ, sau đó ngưng mua để bảo toàn GEMS.
- **Ưu tiên đào ở bãi lớn nhất có thể (`run_mining`):**
  - Bot tự động sắp xếp danh sách bãi đào từ cấp cao nhất xuống thấp nhất mà tài khoản đủ Level & Power.
  - Dồn toàn bộ năng lượng vào bãi lớn nhất trước, phần năng lượng lẻ còn dư sẽ tự động thả tiếp vào bãi lớn kế tiếp (Ví dụ: Có **120 năng lượng**, bot sẽ tự động thả **4 bãi 25 NL (Lv4) + 1 bãi 20 NL (Lv3)** để tiêu sạch 120 NL).
- **Giãn cách Round tiết kiệm Proxy (180 – 240 phút):**
  - Do các bãi cấp cao (như bãi Lv15) có thời gian đào lên tới 5 tiếng, sau khi chạy xong toàn bộ danh sách acc, bot sẽ nghỉ ngẫu nhiên từ **180 đến 240 phút (3 – 4 tiếng)** trước khi bắt đầu round mới để tiết kiệm dung lượng proxy tối đa.

### 🔄 Auto Swap (Đổi quặng thô sang GEMS):
- Sau mỗi chu kỳ đào mỏ, bot tự động quét kho đồ và đổi toàn bộ quặng thô sang GEMS theo biểu giá game:
  - **Iron Ore:** 0.25 GEMS / quặng
  - **Coal:** 0.35 GEMS / quặng
  - **Copper Ore:** 0.60 GEMS / quặng
  - **Sulfur:** 1.20 GEMS / quặng

### 📈 Auto Staking (Lãi kép 18% - 35% APY):
- Thay vì bán đá quý với giá rẻ, bot tự động đem toàn bộ đá quý đào được nạp vào Staking Pool:
  - **Emerald Pool:** 18% APY
  - **Sapphire Pool:** 14% APY
  - **Ruby Pool:** 12% APY
  - **Diamond Pool:** 22% APY
  - **Obsidian Pool:** 28% APY
  - **Void Gem Pool:** 35% APY
- **Đặc quyền của Staking Bullshot:**
  - **Thời gian khóa: 0 ngày** (Không bị khóa tài sản).
  - **Rút (Unstake) tức thì: 0 giây**.
  - **Phí phạt: 0%**.
  - Khi Unstake, hệ thống trả lại 100% gốc kèm theo toàn bộ lãi GEMS đã tích lũy.

---

## 4. Hướng dẫn chạy Bot

### Bước 1: Cài đặt thư viện cần thiết (nếu chưa có)
Mở Terminal / PowerShell trong thư mục dự án và chạy:
```powershell
pip install requests eth-account
```

### Bước 2: Chạy bot
```powershell
python bullshot.py
```

### Bước 3: Xem tiến trình hoạt động & File `log.txt`
- **Trên màn hình CMD:** In log tinh giản trên 1 dòng theo từng tài khoản (`[Acc 1]`, `[Acc 2]`...), tự động bật màu ANSI chuẩn trên Windows CMD:
  - `Login`: Hiển thị ví rút gọn, cấp độ, XP, GEMS, năng lượng hiện tại.
  - `Nhiệm vụ`: Chỉ báo khi hoàn thành & nhận thưởng.
  - `Đào mỏ / Claim mỏ`: Báo kết quả thu hoạch và tổng số bãi vừa thả.
  - `Swap quặng / Nâng cấp / Stake`: Gom gọn thành 1 dòng tổng kết mỗi khi thực hiện.
- **File `log.txt` (Real-time & Thread-safe):**
  - Tự động xóa làm mới vào đầu mỗi round để chống tràn dữ liệu, khóa luồng (`file_lock`) và ghi trực tiếp ngay khi mỗi acc hoàn thành theo định dạng: `Ví | X Username | Point | Rank`.

---

## 5. Tùy chỉnh Luồng & Cấu hình trong `bullshot.py`
Bạn có thể mở file `bullshot.py` và chỉnh trực tiếp trong hàm `get_config()` ở đầu file tùy theo cấu hình máy và số lượng acc:
```python
def get_config():
    return {
        "THREADS": 10,               # Số luồng chạy song song (1 = chạy từng acc, 5-20 = đa luồng)
        "TARGET_LEVEL": 15,          # Cấp độ mục tiêu
        "AUTO_UPGRADE": True,        # Bật/tắt tự động nâng cấp
        "MAX_MINING_POWER": 507,     # Mua Power tối đa đến 507 thì dừng
        "MAX_ENERGY_CAP": 1000,      # Mua Cap Mana tối đa đến 1000 thì dừng
        "AUTO_SWAP_ORES": True,      # Bật/tắt tự động bán quặng sang GEMS
        "AUTO_STAKE_GEMS": True,     # Bật/tắt tự động Stake đá quý
        "AUTO_CLAIM_STAKING": True,  # Bật/tắt tự động thu hoạch lãi Staking
        "QUEST_DELAY_MIN": 5.0,      # Thời gian delay tối thiểu làm nhiệm vụ (giây)
        "QUEST_DELAY_MAX": 7.0,      # Thời gian delay tối đa làm nhiệm vụ (giây)
        "MAX_MINERS": 50,            # Số máy đào tối đa cho phép thả cùng lúc để xả hết mana
        "ROUND_DELAY_MIN_MINUTES": 180, # Giãn cách tối thiểu mỗi round (phút)
        "ROUND_DELAY_MAX_MINUTES": 240, # Giãn cách tối đa mỗi round (phút)
        "MINING_LOCATION_ID": "greenstone-quarry",
        "DEFAULT_REF": "0x44aca053", # Mã giới thiệu mặc định
    }
```
