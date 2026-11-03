# -*- coding: utf-8 -*-
"""
RAFLUX.IO AUTOMATION BOT (Base EVM)
- Auto-detects EVM Wallet & Private Key from account.txt
- Proxy rotation from proxy.txt
- SIWE EIP-191 Authentication (ChainId: 8453)
- Bind Referral Code & Collect Welcome Bonus (+20 Points)
- Generate English Name (50 First * 50 Last + 3-5 Digits) & Update Username
- Auto Email Verification via tempmail.py (+5 Points & Unlock Quests)
- Daily Streak Check-in (+1 to +8 Points)
- Auto Cycle & Countdown Scheduler
"""

import os
import sys
import re
import time
import json
import random
import argparse
import threading
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from eth_account import Account
from eth_account.messages import encode_defunct

# Reconfigure stdout for utf-8 & enable ANSI escape sequences on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    try:
        import colorama
        colorama.just_fix_windows_console()
    except Exception:
        pass
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_ulong()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    except Exception:
        pass
    try:
        os.system("")
    except Exception:
        pass

# ==============================================================================
#                       CẤU HÌNH BOT (CONFIG)
# ==============================================================================
DEFAULT_THREADS = 3          # Số luồng chạy đồng thời (mặc định: 3 - mượt mà cho VPS yếu 1-2 core/1GB RAM)
DEFAULT_REF = "11620404"     # Mã giới thiệu Referral
DEFAULT_ACCOUNT_FILE = "account.txt"
DEFAULT_PROXY_FILE = "proxy.txt"
DEFAULT_OUTPUT_FILE = "raflux_accounts.txt"
DEFAULT_SKIP_EMAIL = False   # True: bỏ qua xác minh email
DEFAULT_RUN_ONCE = False     # True: chạy 1 lần rồi thoát, False: lặp 24/7 theo chu kỳ
# ==============================================================================

# Import MailTM from local tempmail.py
try:
    from tempmail import MailTM
except ImportError:
    MailTM = None

# Import Username Generator from local username.py
try:
    from username import generate_random_username
except ImportError:
    def generate_random_username():
        return f"User{random.randint(10000, 99999)}"

# ANSI Colors
class Colors:
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"
    WHITE = "\033[97m"
    RESET = "\033[0m"
    BOLD = "\033[1m"

def log(tag: str, msg: str, color=Colors.WHITE):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"{Colors.MAGENTA}[{ts}]{Colors.RESET} {color}[{tag}]{Colors.RESET} {msg}")

# Thread-safe Locks & Proxies
FILE_LOCK = threading.Lock()
PROXIES_POOL = []

def parse_proxy(proxy_raw: str) -> dict:
    if not proxy_raw:
        return None
    p = proxy_raw.strip()
    if "://" in p:
        return {"http": p, "https": p}
    parts = p.split(":")
    if len(parts) == 4:
        ip, port, user, pw = parts
        url = f"http://{user}:{pw}@{ip}:{port}"
        return {"http": url, "https": url}
    if len(parts) == 2:
        url = f"http://{parts[0]}:{parts[1]}"
        return {"http": url, "https": url}
    return None

def load_proxies(filepath: str = "proxy.txt") -> list:
    if not os.path.exists(filepath):
        return []
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]

def get_proxy_for_index(idx: int) -> dict:
    if not PROXIES_POOL:
        return None
    raw = PROXIES_POOL[idx % len(PROXIES_POOL)]
    return parse_proxy(raw)

def parse_account_line(line: str):
    line = line.strip()
    if not line or line.startswith("#"):
        return None, None
    parts = re.split(r'[,|:\s]+', line)
    pk = None
    for p in parts:
        p_clean = p.strip()
        if re.fullmatch(r'(?:0x)?[a-fA-F0-9]{64}', p_clean):
            pk = p_clean if p_clean.startswith("0x") else f"0x{p_clean}"
            break
    if pk:
        try:
            acc = Account.from_key(pk)
            return acc.address, pk
        except Exception:
            pass
    return None, None

def load_accounts(filepath: str = "account.txt") -> list:
    if not os.path.exists(filepath):
        return []
    accounts = []
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for idx, line in enumerate(f, 1):
            addr, pk = parse_account_line(line)
            if addr and pk:
                accounts.append((idx, addr, pk))
    return accounts

def reset_output_file(output_file: str):
    """Làm trống file lưu kết quả trước mỗi vòng lặp mới."""
    with FILE_LOCK:
        try:
            with open(output_file, "w", encoding="utf-8") as f:
                pass
        except Exception:
            pass

