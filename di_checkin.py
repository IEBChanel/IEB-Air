"""
DI.XYZ AUTO CHECK-IN & TASKS BOT (checkin.py)
-------------------------------------------------------------
- Thư mục: D:\\IEB\\2026\\di
- Dự án: Decentralized Intelligence (https://di.xyz/check-in)
- Vòng gọi vốn: 100M$ Valuation, Backed bởi OKX Ventures, DraperDragon.
- Chức năng:
  + Tự động đăng nhập Web3 SIWE qua Privy SDK (App ID: cmsdjnd0n00by0djvu64acvd1).
  + Tự động Sync Identity và đọc trạng thái tài khoản (/api/engagement/me).
  + Tự động làm các Task MXH: Telegram Join (+100 pts), Daily Telegram Msg (+50 pts),
    Follow X, Daily Like, Repost, Reply (nếu có liên kết X).
  + Tự động gửi Transaction Check-in On-Chain trên BNB Smart Chain (BSC Mainnet)
    vào Smart Contract 0xC361Eb6E91abD289c912BfCABc644076680659B6 (hàm checkIn()).
  + Tự động confirm attempt và tích lũy chuỗi 30 ngày để Whitelist Mint NFT DI.
  + Kiểm tra số dư gas BNB: nếu ví < 0.0005 BNB sẽ cảnh báo chạy file withdraw.py.
  + Hỗ trợ đa luồng (Multi-threading), xoay vòng proxy, ghi log real-time vào log_di.txt.
"""

import os
import sys
import time
import random
import re
import ctypes
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
import requests
from eth_account import Account
from eth_account.messages import encode_defunct


# ==================== CẤU HÌNH BOT ====================
def get_config():
    return {
        # Số luồng chạy cùng lúc (khuyên dùng 5 - 10 luồng)
        "THREADS": 10,

        # File dữ liệu
        "ACCOUNT_FILE": "account.txt",
        "PROXY_FILE": "proxy.txt",
        "LOG_FILE": "log_di.txt",

        # Smart Contract Check-In trên BSC Mainnet (Chain ID: 56)
        "CHAIN_ID": 56,
        "CHECKIN_CONTRACT": "0xC361Eb6E91abD289c912BfCABc644076680659B6",
        "CHECKIN_DATA": "0x183ff085",  # selector checkIn()
        "GAS_LIMIT": 50000,
        "MIN_BNB_GAS": 0.00005,  # Ngưỡng BNB tối thiểu để thực hiện giao dịch (chỉ cần > 0.00005 BNB là đủ chạy)

        # Bật/Tắt tính năng
        "AUTO_TASKS": True,
        "AUTO_ONCHAIN_CHECKIN": True,

        # Danh sách RPC BSC Mainnet uy tín
        "BSC_RPC_URLS": [
            "https://bsc-dataseed.binance.org/",
            "https://bsc-dataseed1.defibit.io/",
            "https://bsc-dataseed1.ninicoin.io/",
            "https://bsc-dataseed2.binance.org/",
            "https://56.rpc.thirdweb.com/",
        ],

        # Privy App ID của DI.XYZ
        "PRIVY_APP_ID": "cmsdjnd0n00by0djvu64acvd1",

        # Khung giờ chạy ngẫu nhiên hàng ngày theo giờ Việt Nam (UTC+7)
        # Check-in DI.XYZ reset vào 00:00 UTC (tức 07:00 sáng VN)
        "SCHEDULE_HOUR_START": 7,  # Bắt đầu từ 7h00 sáng
        "SCHEDULE_HOUR_END": 8,    # Kết thúc trước 8h00 sáng
    }


CONFIG = get_config()
VN_TZ = timezone(timedelta(hours=7))


# ==================== KÍCH HOẠT ANSI & LOG ====================
def init_console():
    if sys.platform == "win32":
        try:
            os.system("")
        except Exception:
            pass
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass
        try:
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)
            mode = ctypes.c_ulong()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                if kernel32.SetConsoleMode(handle, mode.value | 0x0004):
                    return True
        except Exception:
            pass
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


ANSI_ENABLED = init_console()


