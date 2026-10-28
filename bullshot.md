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

### 💎 Speedrun lên Level 15 (Mục tiêu cho acc ref):
- Bot tính toán chính xác bảng điểm kinh nghiệm XP của game:
  - Cần **31,998 XP** để chạm mốc **Level 15 (Deep Core Driller)**.
- **Cơ chế tối ưu:**
  1. Làm nhiệm vụ mở đầu đưa ví từ **Lv 1 lên Lv 4** trong 2 phút.
  2. Mỗi lần thu hoạch mỏ nhận **+75 XP**.
  3. **Mỗi lần mua Nâng cấp (Upgrade) nhận ngay +100 XP**.
  4. Bot sẽ tự động lấy GEMS đào được để mua các nâng cấp giá rẻ (`Mining Power I` giá 250 GEMS, `Energy Capacity I` giá 270 GEMS), vừa tăng chỉ số đào mỏ vừa húp +100 XP liên tục để cán mốc Level 15 sớm nhất.
  5. Khi tài khoản đạt **Level $\ge 15$**, bot sẽ **tự động ngắt chế độ mua nâng cấp** để dồn 100% tài nguyên sang tích trữ GEMS và nạp Staking chờ Airdrop!

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

### Bước 3: Xem tiến trình hoạt động
- Bot hỗ trợ chạy đa luồng và in log tinh giản trên 1 dòng theo từng tài khoản (`[Acc 1]`, `[Acc 2]`...), đồng thời tự động bật màu chuẩn trên Windows CMD (không bị lỗi ký tự `←[...`):
  - `Login`: Hiển thị ví rút gọn, cấp độ, XP, GEMS, năng lượng hiện tại.
  - `Nhiệm vụ`: Chỉ báo khi hoàn thành & nhận thưởng.
  - `Đào mỏ / Claim mỏ`: Báo kết quả thu hoạch hoặc thời gian đào còn lại.
  - `Swap quặng / Nâng cấp / Stake`: Gom gọn thành 1 dòng tổng kết mỗi khi thực hiện.

---

## 5. Tùy chỉnh Luồng & Cấu hình trong `bullshot.py`
Bạn có thể mở file `bullshot.py` và chỉnh trực tiếp trong hàm `get_config()` ở đầu file tùy theo cấu hình máy và số lượng acc:
```python
def get_config():
    return {
        "THREADS": 5,                # Số luồng chạy song song (1 = chạy từng acc, 5-20 = đa luồng)
        "TARGET_LEVEL": 15,          # Đổi level mục tiêu nếu muốn (ví dụ: 10, 15, 20)
        "AUTO_UPGRADE": True,        # Bật/tắt tự động nâng cấp lấy XP
        "AUTO_SWAP_ORES": True,      # Bật/tắt tự động bán quặng sang GEMS
        "AUTO_STAKE_GEMS": True,     # Bật/tắt tự động Stake đá quý
        "AUTO_CLAIM_STAKING": True,  # Bật/tắt tự động thu hoạch lãi Staking
        "QUEST_DELAY_MIN": 5.0,      # Thời gian delay tối thiểu làm nhiệm vụ (giây)
        "QUEST_DELAY_MAX": 7.0,      # Thời gian delay tối đa làm nhiệm vụ (giây)
        "MINING_LOCATION_ID": "greenstone-quarry",
        "DEFAULT_REF": "0x44aca053", # Mã giới thiệu mặc định
    }
```