def save_result_account(output_file: str, record: str):
    with FILE_LOCK:
        with open(output_file, "a", encoding="utf-8") as f:
            f.write(record + "\n")


class RafluxClient:
    BASE_URL = "https://api.raflux.io/base/v1"
    CHAIN_ID = 8453
    QUEST_EMAIL_ID = "85fee668-5065-4e43-9085-1f6ef0512b20"

    def __init__(self, acc_idx: int, address: str, private_key: str, proxy: dict = None, ref_code: str = "11620404"):
        self.acc_idx = acc_idx
        self.address = address
        self.private_key = private_key
        self.proxy = proxy
        self.ref_code = ref_code
        self.token = None
        self.username = None
        self.email = None
        self.points = 0
        self.streak = 0
        self.checked_in_today = False
        self.cap_resets_at = None

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
            "Origin": "https://raflux.io",
            "Referer": "https://raflux.io/",
            "Content-Type": "application/json",
            "Accept": "application/json"
        })
        if self.proxy:
            self.session.proxies.update(self.proxy)

    def log(self, msg: str, color=Colors.WHITE):
        tag = f"Acc #{self.acc_idx}"
        log(tag, msg, color)

    def login(self) -> bool:
        """SIWE EIP-191 Authentication on Base chain"""
        try:
            # 1. Request SIWE message & Nonce
            r_siwe = self.session.post(
                f"{self.BASE_URL}/siwe",
                json={"address": self.address, "chainId": self.CHAIN_ID},
                timeout=20
            )
            if r_siwe.status_code != 200:
                self.log(f"SIWE Request failed ({r_siwe.status_code}): {r_siwe.text[:120]}", Colors.RED)
                return False

            res_siwe = r_siwe.json()
            msg_to_sign = res_siwe.get("data", {}).get("message")
            if not msg_to_sign:
                self.log("No SIWE message returned by API", Colors.RED)
                return False

            # 2. Sign message with private key
            acc = Account.from_key(self.private_key)
            signable_msg = encode_defunct(text=msg_to_sign)
            signed = acc.sign_message(signable_msg)
            signature = signed.signature.hex()
            if not signature.startswith("0x"):
                signature = "0x" + signature

            # 3. Post to /login
            login_payload = {
                "address": self.address,
                "message": msg_to_sign,
                "signature": signature,
                "chainId": self.CHAIN_ID
            }
            r_login = self.session.post(f"{self.BASE_URL}/login", json=login_payload, timeout=20)
            if r_login.status_code != 200:
                self.log(f"Login failed ({r_login.status_code}): {r_login.text[:120]}", Colors.RED)
                return False

            res_login = r_login.json()
            data = res_login.get("data", {})
            self.token = data.get("token")
            is_new = data.get("isNewUser", False)

            if not self.token:
                self.log("No JWT token in login response", Colors.RED)
                return False

            self.session.headers["Authorization"] = f"Bearer {self.token}"
            tag_info = " [New User]" if is_new else ""
            self.log(f"Đăng nhập SIWE thành công!{tag_info}", Colors.GREEN)
            return True
        except Exception as e:
            self.log(f"Lỗi kết nối khi đăng nhập SIWE: {e}", Colors.RED)
            return False

    def fetch_profile(self):
        """Fetch current user profile and points"""
        try:
            r = self.session.get(f"{self.BASE_URL}/me", timeout=15)
            if r.status_code == 200:
                data = r.json().get("data", {})
                self.username = data.get("username", "")

            r_pts = self.session.get(f"{self.BASE_URL}/me/points", timeout=15)
            if r_pts.status_code == 200:
                pts_data = r_pts.json().get("data", {})
                self.points = pts_data.get("balance", 0)
        except Exception as e:
            self.log(f"Lỗi lấy thông tin profile: {e}", Colors.YELLOW)

    def bind_referral(self):
        """Bind referral code and collect welcome points"""
        if not self.ref_code:
            return
        try:
            # 1. Claim referral code
            r_claim = self.session.post(
                f"{self.BASE_URL}/referrals/claim",
                json={"code": self.ref_code},
                timeout=15
            )
            if r_claim.status_code in (200, 201):
                self.log(f"Bind Ref '{self.ref_code}' THÀNH CÔNG!", Colors.GREEN)
            elif "ALREADY" in r_claim.text or "NOT_ALLOWED" in r_claim.text:
                pass
            else:
                pass

            # 2. Collect welcome bonus points
            r_welcome = self.session.post(
                f"{self.BASE_URL}/me/referrals/collect-welcome-points",
                json={},
                timeout=15
            )
            if r_welcome.status_code == 200:
                res_w = r_welcome.json().get("data", {})
                pts_w = res_w.get("points", 20)
                self.log(f"Thu thập Welcome Bonus: +{pts_w} Points!", Colors.GREEN)
        except Exception as e:
            self.log(f"Lỗi bind referral: {e}", Colors.YELLOW)

    def update_username_if_needed(self):
        """Update username to natural English format if currently default"""
        try:
            if not self.username or "collect" in self.username.lower() or "revive" in self.username.lower():
                for _ in range(5):
                    candidate = generate_random_username()
                    r_check = self.session.get(f"{self.BASE_URL}/username/available?username={candidate}", timeout=10)
                    if r_check.status_code == 200 and r_check.json().get("data", {}).get("available"):
                        r_put = self.session.put(f"{self.BASE_URL}/me/username", json={"username": candidate}, timeout=15)
                        if r_put.status_code == 200:
                            self.username = candidate
                            self.log(f"Đã cập nhật Username: @{self.username}", Colors.CYAN)
                            break
        except Exception as e:
            self.log(f"Lỗi cập nhật username: {e}", Colors.YELLOW)

    def verify_email(self):
        """Verify email using tempmail.py to unlock quest board and earn +5 FP"""
        if not MailTM:
            return
        try:
            # Check if email is already verified
            r_q = self.session.get(f"{self.BASE_URL}/quests", timeout=15)
            if r_q.status_code == 200:
                q_data = r_q.json().get("data", {})
                if q_data.get("emailVerified"):
                    return

            self.log("Bắt đầu xác minh Email (nhận +5 FP & mở khóa quest board)...", Colors.CYAN)
            mail = MailTM(proxy=self.proxy)
            self.email = mail.create_account()
            mail.login()

            # 1. Check email
            self.session.post(f"{self.BASE_URL}/email/check", json={"email": self.email}, timeout=15)

            # 2. Request OTP
            r_req = self.session.post(f"{self.BASE_URL}/email/otp/request", json={"email": self.email}, timeout=15)
            if r_req.status_code != 200:
                self.log(f"Yêu cầu OTP email thất bại ({r_req.status_code}): {r_req.text[:80]}", Colors.YELLOW)
                return

            # 3. Poll for OTP
            otp_code = None
            for _ in range(15):
                time.sleep(3)
                msgs = mail.messages()
                if msgs:
                    mid = msgs[0]["id"]
                    full = mail.message(mid)
                    text = (full.get("text") or "") + " " + full.get("subject", "")
                    m = re.search(r"\b(\d{6})\b", text)
                    if m:
                        otp_code = m.group(1)
                        break

            if otp_code:
                # 4. Verify OTP
                r_ver = self.session.post(f"{self.BASE_URL}/email/otp/verify", json={"code": otp_code}, timeout=15)
                if r_ver.status_code == 200:
                    self.log(f"Xác minh Email thành công ({self.email})!", Colors.GREEN)
                    # 5. Claim verify-email quest
                    r_claim = self.session.post(f"{self.BASE_URL}/quests/{self.QUEST_EMAIL_ID}/claim", json={}, timeout=15)
                    if r_claim.status_code == 200:
                        self.log("Claim nhiệm vụ Verify Email: +5 FP!", Colors.GREEN)
            else:
                self.log(f"Hết thời gian chờ mã OTP email ({self.email})", Colors.YELLOW)
        except Exception as e:
            self.log(f"Lỗi xác minh email: {e}", Colors.YELLOW)

    def do_check_in(self):
        """Execute Daily Check-in Streak"""
        try:
            r = self.session.post(f"{self.BASE_URL}/quests/check-in", json={}, timeout=15)
            if r.status_code == 200:
                res = r.json().get("data", {})
                reward = res.get("fpAwarded", res.get("rewardFp", 1))
                st = res.get("streak", {})
                self.streak = st.get("current", 1)
                self.checked_in_today = True
                self.log(f"Điểm danh Check-in Ngày {self.streak} THÀNH CÔNG: +{reward} FP!", Colors.GREEN)
            elif "ALREADY" in r.text or r.status_code == 409:
                self.checked_in_today = True
                self.log("Hôm nay đã điểm danh Check-in rồi.", Colors.WHITE)
            else:
                self.log(f"Điểm danh Check-in: {r.status_code} {r.text[:80]}", Colors.YELLOW)
        except Exception as e:
            self.log(f"Lỗi điểm danh Check-in: {e}", Colors.YELLOW)

    def check_and_claim_quests(self):
        """Scan available quests and claim any that are ready"""
        try:
            r = self.session.get(f"{self.BASE_URL}/quests", timeout=15)
            if r.status_code != 200:
                return
            data = r.json().get("data", {})
            self.cap_resets_at = data.get("capResetsAt")
            quests = data.get("quests", [])
            for q in quests:
                qid = q.get("id")
                title = q.get("title")
                status = q.get("status")

                if status == "CLAIMABLE":
                    r_c = self.session.post(f"{self.BASE_URL}/quests/{qid}/claim", json={}, timeout=15)
                    if r_c.status_code == 200:
                        reward = r_c.json().get("data", {}).get("fpAwarded", 0)
                        self.log(f"Claim nhiệm vụ [{title}]: +{reward} FP!", Colors.GREEN)
        except Exception as e:
            self.log(f"Lỗi kiểm tra quests: {e}", Colors.YELLOW)

    def run_full_pipeline(self, skip_email: bool = False) -> dict:
        """Run complete account registration, verification, checkin and tasks"""
        short_addr = f"{self.address[:6]}...{self.address[-4:]}"
        self.log(f"Bắt đầu tài khoản | Ví: {short_addr}", Colors.CYAN)

        if not self.login():
            return {"status": "FAILED_LOGIN", "address": self.address}

        # 1. Fetch info
        self.fetch_profile()

        # 2. Bind Ref & Collect Welcome Points (+20 pts)
        self.bind_referral()

        # 3. Update natural Username
        self.update_username_if_needed()

        # 4. Verify Email (+5 pts)
        if not skip_email:
            self.verify_email()

        # 5. Daily Check-in Streak
        self.do_check_in()

        # 6. Check and Claim Quests
        self.check_and_claim_quests()

        # 7. Final Points Query
        self.fetch_profile()
        self.log(f"TỔNG KẾT: Points: {self.points} | Streak: Day {self.streak} | User: @{self.username}", Colors.GREEN)

        return {
            "status": "SUCCESS",
            "address": self.address,
            "private_key": self.private_key,
            "username": self.username or "N/A",
            "email": self.email or "N/A",
            "points": self.points,
            "streak": self.streak,
            "cap_resets_at": self.cap_resets_at
        }