def clean_ansi(text: str) -> str:
    if not ANSI_ENABLED:
        return re.sub(r"(\033|\x1b)\[[0-9;]*[a-zA-Z]", "", text)
    return text


class Colors:
    RESET = "\033[0m" if ANSI_ENABLED else ""
    BOLD = "\033[1m" if ANSI_ENABLED else ""
    DIM = "\033[2m" if ANSI_ENABLED else ""
    RED = "\033[91m" if ANSI_ENABLED else ""
    GREEN = "\033[92m" if ANSI_ENABLED else ""
    YELLOW = "\033[93m" if ANSI_ENABLED else ""
    BLUE = "\033[94m" if ANSI_ENABLED else ""
    MAGENTA = "\033[95m" if ANSI_ENABLED else ""
    CYAN = "\033[96m" if ANSI_ENABLED else ""
    WHITE = "\033[97m" if ANSI_ENABLED else ""


print_lock = threading.Lock()
file_lock = threading.Lock()


def log(acc_idx, msg: str, color=Colors.RESET):
    now = time.strftime("%H:%M:%S")
    tag = f"[Acc {acc_idx}]" if acc_idx is not None else "[DI.XYZ]"
    if ANSI_ENABLED:
        formatted = f"{Colors.DIM}[{now}]{Colors.RESET} {Colors.CYAN}{tag:<10}{Colors.RESET} {color}{msg}{Colors.RESET}"
    else:
        formatted = f"[{now}] {tag:<10} {clean_ansi(msg)}"
    with print_lock:
        print(formatted, flush=True)


