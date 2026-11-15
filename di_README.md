# DI.XYZ AUTO BOT (BNB SMART CHAIN)

Thư mục: `D:\IEB\2026\di`
Dự án: **Decentralized Intelligence** (https://di.xyz/check-in) — Định giá 100M$, OKX Ventures & DraperDragon đầu tư.

---

## 1. Cấu trúc thư mục
- `withdraw.py`: File tự động kiểm tra số dư BNB trên BSC Mainnet. Ví nào `< 0.002 BNB` sẽ tự động rút từ sàn Binance qua SAPI.
- `checkin.py`: File tự động đăng nhập Privy SIWE, làm task MXH (Telegram + X) và gửi Transaction Check-in On-Chain vào contract `0xC361Eb6E91abD289c912BfCABc644076680659B6`.
- `account.txt`: Danh sách 100 ví (`Address|PrivateKey`).
- `binance.txt`: Cấu hình Binance API (Dòng 1: API Key, Dòng 2: Secret Key có quyền Withdraw).
- `proxy.txt`: Danh sách proxy xoay vòng.
- `log_di.txt`: File log kết quả điểm số và chuỗi check-in thời gian thực.

---

## 2. Hướng dẫn sử dụng

### Bước 1: Kiểm tra và nạp gas BNB từ Binance (nếu ví < 0.002 BNB)
Chạy lệnh:
```bash
cd D:\IEB\2026\di
python withdraw.py
```
- Bot sẽ quét số dư on-chain của cả 100 ví.
- Ví nào `< 0.002 BNB` sẽ được tự động rút một khoản ngẫu nhiên (`~0.0051 - 0.0055 BNB`, vượt min sàn) từ Binance về ví con.
- Có delay ngẫu nhiên 20 - 45s giữa các lần rút để bảo vệ tài khoản Binance và chống rate limit.

### Bước 2: Chạy Check-in & Tasks hàng ngày
Chạy lệnh:
```bash
cd D:\IEB\2026\di
python checkin.py
```
- Bot chạy đa luồng (mặc định 10 threads).
- Tự động đăng nhập SIWE, sync danh tính với backend DI.
- Tự động hoàn thành task Telegram (+100 PTS) và các task hàng ngày.
- Tự động gửi transaction on-chain gọi `checkIn()` trên BSC Mainnet và confirm để tích lũy chuỗi 30 ngày (đủ điều kiện Whitelist Mint NFT).
- Tự động lặp lại ngẫu nhiên trong khung giờ 7h00 - 8h00 sáng hàng ngày theo giờ Việt Nam (UTC+7, tương ứng mốc 00h00 - 01h00 UTC khi hệ thống DI.XYZ reset ngày mới), tránh bị trôi lệch giờ và không bỏ lỡ ngày check-in.