def process_account(item: tuple, proxies: list, ref_code: str, skip_email: bool) -> dict:
    idx, addr, pk = item
    proxy = get_proxy_for_index(idx - 1)
    client = RafluxClient(acc_idx=idx, address=addr, private_key=pk, proxy=proxy, ref_code=ref_code)
    return client.run_full_pipeline(skip_email=skip_email)


def run_cycle(accounts: list, proxies: list, ref_code: str, threads: int, skip_email: bool, output_file: str):
    log("SCHEDULER", f"Bắt đầu xử lý {len(accounts)} tài khoản với {threads} luồng...", Colors.MAGENTA)
    results = []
    earliest_reset = None

    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = {
            executor.submit(process_account, item, proxies, ref_code, skip_email): item
            for item in accounts
        }
        for future in as_completed(futures):
            item = futures[future]
            try:
                res = future.result()
                results.append(res)
                if res.get("status") == "SUCCESS":
                    rec = f"{res['address']}|{res['private_key']}|{res['username']}|{res['email']}|{res['points']}|Day_{res['streak']}|SUCCESS"
                    save_result_account(output_file, rec)
                    reset_time = res.get("cap_resets_at")
                    if reset_time and not earliest_reset:
                        earliest_reset = reset_time
            except Exception as e:
                log(f"Acc #{item[0]}", f"Lỗi ngoại lệ: {e}", Colors.RED)

    success_cnt = sum(1 for r in results if r.get("status") == "SUCCESS")
    total_pts = sum(r.get("points", 0) for r in results if r.get("status") == "SUCCESS")
    log("SCHEDULER", f"Hoàn thành lượt chạy: {success_cnt}/{len(accounts)} thành công | Tổng Points: {total_pts}", Colors.GREEN)
    return earliest_reset