def reset_log_file(cycle: int):
    with file_lock:
        try:
            with open(CONFIG["LOG_FILE"], "w", encoding="utf-8") as f:
                f.write(f"# ROUND #{cycle} - Bắt đầu: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("# Ví | Số ngày Check-in | Điểm (Points) | Whitelist Status | Ghi chú\n")
        except Exception:
            pass


def append_log_file(wallet: str, days_str: str, points: int, wl_status: str, note: str):
    line = f"{wallet} | {days_str} | {points} PTS | {wl_status} | {note}\n"
    with file_lock:
        try:
            with open(CONFIG["LOG_FILE"], "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass


# ==================== PARSER ====================
def parse_proxy(raw: str):
    raw = raw.strip()
    if not raw:
        return None
    if "://" in raw:
        protocol, rest = raw.split("://", 1)
    else:
        protocol = "http"
        rest = raw

    if "@" in rest:
        return f"{protocol}://{rest}"

    parts = rest.split(":")
    if len(parts) == 4:
        p1_is_port = parts[1].isdigit() and int(parts[1]) <= 65535
        p3_is_port = parts[3].isdigit() and int(parts[3]) <= 65535
        if p1_is_port and not p3_is_port:
            host, port, user, password = parts[0], parts[1], parts[2], parts[3]
        else:
            user, password, host, port = parts[0], parts[1], parts[2], parts[3]
        return f"{protocol}://{user}:{password}@{host}:{port}"
    elif len(parts) == 2:
        return f"{protocol}://{parts[0]}:{parts[1]}"
    return f"{protocol}://{rest}"


def load_accounts(filename=CONFIG["ACCOUNT_FILE"]):
    accounts = []
    if not os.path.exists(filename):
        return accounts
    try:
        with open(filename, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = re.split(r"\||----|:|,|\s+", line)
                pk_candidate = None
                expected_addr = None
                for p in parts:
                    clean = p.strip()
                    if clean.startswith("0x") and len(clean) == 66:
                        pk_candidate = clean
                    elif not clean.startswith("0x") and len(clean) == 64:
                        pk_candidate = "0x" + clean
                    elif clean.startswith("0x") and len(clean) == 42:
                        expected_addr = clean

                if not pk_candidate and len(parts[-1].strip()) in (64, 66):
                    last = parts[-1].strip()
                    pk_candidate = last if last.startswith("0x") else "0x" + last

                if pk_candidate:
                    if not expected_addr:
                        try:
                            expected_addr = Account.from_key(pk_candidate).address
                        except Exception:
                            continue
                    accounts.append({"address": expected_addr, "private_key": pk_candidate})
    except Exception as e:
        log(None, f"Lỗi đọc {filename}: {e}", Colors.RED)
    return accounts


def load_proxies(filename=CONFIG["PROXY_FILE"]):
    proxies = []
    if not os.path.exists(filename):
        return proxies
    try:
        with open(filename, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    proxies.append(line)
    except Exception as e:
        log(None, f"Lỗi đọc {filename}: {e}", Colors.RED)
    return proxies


# ==================== BSC JSON-RPC ====================
class BscRpc:
    @staticmethod
    def call(method: str, params: list, proxies: list = None, retries: int = 4):
        payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
        for attempt in range(retries):
            rpc_url = CONFIG["BSC_RPC_URLS"][attempt % len(CONFIG["BSC_RPC_URLS"])]
            proxy_dict = None
            if proxies:
                p_url = parse_proxy(random.choice(proxies))
                if p_url:
                    proxy_dict = {"http": p_url, "https": p_url}
            try:
                resp = requests.post(rpc_url, json=payload, timeout=12, proxies=proxy_dict)
                if resp.status_code == 200:
                    data = resp.json()
                    if "error" not in data:
                        return data.get("result")
            except Exception:
                pass

        # Fallback direct
        for rpc_url in CONFIG["BSC_RPC_URLS"]:
            try:
                resp = requests.post(rpc_url, json=payload, timeout=12)
                if resp.status_code == 200:
                    data = resp.json()
                    if "error" not in data:
                        return data.get("result")
            except Exception:
                pass
        return None

    @staticmethod
    def get_balance(address: str, proxies: list = None) -> float:
        res = BscRpc.call("eth_getBalance", [address, "latest"], proxies)
        if not res:
            return 0.0
        try:
            return int(res, 16) / 10**18
        except Exception:
            return 0.0

    @staticmethod
    def get_nonce(address: str, proxies: list = None) -> int:
        res = BscRpc.call("eth_getTransactionCount", [address, "pending"], proxies)
        return int(res, 16) if res else 0

    @staticmethod
    def get_gas_price(proxies: list = None) -> int:
        res = BscRpc.call("eth_gasPrice", [], proxies)
        if res:
            return max(int(res, 16), 100000000)  # Min 0.1 Gwei on BSC (tương đương ~0.0000065 BNB / tx)
        return 500000000  # Fallback 0.5 Gwei

    @staticmethod
    def send_raw_transaction(raw_tx_hex: str, proxies: list = None) -> str:
        if not raw_tx_hex.startswith("0x"):
            raw_tx_hex = "0x" + raw_tx_hex
        res = BscRpc.call("eth_sendRawTransaction", [raw_tx_hex], proxies)
        return res

    @staticmethod
    def wait_for_receipt(tx_hash: str, timeout: int = 40, proxies: list = None) -> dict:
        start_time = time.time()
        while time.time() - start_time < timeout:
            res = BscRpc.call("eth_getTransactionReceipt", [tx_hash], proxies)
            if res and isinstance(res, dict) and res.get("blockNumber"):
                return res
            time.sleep(2.5)
        return None


# ==================== CLIENT DI.XYZ ====================
class DIClient:
    BASE_URL = "https://di.xyz/api"
    PRIVY_AUTH_URL = "https://auth.privy.io/api/v1"

    def __init__(self, acc_idx: int, private_key: str, proxies: list):
        self.acc_idx = acc_idx
        if not private_key.startswith("0x"):
            private_key = "0x" + private_key
        self.private_key = private_key
        self.account = Account.from_key(private_key)
        self.wallet_address = self.account.address
        self.short_wallet = f"{self.wallet_address[:6]}...{self.wallet_address[-4:]}"

        self.raw_proxies = proxies or []
        self.proxy_index = (acc_idx - 1) % len(self.raw_proxies) if self.raw_proxies else 0
        self.token = None
        self.session = requests.Session()
        self.user_data = {}
        self.engagement_data = {}
        self.set_proxy()

    def set_proxy(self):
        if not self.raw_proxies:
            return
        p_raw = self.raw_proxies[self.proxy_index % len(self.raw_proxies)]
        parsed = parse_proxy(p_raw)
        if parsed:
            self.session.proxies.clear()
            self.session.proxies.update({"http": parsed, "https": parsed})

    def rotate_proxy(self):
        if len(self.raw_proxies) > 1:
            self.proxy_index = (self.proxy_index + 1) % len(self.raw_proxies)
            self.set_proxy()

    def request(self, method: str, url: str, json_data: dict = None, headers: dict = None, retries: int = 3):
        h = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Origin": "https://di.xyz",
            "Referer": "https://di.xyz/check-in",
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
        }
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        if headers:
            h.update(headers)

        for _ in range(retries):
            try:
                resp = self.session.request(method, url, json=json_data, headers=h, timeout=15)
                if resp.status_code in (403, 429, 502, 503, 504):
                    self.rotate_proxy()
                    time.sleep(1.5)
                    continue
                return resp
            except Exception:
                self.rotate_proxy()
                time.sleep(1.5)
        return None

    # ---------- 1. AUTHENTICATION (PRIVY SIWE) ----------
    def login(self) -> bool:
        """Đăng nhập SIWE qua Privy SDK chuẩn của DI.XYZ"""
        privy_headers = {
            "privy-app-id": CONFIG["PRIVY_APP_ID"],
            "privy-client": "react-auth:1.98.0",
            "Origin": "https://di.xyz",
            "Referer": "https://di.xyz/",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        # Step 1: Lấy SIWE Nonce
        r_init = self.request(
            "POST",
            f"{self.PRIVY_AUTH_URL}/siwe/init",
            json_data={"address": self.wallet_address},
            headers=privy_headers,
        )
        if not r_init or r_init.status_code != 200:
            log(self.acc_idx, "Lỗi kết nối Privy SIWE Init", Colors.RED)
            return False

        nonce = r_init.json().get("nonce")
        if not nonce:
            log(self.acc_idx, "Không tìm thấy Nonce từ Privy", Colors.RED)
            return False

        # Step 2: Tạo và ký SIWE Message
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        message = (
            f"di.xyz wants you to sign in with your Ethereum account:\n"
            f"{self.wallet_address}\n\n"
            f"By signing, you are proving you own this wallet and logging in. This does not initiate a transaction or cost any fees.\n\n"
            f"URI: https://di.xyz\n"
            f"Version: 1\n"
            f"Chain ID: 56\n"
            f"Nonce: {nonce}\n"
            f"Issued At: {now_iso}\n"
            f"Resources:\n"
            f"- https://privy.io"
        )
        signable = encode_defunct(text=message)
        signed = self.account.sign_message(signable)
        sig_hex = signed.signature.hex()
        if not sig_hex.startswith("0x"):
            sig_hex = "0x" + sig_hex

        # Step 3: Xác thực với Privy SIWE
        auth_payload = {
            "message": message,
            "signature": sig_hex,
            "chainId": "eip155:56",
            "walletClientType": "metamask",
            "connectorType": "injected",
            "mode": "login-or-sign-up",
        }
        r_auth = self.request(
            "POST",
            f"{self.PRIVY_AUTH_URL}/siwe/authenticate",
            json_data=auth_payload,
            headers=privy_headers,
        )
        if not r_auth or r_auth.status_code != 200:
            log(self.acc_idx, "Xác thực Privy SIWE thất bại", Colors.RED)
            return False

        auth_data = r_auth.json()
        self.token = auth_data.get("token")
        self.user_data = auth_data.get("user") or {}

        # Step 4: Đồng bộ danh tính vào DI.XYZ backend
        r_sync = self.request("POST", f"{self.BASE_URL}/identity/sync")
        if not r_sync or r_sync.status_code != 200:
            log(self.acc_idx, "Lỗi đồng bộ danh tính /api/identity/sync", Colors.RED)
            return False

        # Step 5: Đọc trạng thái engagement
        self.refresh_engagement()
        points = self.engagement_data.get("points_balance", 0)
        wl_info = self.engagement_data.get("whitelist") or {}
        days = wl_info.get("active_day_count", 0)

        log(
            self.acc_idx,
            f"Login ({self.short_wallet}) | {Colors.GREEN}{points} PTS{Colors.RESET} | Check-in: {Colors.CYAN}{days}/30 ngày{Colors.RESET}",
        )
        return True

    def refresh_engagement(self):
        r_me = self.request("GET", f"{self.BASE_URL}/engagement/me")
        if r_me and r_me.status_code == 200:
            data = r_me.json()
            self.engagement_data = data.get("engagement") or {}
        return self.engagement_data

    # ---------- 2. AUTO TASKS (OFF-CHAIN) ----------
    def run_tasks(self):
        """Tự động làm toàn bộ Task MXH có thể nhận điểm"""
        if not CONFIG.get("AUTO_TASKS", True):
            return

        eng = self.refresh_engagement()
        completed_task_keys = set()
        for t in eng.get("tasks") or []:
            if t.get("status") == "completed":
                completed_task_keys.add(t.get("task_key"))

        # 1. Task Telegram Join (+100 PTS)
        if "telegram_join" not in completed_task_keys:
            r_start = self.request("POST", f"{self.BASE_URL}/tasks/verification/start", json_data={"taskKey": "telegram_join"})
            if r_start and r_start.status_code == 200:
                log(self.acc_idx, "Task: Join Telegram -> Đang đếm ngược 10s...", Colors.YELLOW)
                time.sleep(10.5)
                r_comp = self.request("POST", f"{self.BASE_URL}/tasks/verification/complete", json_data={"taskKey": "telegram_join"})
                if r_comp and r_comp.status_code == 200:
                    log(self.acc_idx, f"Task: Join Telegram -> {Colors.GREEN}+100 PTS{Colors.RESET}")
                    completed_task_keys.add("telegram_join")

        # 2. Task Daily Telegram Community Message (+50 PTS)
        if "daily_telegram_message" not in completed_task_keys:
            r_start = self.request("POST", f"{self.BASE_URL}/tasks/verification/start", json_data={"taskKey": "daily_telegram_message"})
            if r_start and r_start.status_code == 200:
                log(self.acc_idx, "Task: Daily Telegram Message -> Đang đếm ngược 5s...", Colors.YELLOW)
                time.sleep(5.5)
                r_comp = self.request("POST", f"{self.BASE_URL}/tasks/verification/complete", json_data={"taskKey": "daily_telegram_message"})
                if r_comp and r_comp.status_code == 200:
                    log(self.acc_idx, f"Task: Daily Telegram Message -> {Colors.GREEN}+50 PTS{Colors.RESET}")

        # 3. Các task X (nếu ví có linked X)
        linked_accounts = self.user_data.get("linked_accounts") or []
        has_twitter = any(a.get("type") in ("twitter", "twitter_oauth") for a in linked_accounts)
        if has_twitter:
            # Task Follow DI on X
            if "x_follow" not in completed_task_keys:
                r_start = self.request("POST", f"{self.BASE_URL}/tasks/verification/start", json_data={"taskKey": "x_follow"})
                if r_start and r_start.status_code == 200:
                    time.sleep(5.5)
                    r_comp = self.request("POST", f"{self.BASE_URL}/tasks/verification/complete", json_data={"taskKey": "x_follow"})
                    if r_comp and r_comp.status_code == 200:
                        log(self.acc_idx, f"Task: Follow DI on X -> {Colors.GREEN}+100 PTS{Colors.RESET}")

            # Các task hàng ngày (Like, Repost, Reply)
            daily_content = eng.get("daily_x_content") or {}
            rev_id = daily_content.get("content_revision_id")
            for t_key, t_name in [("daily_like", "Daily Like X"), ("daily_repost", "Daily Repost X"), ("daily_reply", "Daily Reply X")]:
                if t_key not in completed_task_keys:
                    p_load = {"taskKey": t_key}
                    if rev_id:
                        p_load["contentRevisionId"] = rev_id
                    r_start = self.request("POST", f"{self.BASE_URL}/tasks/verification/start", json_data=p_load)
                    if r_start and r_start.status_code == 200:
                        time.sleep(5.5)
                        r_comp = self.request("POST", f"{self.BASE_URL}/tasks/verification/complete", json_data=p_load)
                        if r_comp and r_comp.status_code == 200:
                            log(self.acc_idx, f"Task: {t_name} -> {Colors.GREEN}+50 PTS{Colors.RESET}")

    # ---------- 3. ON-CHAIN CHECK-IN (BSC MAINNET) ----------
    def run_checkin(self) -> str:
        """Gửi giao dịch On-Chain check-in trên mạng BSC Mainnet"""
        if not CONFIG.get("AUTO_ONCHAIN_CHECKIN", True):
            return "Skipped"

        # Kiểm tra số dư gas BNB trên BSC
        bnb_bal = BscRpc.get_balance(self.wallet_address, self.raw_proxies)
        min_gas = CONFIG["MIN_BNB_GAS"]
        if bnb_bal < min_gas:
            log(
                self.acc_idx,
                f"Thiếu gas BNB ({Colors.RED}{bnb_bal:.6f} BNB{Colors.RESET} < {min_gas}). Chạy file {Colors.YELLOW}withdraw.py{Colors.RESET} để nạp thêm!",
                Colors.YELLOW,
            )
            return f"Thiếu Gas ({bnb_bal:.5f} BNB)"

        # Step 1: Tạo Check-in Attempt trên Backend
        r_att = self.request(
            "POST",
            f"{self.BASE_URL}/check-in/attempts",
            json_data={"chainId": CONFIG["CHAIN_ID"], "walletAddress": self.wallet_address},
        )
        if not r_att or r_att.status_code not in (200, 201):
            err_msg = r_att.json().get("code") if r_att and r_att.text else "UNKNOWN_ERROR"
            if err_msg == "CHECKIN_TODAY_ALREADY_SUCCEEDED":
                log(self.acc_idx, "Hôm nay đã Check-in On-Chain rồi (Đạt chỉ tiêu ngày)", Colors.DIM)
                return "Đã Check-in hôm nay"
            log(self.acc_idx, f"Tạo Check-in attempt thất bại: {err_msg}", Colors.RED)
            return f"Lỗi attempt: {err_msg}"

        attempt_info = r_att.json().get("attempt") or {}
        attempt_id = attempt_info.get("id")
        if not attempt_id:
            log(self.acc_idx, "Không nhận được Attempt ID từ Backend", Colors.RED)
            return "Lỗi attempt ID"

        # Step 2: Chuẩn bị thông số giao dịch On-Chain trên BSC
        nonce = BscRpc.get_nonce(self.wallet_address, self.raw_proxies)
        gas_price = BscRpc.get_gas_price(self.raw_proxies)

        tx_params = {
            "nonce": nonce,
            "gasPrice": gas_price,
            "gas": CONFIG["GAS_LIMIT"],
            "to": CONFIG["CHECKIN_CONTRACT"],
            "value": 0,
            "data": CONFIG["CHECKIN_DATA"],
            "chainId": CONFIG["CHAIN_ID"],
        }

        # Step 3: Ký raw transaction bằng private key
        try:
            signed_tx = self.account.sign_transaction(tx_params)
            raw_tx_hex = signed_tx.raw_transaction.hex()
        except Exception as e:
            log(self.acc_idx, f"Lỗi ký transaction: {e}", Colors.RED)
            return "Lỗi ký Tx"

        # Step 4: Broadcast Transaction lên mạng BSC
        log(self.acc_idx, f"Đang gửi Tx Check-in On-Chain (GasPrice: {gas_price / 10**9:.2f} Gwei)...", Colors.CYAN)
        tx_hash = BscRpc.send_raw_transaction(raw_tx_hex, self.raw_proxies)
        if not tx_hash or not tx_hash.startswith("0x"):
            log(self.acc_idx, f"Lỗi broadcast transaction: {tx_hash}", Colors.RED)
            # Báo attempt failed để dọn dẹp state
            self.request("PATCH", f"{self.BASE_URL}/check-in/attempts", json_data={"action": "failed", "attemptId": attempt_id})
            return "Lỗi Broadcast Tx"

        short_tx = f"{tx_hash[:10]}...{tx_hash[-6:]}"
        log(self.acc_idx, f"Tx đã gửi lên BSC: {Colors.CYAN}{short_tx}{Colors.RESET}. Đang sync attempt...", Colors.CYAN)

        # Step 5: Báo cho backend rằng transaction đã được submit
        self.request(
            "PATCH",
            f"{self.BASE_URL}/check-in/attempts",
            json_data={"action": "submitted", "attemptId": attempt_id, "txHash": tx_hash},
        )

        # Step 6: Chờ xác nhận Block trên BSC
        receipt = BscRpc.wait_for_receipt(tx_hash, timeout=40, proxies=self.raw_proxies)
        if not receipt:
            log(self.acc_idx, f"Chờ xác nhận Tx quá hạn (Tx vẫn có thể khớp sau): {short_tx}", Colors.YELLOW)
            return "Tx Pending"

        status_int = int(receipt.get("status", 0), 16) if isinstance(receipt.get("status"), str) else receipt.get("status", 0)
        if status_int != 1:
            log(self.acc_idx, f"Giao dịch BSC bị Revert/Thất bại: {short_tx}", Colors.RED)
            self.request("PATCH", f"{self.BASE_URL}/check-in/attempts", json_data={"action": "failed", "attemptId": attempt_id})
            return "Tx Reverted"

        # Step 7: Xác nhận với Backend để nhận điểm
        r_conf = self.request(
            "POST",
            f"{self.BASE_URL}/check-in/confirm",
            json_data={"attemptId": attempt_id, "txHash": tx_hash},
        )
        if r_conf and r_conf.status_code == 200:
            cdata = r_conf.json().get("checkIn") or {}
            pts_awarded = cdata.get("points_awarded", 0)
            eng = self.refresh_engagement()
            wl_info = eng.get("whitelist") or {}
            days = wl_info.get("active_day_count", 0)
            log(
                self.acc_idx,
                f"Check-in On-Chain THÀNH CÔNG! {Colors.GREEN}+{pts_awarded} PTS{Colors.RESET} | Tích lũy: {Colors.GREEN}{days}/30 ngày{Colors.RESET}",
                Colors.GREEN,
            )
            return f"Thành công (+{pts_awarded} PTS, {days}/30d)"
        else:
            log(self.acc_idx, "Tx thành công nhưng lỗi Confirm Backend", Colors.YELLOW)
            return "Tx OK (Lỗi Confirm)"


# ==================== PROCESS SINGLE ACCOUNT ====================
def process_account(idx: int, acc: dict, proxies: list):
    client = DIClient(acc_idx=idx, private_key=acc["private_key"], proxies=proxies)

    if not client.login():
        append_log_file(client.wallet_address, "0/30", 0, "Chưa xác thực", "Lỗi Login SIWE")
        return

    # 1. Chạy các task MXH
    try:
        client.run_tasks()
    except Exception as e:
        log(idx, f"Lỗi làm tasks: {e}", Colors.RED)

    # 2. Chạy On-Chain Check-in
    checkin_status = "Bỏ qua"
    try:
        checkin_status = client.run_checkin()
    except Exception as e:
        log(idx, f"Lỗi check-in: {e}", Colors.RED)
        checkin_status = f"Lỗi: {e}"

    # 3. Ghi nhận kết quả
    eng = client.refresh_engagement()
    points = eng.get("points_balance", 0)
    wl_info = eng.get("whitelist") or {}
    days = wl_info.get("active_day_count", 0)
    wl_status = "Đủ chuẩn Mint" if days >= 30 else f"Đang tích lũy ({days}/30)"

    append_log_file(
        wallet=client.wallet_address,
        days_str=f"{days}/30",
        points=points,
        wl_status=wl_status,
        note=checkin_status,
    )


def sleep_until_next_run():
    """
    Tính toán thời gian nghỉ ngẫu nhiên vào khung 7h - 8h sáng hàng ngày theo giờ Việt Nam (UTC+7).
    (DI.XYZ reset ngày mới vào 00:00 UTC = 07:00 AM VN).
    """
    now_vn = datetime.now(VN_TZ)
    # Nếu trước 7h sáng -> mốc chạy tiếp theo là 7-8h sáng hôm nay
    # Nếu từ 7h sáng trở đi -> mốc chạy tiếp theo là 7-8h sáng ngày mai
    if now_vn.hour < CONFIG["SCHEDULE_HOUR_START"]:
        target_date = now_vn.date()
    else:
        target_date = now_vn.date() + timedelta(days=1)

    max_seconds = max(0, (CONFIG["SCHEDULE_HOUR_END"] - CONFIG["SCHEDULE_HOUR_START"]) * 3600)
    random_seconds = random.randint(0, max_seconds)
    target_dt = datetime(
        target_date.year,
        target_date.month,
        target_date.day,
        CONFIG["SCHEDULE_HOUR_START"],
        0,
        0,
        tzinfo=VN_TZ,
    ) + timedelta(seconds=random_seconds)

    # Đảm bảo target luôn ở tương lai
    if target_dt <= now_vn:
        target_date = target_date + timedelta(days=1)
        target_dt = datetime(
            target_date.year,
            target_date.month,
            target_date.day,
            CONFIG["SCHEDULE_HOUR_START"],
            0,
            0,
            tzinfo=VN_TZ,
        ) + timedelta(seconds=random_seconds)

    total_seconds = int((target_dt - now_vn).total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    target_str = target_dt.strftime("%d/%m/%Y %H:%M:%S")
    print(f"\n{Colors.CYAN}{Colors.BOLD}[HẸN GIỜ CHECK-IN]{Colors.RESET} Lần chạy tiếp theo: {Colors.GREEN}{target_str} (Giờ VN - UTC+7){Colors.RESET}")
    print(f"{Colors.CYAN}Đã hoàn thành toàn bộ ví. Nghỉ: {Colors.YELLOW}{hours} giờ {minutes} phút {seconds} giây{Colors.RESET}...\n")

    # Đếm ngược và cập nhật mỗi 30 phút (1800 giây)
    while total_seconds > 0:
        sleep_step = min(total_seconds, 1800)
        time.sleep(sleep_step)
        now_check = datetime.now(VN_TZ)
        remaining = int((target_dt - now_check).total_seconds())
        if remaining > 0:
            rem_h = remaining // 3600
            rem_m = (remaining % 3600) // 60
            print(f"[{now_check.strftime('%H:%M:%S')}] Đang chờ đến {target_str}... (còn khoảng {rem_h}h {rem_m}m)")
            total_seconds = remaining
        else:
            break


# ==================== MAIN RUNNER ====================
def main():
    print(f"\n{Colors.GREEN}{Colors.BOLD}=== DI.XYZ AUTO CHECK-IN & TASKS BOT | BSC MAINNET ==={Colors.RESET}\n")

    accounts = load_accounts(CONFIG["ACCOUNT_FILE"])
    proxies = load_proxies(CONFIG["PROXY_FILE"])

    if not accounts:
        log(None, f"Không tìm thấy tài khoản trong {CONFIG['ACCOUNT_FILE']}!", Colors.RED)
        return

    threads = max(1, min(CONFIG["THREADS"], len(accounts)))
    log(None, f"Đã nạp {len(accounts)} ví | {len(proxies)} proxies | Chạy đa luồng: {threads} threads", Colors.GREEN)

    cycle = 1
    while True:
        reset_log_file(cycle)
        print(f"\n{Colors.BOLD}--- BẮT ĐẦU CHU KỲ #{cycle} (Đã làm mới {CONFIG['LOG_FILE']}) ---{Colors.RESET}\n")

        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = {
                executor.submit(process_account, idx, acc, proxies): idx
                for idx, acc in enumerate(accounts, 1)
            }
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    acc_idx = futures[future]
                    log(acc_idx, f"Lỗi luồng: {e}", Colors.RED)

        cycle += 1
        sleep_until_next_run()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Đã dừng bot.{Colors.RESET}")