def countdown(seconds: int):
    while seconds > 0:
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        sys.stdout.write(f"\r{Colors.YELLOW}[COUNTDOWN]{Colors.RESET} Chờ phiên tiếp theo sau: {h:02d}h {m:02d}m {s:02d}s ... ")
        sys.stdout.flush()
        time.sleep(1)
        seconds -= 1
    sys.stdout.write("\r" + " " * 75 + "\r")
    sys.stdout.flush()


def parse_iso_to_seconds(iso_str: str) -> int:
    try:
        target = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = (target - now).total_seconds()
        return max(60, int(delta) + 10)
    except Exception:
        return 86400


def print_banner(args, num_accounts: int):
    print(f"{Colors.BOLD}{Colors.CYAN}====================================================={Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}              RAFLUX.IO AUTO BOT (BASE EVM)          {Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}====================================================={Colors.RESET}")
    print(f"File tài khoản  : {args.account} ({num_accounts} ví hợp lệ)")
    print(f"File proxy      : {args.proxy} ({len(PROXIES_POOL)} proxies)")
    print(f"Mã giới thiệu   : {args.ref}")
    print(f"Số luồng        : {args.threads}")
    print(f"Xác minh Email  : {'Bỏ qua' if args.skip_email else 'Tự động (tempmail.py)'}")
    print(f"Chế độ lặp      : {'Chạy 1 lần (--once)' if args.once else 'Tự động lặp theo chu kỳ (24/7)'}")
    print(f"File lưu kết quả: {args.output}")
    print(f"{Colors.BOLD}{Colors.CYAN}====================================================={Colors.RESET}\n")


def main():
    parser = argparse.ArgumentParser(description="Raflux Auto Bot (Base EVM)")
    parser.add_argument("--account", default=DEFAULT_ACCOUNT_FILE, help=f"Đường dẫn file tài khoản (mặc định: {DEFAULT_ACCOUNT_FILE})")
    parser.add_argument("--proxy", default=DEFAULT_PROXY_FILE, help=f"Đường dẫn file proxy (mặc định: {DEFAULT_PROXY_FILE})")
    parser.add_argument("--ref", default=DEFAULT_REF, help=f"Mã giới thiệu Referral (mặc định: {DEFAULT_REF})")
    parser.add_argument("--threads", type=int, default=DEFAULT_THREADS, help=f"Số luồng đồng thời (mặc định: {DEFAULT_THREADS})")
    parser.add_argument("--skip-email", action="store_true", default=DEFAULT_SKIP_EMAIL, help="Bỏ qua xác minh email")
    parser.add_argument("--once", action="store_true", default=DEFAULT_RUN_ONCE, help="Chạy đúng 1 lần rồi thoát (không lặp theo chu kỳ)")
    parser.add_argument("--output", default=DEFAULT_OUTPUT_FILE, help=f"File xuất kết quả (mặc định: {DEFAULT_OUTPUT_FILE})")
    args = parser.parse_args()

    global PROXIES_POOL
    PROXIES_POOL = load_proxies(args.proxy)
    accounts = load_accounts(args.account)

    print_banner(args, len(accounts))

    if not accounts:
        log("ERROR", f"Không tìm thấy tài khoản hợp lệ trong {args.account}!", Colors.RED)
        return

    cycle_num = 1
    while True:
        if cycle_num > 1:
            # Xóa màn hình console cho vòng lặp mới gọn gàng
            try:
                os.system("cls" if sys.platform == "win32" else "clear")
            except Exception:
                pass
            print_banner(args, len(accounts))

        log("SYSTEM", f"=== BẮT ĐẦU VÒNG CHẠY #{cycle_num} ===", Colors.CYAN)
        reset_output_file(args.output)
        log("SYSTEM", f"Đã làm mới file lưu tài khoản: {args.output}", Colors.YELLOW)

        resets_at = run_cycle(
            accounts=accounts,
            proxies=PROXIES_POOL,
            ref_code=args.ref,
            threads=args.threads,
            skip_email=args.skip_email,
            output_file=args.output
        )

        if args.once:
            log("SYSTEM", "Chế độ --once đã hoàn thành. Kết thúc bot.", Colors.GREEN)
            break

        wait_sec = parse_iso_to_seconds(resets_at) if resets_at else 86400
        log("SCHEDULER", f"Chu kỳ tiếp theo được lên lịch sau {wait_sec // 3600}h {(wait_sec % 3600) // 60}m...", Colors.YELLOW)
        countdown(wait_sec)
        cycle_num += 1


if __name__ == "__main__":
    main()

