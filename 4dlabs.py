import os
import sys
import time
import json
import random
import threading
import hmac
import hashlib
import urllib.parse
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from eth_account import Account
from eth_account.messages import encode_defunct
import eth_abi
import eth_utils


# ==================== CẤU HÌNH BOT 4DLABS (CHỈNH SỬA TẠI ĐÂY) ====================
def get_config():
    return {
        "THREADS": 10,                        # Số luồng chạy song song (1 = chạy tuần tự, 10-20 = đa luồng)
        "SEASON_PHASE": "S1",                 # Mùa hiện tại (Season 1: Prelude)
        "INVITATION_CODE": "",                # Mã giới thiệu (tùy chọn, để trống nếu không dùng)
        "AUTO_WITHDRAW_BINANCE": True,        # Tự động rút BNB từ sàn Binance vào các ví có balance = 0
        "BINANCE_KEY_FILE": "binance.txt",    # File chứa Binance API Key & Secret
        "BINANCE_WITHDRAW_MIN_PCT": 5,        # Tối thiểu ngẫu nhiên vượt mức min sàn (> min 5%)
        "BINANCE_WITHDRAW_MAX_PCT": 50,       # Tối đa ngẫu nhiên vượt mức min sàn (> min 50%)
        "BINANCE_WITHDRAW_DELAY_MIN": 20,     # Độ trễ ngẫu nhiên tối thiểu giữa các lệnh rút sàn (giây)
        "BINANCE_WITHDRAW_DELAY_MAX": 45,     # Độ trễ ngẫu nhiên tối đa giữa các lệnh rút sàn (giây)
        "AUTO_CHECKIN_ONCHAIN": True,         # Tự động gửi tx checkIn(location) trên mạng BSC Mainnet nếu ví có BNB
        "PREFERRED_CONTINENT": "RANDOM",      # Châu lục check-in: "RANDOM", "MOST_POPULAR", "LEAST_POPULAR" hoặc "ASN", "AFR", "NAM", "EUR", "OCE", "SAM"
        "MIN_BNB_FOR_CHECKIN": 0.00003,       # Số dư BNB tối thiểu trên BSC để thực hiện giao dịch check-in
        "MAX_GAS_PRICE_GWEI": 3.0,            # Giới hạn Gas Price tối đa (Gwei) khi check-in trên BSC Mainnet
        "WALLET_DELAY_MIN_SECONDS": 55,       # Giãn cách ngẫu nhiên tối thiểu giữa các ví (giây)
        "WALLET_DELAY_MAX_SECONDS": 95,       # Giãn cách ngẫu nhiên tối đa giữa các ví (giây)
        "RANDOM_DAILY_SCHEDULE_UTC7": True,   # Tự động lập lịch giờ check-in ngẫu nhiên mỗi ngày (UTC+7)
        "SCHEDULE_HOUR_START_UTC7": 7,        # Khung giờ bắt đầu check-in ngẫu nhiên (7h sáng UTC+7)
        "SCHEDULE_HOUR_END_UTC7": 22,         # Khung giờ kết thúc check-in ngẫu nhiên (22h tối UTC+7)
        "AUTO_VERIFY_SOCIAL": True,           # Tự động verify X Follow/Retweet, Discord, Telegram (nếu ví đã bind OAuth)
        "ROUND_DELAY_MIN_MINUTES": 720,       # Thời gian nghỉ tối thiểu giữa mỗi chu kỳ nếu tắt lịch UTC+7 (12 tiếng)
        "ROUND_DELAY_MAX_MINUTES": 1440,      # Thời gian nghỉ tối đa giữa mỗi chu kỳ nếu tắt lịch UTC+7 (24 tiếng)
    }


CONFIG = get_config()


# ==================== HẰNG SỐ MẠNG (NETWORK), TIỀN TỐ (PREFIXES) & CONTRACT ====================
class NetworkConfig:
    """Thông số mạng BNB Smart Chain (BSC Mainnet) & Smart Contract của 4Dlabs"""
    NETWORK_NAME = "BNB Smart Chain Mainnet"
    CHAIN_KEY = "bscMainnet"
    CHAIN_ID = 56
    CAIP2_CHAIN_ID = "eip155:56"
    NATIVE_SYMBOL = "BNB"
    NATIVE_DECIMALS = 18
    EXPLORER_URL = "https://bscscan.com"
    EXPLORER_API_URL = "https://api.bscscan.com/api"

    # Danh sách RPC BSC Mainnet (tự động xoay vòng nếu RPC bị nghẽn)
    BSC_RPC_URLS = [
        "https://bsc-dataseed.binance.org/",
        "https://bsc-dataseed1.defibit.io/",
        "https://bsc-dataseed1.ninicoin.io/",
        "https://bsc-dataseed2.binance.org/",
        "https://56.rpc.thirdweb.com/",
    ]

    # Smart Contract Check-in mặc định của 4Dlabs trên BSC Mainnet
    DEFAULT_CHECKIN_CONTRACT = "0x654612a216517bdbbA8356Ff9462944AC5165fDc"

    # Function Selectors (4-byte Keccak-256)
    # function checkIn(string _location) -> 0xf21bb4c5
    SELECTOR_CHECKIN = "0x" + eth_utils.keccak(text="checkIn(string)")[:4].hex()
    # function legal_location(string) view returns (bool) -> 0x43befb2a
    SELECTOR_LEGAL_LOCATION = "0x" + eth_utils.keccak(text="legal_location(string)")[:4].hex()
    # event CheckIn(address indexed user_addr, string checkIn_location)
    EVENT_CHECKIN_TOPIC = "0x" + eth_utils.keccak(text="CheckIn(address,string)").hex()


class AppPrefixes:
    """Toàn bộ tiền tố định danh, URL, Privy App ID & Endpoints của dự án 4Dlabs"""
    PROJECT_NAME = "4D Labs"
    SPONSOR_NAME = "YZi Labs"
    BASE_URL = "https://dapp.4dlabs.space"
    DOCS_REFERRAL_URL = "https://docs.4dlabs.space/task-hub/referral"

    # Cấu hình xác thực Privy SIWE
    AUTH_MODE = "privy"
    PRIVY_APP_ID = "cmrw7x5ja02n20bifmgb02yw0"
    PRIVY_AUTH_BASE = "https://auth.privy.io/api/v1"
    PRIVY_CLIENT_VERSION = "react-auth:2.4.1"
    SIWE_DOMAIN = "dapp.4dlabs.space"
    SIWE_URI = "https://dapp.4dlabs.space"
    SIWE_VERSION = "1"
    SIWE_RESOURCE = "https://privy.io"

    # Tiền tố lưu trữ phiên (Session / LocalStorage Prefixes trong dApp)
    STORAGE_ACTIVE_WALLET = "4dlabs:active-wallet"
    STORAGE_LOGIN_ACCOUNT = "4dlabs:login-account"
    STORAGE_REFERRAL_SESSION = "4dlabs:referral:v1"
    EVENT_SESSION_EXPIRED = "4dlabs:session-expired"

    # Tài khoản mạng xã hội chính thức của dự án
    OFFICIAL_X_ACCOUNT = "4Dlabs_Official"
    OFFICIAL_TELEGRAM = "official_4dlabs"
    OFFICIAL_DISCORD_URL = "https://discord.gg/pD9hSXbZHM"
    SPONSOR_X_ACCOUNT = "yzilabs"

    # Danh sách 6 địa điểm / châu lục Check-in chuẩn trong dApp
    CONTINENTS = ["AFR", "ASN", "EUR", "NAM", "OCE", "SAM"]
    LOCATIONS = [
        {"key": "pyramid", "continent": "AFR", "imageField": "afr_pic", "title": "Great Pyramid (Africa)"},
        {"key": "wall", "continent": "ASN", "imageField": "asn_pic", "title": "Great Wall (Asia)"},
        {"key": "eiffel", "continent": "EUR", "imageField": "eur_pic", "title": "Eiffel Tower (Europe)"},
        {"key": "liberty", "continent": "NAM", "imageField": "nam_pic", "title": "Statue of Liberty (North America)"},
        {"key": "opera", "continent": "OCE", "imageField": "oce_pic", "title": "Sydney Opera House (Oceania)"},
        {"key": "christ", "continent": "SAM", "imageField": "sam_pic", "title": "Christ the Redeemer (South America)"},
    ]

    # Loại giới thiệu (Invite Type)
    INVITE_TYPE_DIRECT = 1
    INVITE_TYPE_INDIRECT = 2

    # Các loại hóa đơn điểm (Bill Types trong Score History)
    BILL_TYPES = [
        "CheckIn",
        "CheckInBonus",
        "TwitterFollow",
        "TwitterRetweet",
        "DiscordJoin",
        "TelegramJoin",
        "ReferBonus",
    ]

    # Toàn bộ API Endpoints của Backend 4Dlabs
    ENDPOINTS = {
        "auth": {
            "privyAuth": "/api/auth/privy-auth",
            "syncLoginMethods": "/api/auth/login-methods/sync",
        },
        "task": {
            "config": "/api/task/task-config",
            "myCheckin": "/api/task/my-checkin",
            "myCheckinStatus": "/api/task/my-checkin-status",
            "myCheckinBySeason": "/api/task/my-checkin-by-season",
            "checkinStat": "/api/task/checkin-stat",
            "checkinStatBySeason": "/api/task/checkin-stat-by-season",
        },
        "rank": {
            "me": "/api/rank/me",
            "meBySeason": "/api/rank/me-by-season",
            "leaderboard": "/api/rank/leaderboard",
        },
        "profile": {
            "scoreHistoryLog": "/api/profile/score-history-log",
            "scoreHistoryLogBySeason": "/api/profile/score-history-log-by-season",
            "linkedAccounts": "/api/profile/linked-accounts",
            "socialState": "/api/profile/social-state",
        },
        "referral": {
            "code": "/api/referral/code",
            "inviteesCount": "/api/referral/invitees-count",
            "inviteesDetails": "/api/referral/invitees-details",
        },
        "twitter": {
            "requestToken": "/api/twitter/request-token",
            "followVerify": "/api/twitter/follow/verify",
            "retweetVerify": "/api/twitter/retweet/verify",
        },
        "discord": {
            "authorizeUrl": "/api/discord/authorize-url",
            "joinGuild": "/api/discord/join-guild",
        },
        "telegram": {
            "authorizeUrl": "/api/telegram/authorize-url",
            "subscribe": "/api/telegram/subscribe",
        },
        "utils": {
            "image": "/api/utils/image",
        },
    }


# ==================== MÀU SẮC CONSOLE & KHÓA LUỒNG ====================
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    RED = "\033[91m"
    MAGENTA = "\033[95m"


def init_console():
    """Kích hoạt hiển thị màu ANSI chuẩn trên Windows CMD / PowerShell & UTF-8"""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if os.name == "nt":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            mode = ctypes.c_ulong()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel32.SetConsoleMode(handle, mode.value | 0x0004)
        except Exception:
            pass


init_console()

print_lock = threading.Lock()
file_lock = threading.Lock()

LOG_FILE = "log_4dlabs.txt"


def log(acc_idx, msg, color=Colors.RESET):
    """Hàm in log ngắn gọn, an toàn đa luồng: [Giờ] [Acc X] Nội dung"""
    now = datetime.now().strftime("%H:%M:%S")
    prefix = f"[Acc {acc_idx:<3}]" if acc_idx is not None else "[SYSTEM ]"
    line = f"{Colors.DIM}[{now}]{Colors.RESET} {Colors.CYAN}{prefix}{Colors.RESET} {color}{msg}{Colors.RESET}"
    with print_lock:
        print(line, flush=True)


def reset_log_file(cycle: int, filename=LOG_FILE):
    """Xóa làm mới file log_4dlabs.txt ở đầu mỗi round"""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header = (
        f"# 4DLABS ROUND #{cycle} - Cập nhật lúc: {now_str}\n"
        f"# Ví | Mã Ref | Điểm (Checkin/Social/Ref) | Rank | Số Ref (Direct/Indirect) | Check-in Hôm nay\n"
    )
    with file_lock:
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(header)
        except Exception as e:
            log(None, f"Lỗi tạo file {filename}: {e}", Colors.RED)


def append_log_file(
    wallet: str,
    my_ref: str,
    score_str: str,
    rank_str: str,
    ref_count_str: str,
    checkin_str: str,
    filename=LOG_FILE,
):
    """Ghi kết quả thực tế của từng ví vào log_4dlabs.txt theo thời gian thực"""
    line = f"{wallet} | {my_ref} | {score_str} | {rank_str} | {ref_count_str} | {checkin_str}\n"
    with file_lock:
        try:
            with open(filename, "a", encoding="utf-8") as f:
                f.write(line)
                f.flush()
        except Exception as e:
            log(None, f"Lỗi ghi file {filename}: {e}", Colors.RED)


# ==================== PARSER PROXY & ACCOUNT ====================
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
            ip, port, user, pw = parts[0], parts[1], parts[2], parts[3]
            return f"{protocol}://{user}:{pw}@{ip}:{port}"
        elif p3_is_port and not p1_is_port:
            user, pw, ip, port = parts[0], parts[1], parts[2], parts[3]
            return f"{protocol}://{user}:{pw}@{ip}:{port}"
        else:
            ip, port, user, pw = parts[0], parts[1], parts[2], parts[3]
            return f"{protocol}://{user}:{pw}@{ip}:{port}"
    elif len(parts) == 2:
        return f"{protocol}://{parts[0]}:{parts[1]}"

    return f"{protocol}://{rest}"


def parse_account(line: str):
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    for sep in ["|", ",", "\t", " "]:
        if sep in line:
            parts = [p.strip() for p in line.split(sep) if p.strip()]
            for p in reversed(parts):
                clean_hex = p[2:] if p.startswith("0x") else p
                if len(clean_hex) == 64:
                    try:
                        int(clean_hex, 16)
                        pk = p if p.startswith("0x") else "0x" + p
                        acc = Account.from_key(pk)
                        return {"private_key": pk, "address": acc.address}
                    except ValueError:
                        pass

    clean_hex = line[2:] if line.startswith("0x") else line
    if len(clean_hex) == 64:
        pk = line if line.startswith("0x") else "0x" + line
        try:
            acc = Account.from_key(pk)
            return {"private_key": pk, "address": acc.address}
        except Exception:
            return {"private_key": pk}
    return None


def load_accounts(filename="account.txt"):
    accounts = []
    if not os.path.exists(filename):
        return accounts
    try:
        with open(filename, "r", encoding="utf-8") as f:
            for line in f:
                acc = parse_account(line)
                if acc:
                    accounts.append(acc)
    except Exception as e:
        log(None, f"Lỗi đọc {filename}: {e}", Colors.RED)
    return accounts


def load_proxies(filename="proxy.txt"):
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


# ==================== TỰ ĐỘNG CHUYỂN BNB VÀO VÍ CÓ BALANCE = 0 ====================
def bsc_rpc_call(method: str, params: list, proxies: list = None, retries: int = 4):
    """Gọi JSON-RPC trực tiếp tới BSC Mainnet (hỗ trợ xoay vòng RPC & proxy)"""
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    for attempt in range(retries):
        rpc_url = NetworkConfig.BSC_RPC_URLS[attempt % len(NetworkConfig.BSC_RPC_URLS)]
        try:
            proxy_dict = None
            if proxies:
                p_url = parse_proxy(random.choice(proxies))
                if p_url:
                    proxy_dict = {"http": p_url, "https": p_url}
            resp = requests.post(rpc_url, json=payload, timeout=12, proxies=proxy_dict)
            if resp.status_code == 200:
                data = resp.json()
                if "error" not in data:
                    return data.get("result")
        except Exception:
            pass

    # Fallback kết nối trực tiếp (không qua proxy) nếu các proxy đều lỗi
    for rpc_url in NetworkConfig.BSC_RPC_URLS:
        try:
            resp = requests.post(rpc_url, json=payload, timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                if "error" not in data:
                    return data.get("result")
        except Exception:
            pass
    return None


def get_wallet_bnb_balance(address: str, proxies: list = None) -> float:
    """Lấy số dư BNB của địa chỉ ví trên BSC Mainnet"""
    res = bsc_rpc_call("eth_getBalance", [address, "latest"], proxies)
    if not res:
        return 0.0
    try:
        return int(res, 16) / (10 ** NetworkConfig.NATIVE_DECIMALS)
    except Exception:
        return 0.0


# ==================== TỰ ĐỘNG RÚT BNB TỪ SÀN BINANCE VÀO VÍ CÓ BALANCE = 0 ====================
def load_binance_credentials(filename="binance.txt"):
    """Đọc API Key và Secret Key từ file binance.txt"""
    if not os.path.exists(filename):
        return None, None
    api_key, secret_key = "", ""
    try:
        with open(filename, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        for l in lines:
            if "api_key=" in l.lower():
                api_key = l.split("=", 1)[1].strip()
            elif "secret_key=" in l.lower() or "secret=" in l.lower():
                secret_key = l.split("=", 1)[1].strip()
            elif "|" in l:
                parts = l.split("|", 1)
                api_key, secret_key = parts[0].strip(), parts[1].strip()
        if not api_key and len(lines) >= 2:
            api_key = lines[0]
            secret_key = lines[1]
    except Exception as e:
        log(None, f"[Binance] Lỗi đọc {filename}: {e}", Colors.RED)
    return api_key, secret_key


def binance_sign(params: dict, secret: str) -> str:
    """Tạo chữ ký HMAC-SHA256 chuẩn cho Binance API"""
    query_string = urllib.parse.urlencode(params)
    return hmac.new(secret.encode("utf-8"), query_string.encode("utf-8"), hashlib.sha256).hexdigest()


def get_binance_bnb_info(api_key: str, secret_key: str) -> dict:
    """Lấy giá BNB/USDT hiện tại và thông số min rút mạng BSC từ Binance API"""
    info = {"min_withdraw": 0.005, "fee": 0.0001, "bnb_price": 700.0}

    # 1. Lấy giá BNB/USDT thị trường
    try:
        r_p = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=BNBUSDT", timeout=10)
        if r_p.status_code == 200:
            info["bnb_price"] = float(r_p.json().get("price", 700.0))
    except Exception:
        pass

    # 2. Lấy cấu hình rút tiền từ SAPI
    try:
        ts = int(time.time() * 1000)
        params = {"timestamp": ts}
        params["signature"] = binance_sign(params, secret_key)
        headers = {"X-MBX-APIKEY": api_key}
        r_c = requests.get(
            "https://api.binance.com/sapi/v1/capital/config/getall",
            headers=headers,
            params=params,
            timeout=12,
        )
        if r_c.status_code == 200:
            for item in r_c.json():
                if item.get("coin") == "BNB":
                    for net in item.get("networkList", []):
                        if net.get("network") == "BSC":
                            info["min_withdraw"] = float(net.get("withdrawMin", 0.005))
                            info["fee"] = float(net.get("withdrawFee", 0.0001))
                            break
                    break
    except Exception:
        pass

    return info


def execute_binance_withdraw(api_key: str, secret_key: str, address: str, amount: float, network: str = "BSC"):
    """Gửi yêu cầu rút coin qua endpoint SAPI /sapi/v1/capital/withdraw/apply"""
    url = "https://api.binance.com/sapi/v1/capital/withdraw/apply"
    ts = int(time.time() * 1000)
    params = {
        "coin": "BNB",
        "network": network,
        "address": address,
        "amount": f"{amount:.5f}",
        "timestamp": ts,
    }
    params["signature"] = binance_sign(params, secret_key)
    headers = {"X-MBX-APIKEY": api_key}
    try:
        resp = requests.post(url, headers=headers, params=params, timeout=15)
        if resp.status_code == 200:
            return True, resp.json().get("id")
        else:
            err_data = resp.json() if resp.text else {}
            msg = err_data.get("msg") or resp.text
            return False, msg
    except Exception as e:
        return False, str(e)


def withdraw_binance_to_zero_wallets(accounts: list, proxies: list = None):
    """
    Quét danh sách ví trong account.txt:
    Ví nào có số dư balance = 0 sẽ được tự động rút BNB trực tiếp từ sàn Binance
    với số lượng ngẫu nhiên > min rút của sàn (mặc định > min 5% - 50%).
    """
    if not CONFIG.get("AUTO_WITHDRAW_BINANCE", True):
        return

    key_file = CONFIG.get("BINANCE_KEY_FILE", "binance.txt")
    api_key, secret_key = load_binance_credentials(key_file)
    if not api_key or not secret_key:
        log(
            None,
            f"[Binance] Chưa điền API Key & Secret trong file {key_file}. Bỏ qua tự động rút từ sàn.",
            Colors.YELLOW,
        )
        return

    # 1. Quét tìm tất cả các ví trong account.txt có balance = 0
    zero_wallets = []
    log(None, f"[Binance] Đang kiểm tra số dư BNB của {len(accounts)} ví trong account.txt...", Colors.CYAN)
    for idx, acc_data in enumerate(accounts, 1):
        pk = acc_data.get("private_key")
        addr = acc_data.get("address")
        if not addr and pk:
            try:
                addr = Account.from_key(pk).address
                acc_data["address"] = addr
            except Exception:
                continue

        bal = get_wallet_bnb_balance(addr, proxies)
        if bal == 0.0:
            zero_wallets.append((idx, addr))

    if not zero_wallets:
        log(None, "[Binance] Tất cả các ví đều đã có số dư BNB (không có ví nào balance = 0).", Colors.GREEN)
        return

    # 2. Lấy thông số min rút và giá BNB
    bnb_info = get_binance_bnb_info(api_key, secret_key)
    min_w = bnb_info["min_withdraw"]
    price = bnb_info["bnb_price"]

    min_pct = float(CONFIG.get("BINANCE_WITHDRAW_MIN_PCT", 5)) / 100.0
    max_pct = float(CONFIG.get("BINANCE_WITHDRAW_MAX_PCT", 50)) / 100.0
    range_min = min_w * (1.0 + min_pct)
    range_max = min_w * (1.0 + max_pct)

    log(
        None,
        f"[Binance] Phát hiện {Colors.YELLOW}{len(zero_wallets)}/{len(accounts)}{Colors.RESET} ví có balance = 0! Min sàn: {min_w} BNB | Rút ngẫu nhiên: {range_min:.5f} - {range_max:.5f} BNB (~${range_min * price:.2f} - ${range_max * price:.2f})",
        Colors.YELLOW,
    )

    success_count = 0
    d_min = float(CONFIG.get("BINANCE_WITHDRAW_DELAY_MIN", 20))
    d_max = float(CONFIG.get("BINANCE_WITHDRAW_DELAY_MAX", 45))

    for acc_idx, dest_addr in zero_wallets:
        rand_amount = round(random.uniform(range_min, range_max), 5)
        usd_val = rand_amount * price
        log(
            acc_idx,
            f"[Binance] Đang gửi lệnh rút {Colors.GREEN}{rand_amount} BNB{Colors.RESET} (~${usd_val:.2f}) tới ví {dest_addr}...",
            Colors.CYAN,
        )

        ok, result = execute_binance_withdraw(api_key, secret_key, dest_addr, rand_amount, network="BSC")
        if ok:
            success_count += 1
            log(
                acc_idx,
                f"[Binance] Lệnh rút thành công! Withdraw ID: {result}",
                Colors.GREEN,
            )
        else:
            log(
                acc_idx,
                f"[Binance] Lỗi rút BNB tới {dest_addr[:10]}...: {result}",
                Colors.RED,
            )

        if acc_idx != zero_wallets[-1][0]:
            sleep_delay = round(random.uniform(min(d_min, d_max), max(d_min, d_max)), 1)
            log(None, f"[Binance] Chờ {sleep_delay}s trước khi gửi lệnh rút tiếp theo...", Colors.DIM)
            time.sleep(sleep_delay)

    log(
        None,
        f"[Binance] Hoàn tất rút BNB! Đã gửi thành công {success_count}/{len(zero_wallets)} lệnh rút từ Binance.",
        Colors.GREEN if success_count == len(zero_wallets) else Colors.YELLOW,
    )


# ==================== CLIENT CHÍNH CỦA DỰ ÁN 4DLABS ====================
class FourDLabsClient:
    """
    Client tích hợp đầy đủ toàn bộ chức năng của dApp 4Dlabs (https://dapp.4dlabs.space):
    1. Xác thực Privy SIWE (Sign-In With Ethereum) trên mạng BSC Mainnet (eip155:56).
    2. Đăng nhập & Đăng ký gắn mã giới thiệu (/api/auth/privy-auth) + Đồng bộ Login Methods.
    3. Kiểm tra cấu hình mùa giải & nhiệm vụ (/api/task/task-config).
    4. Giao dịch On-chain Check-in trên BSC Mainnet:
       - Kiểm tra legal_location(string) trên Smart Contract.
       - Đọc số dư BNB, ước tính gas, ký và phát tán giao dịch checkIn(string).
       - Đợi xác nhận Receipt và đồng bộ điểm Check-in trên Backend.
    5. Kiểm tra & Xác minh nhiệm vụ Social (X Follow, X Retweet, Discord Join, Telegram Subscribe).
    6. Truy vấn Rank, Điểm chi tiết từng hạng mục, Lịch sử cộng điểm & Thống kê Referral 2 tầng.
    """

    def __init__(self, acc_idx: int, private_key: str, proxies: list):
        self.acc_idx = acc_idx
        if not private_key.startswith("0x"):
            private_key = "0x" + private_key
        self.private_key = private_key
        self.account = Account.from_key(private_key)
        self.checksum_address = self.account.address
        self.wallet_address = self.checksum_address.lower()

        self.raw_proxies = proxies or []
        self.proxy_index = (acc_idx - 1) % len(self.raw_proxies) if self.raw_proxies else 0
        self.rpc_index = (acc_idx - 1) % len(NetworkConfig.BSC_RPC_URLS)

        self.privy_token = None
        self.privy_user_id = None
        self.backend_user_id = None
        self.invitation_code = None

        self.session = requests.Session()
        self.set_proxy()

    # -------------------- QUẢN LÝ PROXY & HTTP REQUEST --------------------
    def set_proxy(self):
        if not self.raw_proxies:
            return
        proxy_raw = self.raw_proxies[self.proxy_index % len(self.raw_proxies)]
        parsed = parse_proxy(proxy_raw)
        if parsed:
            self.session.proxies.clear()
            self.session.proxies.update({"http": parsed, "https": parsed})

    def rotate_proxy(self):
        if len(self.raw_proxies) > 1:
            self.proxy_index = (self.proxy_index + 1) % len(self.raw_proxies)
            self.set_proxy()

    def get_privy_headers(self) -> dict:
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": AppPrefixes.BASE_URL,
            "Referer": f"{AppPrefixes.BASE_URL}/",
            "privy-app-id": AppPrefixes.PRIVY_APP_ID,
            "privy-client": AppPrefixes.PRIVY_CLIENT_VERSION,
        }

    def get_api_headers(self, authenticated: bool = True, ref_code: str = None) -> dict:
        referer = f"{AppPrefixes.BASE_URL}/join/{ref_code}" if ref_code else f"{AppPrefixes.BASE_URL}/tasks"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Origin": AppPrefixes.BASE_URL,
            "Referer": referer,
        }
        if authenticated and self.privy_token:
            headers["Authorization"] = f"Bearer {self.privy_token}"
        return headers

    def http_request(
        self,
        method: str,
        url: str,
        headers: dict = None,
        params: dict = None,
        json_data: dict = None,
        retries: int = 4,
    ):
        for attempt in range(retries):
            try:
                req_headers = dict(headers or {})
                if json_data is not None and "Content-Type" not in req_headers:
                    req_headers["Content-Type"] = "application/json"
                resp = self.session.request(
                    method=method,
                    url=url,
                    headers=req_headers,
                    params=params,
                    json=json_data,
                    timeout=25,
                )
                return resp
            except (
                requests.exceptions.ProxyError,
                requests.exceptions.Timeout,
                requests.exceptions.ConnectionError,
            ):
                self.rotate_proxy()
                time.sleep(0.8)
            except Exception as e:
                if attempt == retries - 1:
                    log(self.acc_idx, f"Lỗi kết nối {url}: {e}", Colors.RED)
                time.sleep(0.8)
        return None

    def api_request(
        self,
        method: str,
        endpoint: str,
        params: dict = None,
        json_data: dict = None,
        authenticated: bool = True,
        ref_code: str = None,
    ):
        url = f"{AppPrefixes.BASE_URL}{endpoint}"
        headers = self.get_api_headers(authenticated=authenticated, ref_code=ref_code)
        resp = self.http_request(method, url, headers=headers, params=params, json_data=json_data)
        if resp and resp.status_code == 401 and authenticated and endpoint != AppPrefixes.ENDPOINTS["auth"]["privyAuth"]:
            if self.login(silent=True):
                headers = self.get_api_headers(authenticated=authenticated, ref_code=ref_code)
                resp = self.http_request(method, url, headers=headers, params=params, json_data=json_data)
        return resp

    # -------------------- 1. XÁC THỰC PRIVY SIWE & ĐĂNG NHẬP BACKEND --------------------
    def siwe_init(self) -> str:
        """Bước 1: Lấy mã nonce SIWE từ Privy (POST /api/v1/siwe/init)"""
        url = f"{AppPrefixes.PRIVY_AUTH_BASE}/siwe/init"
        resp = self.http_request(
            "POST",
            url,
            headers=self.get_privy_headers(),
            json_data={"address": self.checksum_address},
        )
        if not resp or resp.status_code != 200:
            return None
        return resp.json().get("nonce")

    def build_siwe_message(self, nonce: str) -> str:
        """Bước 2: Tạo thông điệp chuẩn EIP-4361 (SIWE) cho mạng BSC Mainnet (Chain ID 56)"""
        issued_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        return (
            f"{AppPrefixes.SIWE_DOMAIN} wants you to sign in with your Ethereum account:\n"
            f"{self.checksum_address}\n\n"
            f"By signing, you are proving you own this wallet and logging in. This does not initiate a transaction or cost any fees.\n\n"
            f"URI: {AppPrefixes.SIWE_URI}\n"
            f"Version: {AppPrefixes.SIWE_VERSION}\n"
            f"Chain ID: {NetworkConfig.CHAIN_ID}\n"
            f"Nonce: {nonce}\n"
            f"Issued At: {issued_at}\n"
            f"Resources:\n"
            f"- {AppPrefixes.SIWE_RESOURCE}"
        )

    def siwe_authenticate(self, message: str, signature: str) -> dict:
        """Bước 3: Xác thực chữ ký SIWE với Privy để lấy Bearer JWT Token"""
        url = f"{AppPrefixes.PRIVY_AUTH_BASE}/siwe/authenticate"
        payload = {
            "message": message,
            "signature": signature,
            "chainId": NetworkConfig.CAIP2_CHAIN_ID,
            "walletClientType": "metamask",
            "connectorType": "injected",
            "mode": "login-or-sign-up",
        }
        resp = self.http_request("POST", url, headers=self.get_privy_headers(), json_data=payload)
        if not resp or resp.status_code != 200:
            return None
        return resp.json()

    def backend_privy_auth(self, invitation_code: str = None) -> dict:
        """Bước 4: Đăng nhập vào Backend 4Dlabs (/api/auth/privy-auth) kèm mã ref"""
        payload = {"privy_user_token": self.privy_token}
        if invitation_code:
            payload["invitation_code"] = invitation_code

        resp = self.api_request(
            "POST",
            AppPrefixes.ENDPOINTS["auth"]["privyAuth"],
            json_data=payload,
            authenticated=False,
            ref_code=invitation_code,
        )
        if not resp or resp.status_code != 200:
            return None
        return resp.json()

    def sync_login_methods(self) -> dict:
        """Bước 5: Đồng bộ phương thức đăng nhập (/api/auth/login-methods/sync)"""
        resp = self.api_request("POST", AppPrefixes.ENDPOINTS["auth"]["syncLoginMethods"])
        if resp and resp.status_code == 200:
            return resp.json()
        return None

    def login(self, ref_code: str = None, silent: bool = False) -> bool:
        """Thực hiện toàn bộ chu trình đăng nhập Privy SIWE + Backend 4Dlabs"""
        nonce = self.siwe_init()
        if not nonce:
            log(self.acc_idx, "Lỗi lấy nonce SIWE từ Privy", Colors.RED)
            return False

        siwe_msg = self.build_siwe_message(nonce)
        signed = Account.sign_message(encode_defunct(text=siwe_msg), self.private_key)
        signature = signed.signature.hex()
        if not signature.startswith("0x"):
            signature = "0x" + signature

        privy_data = self.siwe_authenticate(siwe_msg, signature)
        if not privy_data or not privy_data.get("token"):
            log(self.acc_idx, "Lỗi xác thực chữ ký SIWE trên Privy", Colors.RED)
            return False

        self.privy_token = privy_data["token"]
        self.privy_user_id = (privy_data.get("user") or {}).get("id")

        if ref_code is None:
            ref_code = CONFIG.get("INVITATION_CODE", "").strip() or None

        auth_res = self.backend_privy_auth(invitation_code=ref_code)
        if not auth_res:
            log(self.acc_idx, "Lỗi xác thực /api/auth/privy-auth trên 4Dlabs", Colors.RED)
            return False

        self.backend_user_id = auth_res.get("user_id")
        self.invitation_code = auth_res.get("invitation_code")

        # Đồng bộ login methods giống hệt trình duyệt
        self.sync_login_methods()

        if not silent:
            short_w = f"{self.checksum_address[:6]}..{self.checksum_address[-4:]}"
            ref_info = f" | Gắn Ref: {ref_code}" if ref_code else ""
            log(
                self.acc_idx,
                f"Login ({short_w}) | Ref Code: {Colors.GREEN}{self.invitation_code}{Colors.RESET}{ref_info}",
            )
        return True

    # -------------------- 2. TRUY VẤN TASK CONFIG, CHECK-IN, RANK & REFERRAL --------------------
    def get_task_config(self) -> dict:
        """Lấy cấu hình mùa giải, điểm thưởng và địa chỉ contract check-in (/api/task/task-config)"""
        resp = self.api_request("GET", AppPrefixes.ENDPOINTS["task"]["config"], authenticated=False)
        return resp.json() if resp and resp.status_code == 200 else {}

    def get_my_checkin_status(self) -> dict:
        """Kiểm tra hôm nay đã check-in chưa (/api/task/my-checkin-status)"""
        resp = self.api_request("GET", AppPrefixes.ENDPOINTS["task"]["myCheckinStatus"])
        return resp.json() if resp and resp.status_code == 200 else {}

    def get_my_checkin(self, season_phase: str = None) -> dict:
        """Lấy tổng số ngày check-in, chuỗi ngày liên tiếp & tổng điểm check-in"""
        if season_phase:
            resp = self.api_request(
                "GET",
                AppPrefixes.ENDPOINTS["task"]["myCheckinBySeason"],
                params={"season_phase": season_phase},
            )
        else:
            resp = self.api_request("GET", AppPrefixes.ENDPOINTS["task"]["myCheckin"])
        return resp.json() if resp and resp.status_code == 200 else {}

    def get_checkin_stats(self, season_phase: str = None) -> dict:
        """Lấy thống kê số lượt check-in tại 6 châu lục trên toàn hệ thống"""
        if season_phase:
            resp = self.api_request(
                "GET",
                AppPrefixes.ENDPOINTS["task"]["checkinStatBySeason"],
                params={"season_phase": season_phase},
                authenticated=False,
            )
        else:
            resp = self.api_request("GET", AppPrefixes.ENDPOINTS["task"]["checkinStat"], authenticated=False)
        return resp.json() if resp and resp.status_code == 200 else {}

    def get_rank_me(self) -> dict:
        """Lấy tổng điểm tích lũy và thứ hạng tổng (/api/rank/me)"""
        resp = self.api_request("GET", AppPrefixes.ENDPOINTS["rank"]["me"])
        return resp.json() if resp and resp.status_code == 200 else {}

    def get_rank_me_by_season(self, season_phase: str = "S1") -> dict:
        """Lấy điểm & thứ hạng theo mùa (/api/rank/me-by-season)"""
        resp = self.api_request(
            "GET",
            AppPrefixes.ENDPOINTS["rank"]["meBySeason"],
            params={"season_phase": season_phase},
        )
        return resp.json() if resp and resp.status_code == 200 else {}

    def get_leaderboard(self, season_phase: str = "S1", page: int = 1, page_size: int = 20) -> dict:
        """Lấy bảng xếp hạng mùa giải (/api/rank/leaderboard)"""
        resp = self.api_request(
            "GET",
            AppPrefixes.ENDPOINTS["rank"]["leaderboard"],
            params={"season_phase": season_phase, "page": page, "page_size": page_size},
            authenticated=False,
        )
        return resp.json() if resp and resp.status_code == 200 else {}

    def get_linked_accounts(self) -> dict:
        """Kiểm tra trạng thái liên kết X, Discord, Telegram (/api/profile/linked-accounts)"""
        resp = self.api_request("GET", AppPrefixes.ENDPOINTS["profile"]["linkedAccounts"])
        return resp.json() if resp and resp.status_code == 200 else {}

    def get_social_state(self) -> dict:
        """Kiểm tra trạng thái hoàn thành 4 nhiệm vụ Social (/api/profile/social-state)"""
        resp = self.api_request("GET", AppPrefixes.ENDPOINTS["profile"]["socialState"])
        return resp.json() if resp and resp.status_code == 200 else {}

    def get_score_history(self, season_phase: str = None, page: int = 1, page_size: int = 20) -> dict:
        """Lấy lịch sử cộng điểm chi tiết (/api/profile/score-history-log)"""
        ep = (
            AppPrefixes.ENDPOINTS["profile"]["scoreHistoryLogBySeason"]
            if season_phase
            else AppPrefixes.ENDPOINTS["profile"]["scoreHistoryLog"]
        )
        params = {"page": page, "page_size": page_size}
        if season_phase:
            params["season_phase"] = season_phase
        resp = self.api_request("GET", ep, params=params)
        return resp.json() if resp and resp.status_code == 200 else {}

    def get_referral_code(self) -> str:
        """Lấy mã giới thiệu của ví (/api/referral/code)"""
        resp = self.api_request("GET", AppPrefixes.ENDPOINTS["referral"]["code"])
        if resp and resp.status_code == 200:
            return resp.json().get("invitation_code")
        return self.invitation_code

    def get_invitees_count(self) -> dict:
        """Lấy số lượng ref trực tiếp (tầng 1) và gián tiếp (tầng 2) (/api/referral/invitees-count)"""
        resp = self.api_request("GET", AppPrefixes.ENDPOINTS["referral"]["inviteesCount"])
        return resp.json() if resp and resp.status_code == 200 else {}

    def get_invitees_details(self, season_phase: str = None, page: int = 1, page_size: int = 20) -> dict:
        """Lấy danh sách chi tiết các ví tuyến dưới và điểm hoa hồng (/api/referral/invitees-details)"""
        params = {"page": page, "page_size": page_size}
        if season_phase:
            params["season_phase"] = season_phase
        resp = self.api_request("GET", AppPrefixes.ENDPOINTS["referral"]["inviteesDetails"], params=params)
        return resp.json() if resp and resp.status_code == 200 else {}

    # -------------------- 3. NHIỆM VỤ MẠNG XÃ HỘI (SOCIAL TASKS & OAUTH) --------------------
    def get_oauth_authorize_url(self, provider: str) -> str:
        """
        Lấy link kết nối OAuth cho 'twitter', 'discord', hoặc 'telegram'
        (Dành cho trường hợp người dùng muốn mở trình duyệt liên kết tài khoản mạng xã hội)
        """
        if provider == "twitter":
            ep = AppPrefixes.ENDPOINTS["twitter"]["requestToken"]
        elif provider == "discord":
            ep = AppPrefixes.ENDPOINTS["discord"]["authorizeUrl"]
        elif provider == "telegram":
            ep = AppPrefixes.ENDPOINTS["telegram"]["authorizeUrl"]
        else:
            return None
        resp = self.api_request("GET", ep)
        if resp and resp.status_code == 200:
            return resp.json().get("authorize_url")
        return None

    def run_social_tasks(self):
        """
        Tự động kiểm tra các tài khoản mạng xã hội đã liên kết (X, Discord, Telegram)
        và gửi yêu cầu verify nhận điểm nếu nhiệm vụ chưa hoàn thành.
        """
        if not CONFIG.get("AUTO_VERIFY_SOCIAL", True):
            return

        linked = self.get_linked_accounts()
        social = self.get_social_state()
        if not linked or not social:
            return

        completed_any = []

        # 1. X (Twitter) Follow & Retweet
        if linked.get("bind_twitter"):
            if social.get("is_twitter_follow") == 0:
                r_fol = self.api_request("POST", AppPrefixes.ENDPOINTS["twitter"]["followVerify"])
                if r_fol and r_fol.status_code == 200 and r_fol.json().get("verified"):
                    completed_any.append("X Follow (+50đ)")
            if social.get("is_twitter_retweet") == 0:
                r_rt = self.api_request("POST", AppPrefixes.ENDPOINTS["twitter"]["retweetVerify"])
                if r_rt and r_rt.status_code == 200 and r_rt.json().get("verified"):
                    completed_any.append("X Retweet (+25đ)")

        # 2. Discord Join Guild
        if linked.get("bind_discord") and social.get("is_discord_join") == 0:
            r_dis = self.api_request("POST", AppPrefixes.ENDPOINTS["discord"]["joinGuild"])
            if r_dis and r_dis.status_code == 200 and r_dis.json().get("status") in ("joined", "already_joined"):
                completed_any.append("Discord Join (+50đ)")

        # 3. Telegram Subscribe
        if linked.get("bind_telegram") and social.get("is_telegram_join") == 0:
            r_tg = self.api_request("POST", AppPrefixes.ENDPOINTS["telegram"]["subscribe"])
            if r_tg and r_tg.status_code == 200 and r_tg.json().get("status") in ("subscribed", "already_subscribed"):
                completed_any.append("Telegram Subscribe (+50đ)")

        if completed_any:
            log(self.acc_idx, f"Hoàn thành Social: {', '.join(completed_any)}", Colors.GREEN)

    # -------------------- 4. TƯƠNG TÁC BLOCKCHAIN BSC MAINNET & ON-CHAIN CHECK-IN --------------------
    def rpc_call(self, method: str, params: list, retries: int = 4):
        """Gọi JSON-RPC trực tiếp tới mạng BSC Mainnet (tự động đổi RPC & fallback nếu proxy nghẽn)"""
        payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
        for attempt in range(retries):
            rpc_url = NetworkConfig.BSC_RPC_URLS[self.rpc_index % len(NetworkConfig.BSC_RPC_URLS)]
            try:
                resp = (
                    self.session.post(rpc_url, json=payload, timeout=15)
                    if attempt < 2
                    else requests.post(rpc_url, json=payload, timeout=15)
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if "error" not in data:
                        return data.get("result")
            except Exception:
                self.rotate_proxy()
            self.rpc_index = (self.rpc_index + 1) % len(NetworkConfig.BSC_RPC_URLS)
        return None

    def get_bnb_balance(self) -> float:
        """Lấy số dư BNB trên mạng BSC Mainnet (Chain ID 56)"""
        res = self.rpc_call("eth_getBalance", [self.checksum_address, "latest"])
        if not res:
            return 0.0
        try:
            return int(res, 16) / (10 ** NetworkConfig.NATIVE_DECIMALS)
        except Exception:
            return 0.0

    def is_legal_location(self, contract_address: str, continent: str) -> bool:
        """
        Gọi hàm view `legal_location(string)` trên Smart Contract để kiểm tra châu lục có đang mở không
        """
        encoded_arg = eth_abi.encode(["string"], [continent]).hex()
        call_data = NetworkConfig.SELECTOR_LEGAL_LOCATION + encoded_arg
        res = self.rpc_call(
            "eth_call",
            [{"to": contract_address, "data": call_data}, "latest"],
        )
        if not res or res == "0x":
            return False
        try:
            return int(res, 16) == 1
        except Exception:
            return False

    def encode_checkin_data(self, continent: str) -> str:
        """Mã hóa ABI cho hàm `checkIn(string _location)`"""
        encoded_arg = eth_abi.encode(["string"], [continent]).hex()
        return NetworkConfig.SELECTOR_CHECKIN + encoded_arg

    def wait_for_tx_receipt(self, tx_hash: str, timeout_sec: int = 60) -> dict:
        """Chờ Transaction Receipt trên mạng BSC Mainnet"""
        start = time.time()
        while time.time() - start < timeout_sec:
            receipt = self.rpc_call("eth_getTransactionReceipt", [tx_hash])
            if receipt:
                return receipt
            time.sleep(3)
        return None

    def run_daily_checkin(self, task_cfg: dict) -> str:
        """
        Kiểm tra trạng thái Check-in hàng ngày và thực hiện Check-in On-chain trên BSC Mainnet nếu đủ điều kiện
        """
        status_data = self.get_my_checkin_status()
        checked_today = status_data.get("checked_in_today") == 1
        last_loc = status_data.get("last_checkin_location")

        if checked_today:
            return f"Đã Check-in ({last_loc or 'OK'})"

        if not CONFIG.get("AUTO_CHECKIN_ONCHAIN", True):
            return "Chưa Check-in (Tắt Auto)"

        bnb_balance = self.get_bnb_balance()
        min_bnb = float(CONFIG.get("MIN_BNB_FOR_CHECKIN", 0.00003))
        if bnb_balance < min_bnb:
            return f"Chưa Check-in (Thiếu gas: {bnb_balance:.5f} BNB)"

        contract_info = task_cfg.get("checkin-contract") or {}
        contract_addr = contract_info.get("contract_address") or NetworkConfig.DEFAULT_CHECKIN_CONTRACT

        # Chọn châu lục check-in (Hỗ trợ RANDOM, MOST_POPULAR, LEAST_POPULAR hoặc mã châu lục cụ thể)
        pref = str(CONFIG.get("PREFERRED_CONTINENT", "RANDOM")).upper().strip()
        candidates = list(AppPrefixes.CONTINENTS)
        if pref == "MOST_POPULAR":
            stats = self.get_checkin_stats().get("items") or []
            if stats:
                sorted_stats = sorted(stats, key=lambda x: x.get("count", 0), reverse=True)
                candidates = [x["continent"] for x in sorted_stats if x.get("continent") in AppPrefixes.CONTINENTS]
        elif pref == "LEAST_POPULAR":
            stats = self.get_checkin_stats().get("items") or []
            if stats:
                sorted_stats = sorted(stats, key=lambda x: x.get("count", 0))
                candidates = [x["continent"] for x in sorted_stats if x.get("continent") in AppPrefixes.CONTINENTS]
        elif pref in AppPrefixes.CONTINENTS:
            candidates.remove(pref)
            candidates.insert(0, pref)
        else:
            random.shuffle(candidates)

        chosen_continent = None
        for cont in candidates:
            if self.is_legal_location(contract_addr, cont):
                chosen_continent = cont
                break

        if not chosen_continent:
            return "Chưa Check-in (Không có location hợp lệ)"

        # Chuẩn bị giao dịch checkIn(string) trên BSC Mainnet
        call_data = self.encode_checkin_data(chosen_continent)
        nonce_hex = self.rpc_call("eth_getTransactionCount", [self.checksum_address, "pending"])
        gas_price_hex = self.rpc_call("eth_gasPrice", [])
        if not nonce_hex or not gas_price_hex:
            return "Lỗi lấy Nonce/GasPrice BSC"

        nonce = int(nonce_hex, 16)
        gas_price = int(gas_price_hex, 16)
        max_gas_wei = int(float(CONFIG.get("MAX_GAS_PRICE_GWEI", 3.0)) * 1e9)
        if gas_price > max_gas_wei:
            gas_price = max_gas_wei

        est_gas_hex = self.rpc_call(
            "eth_estimateGas",
            [{"from": self.checksum_address, "to": contract_addr, "data": call_data, "value": "0x0"}],
        )
        gas_limit = int(int(est_gas_hex, 16) * 1.2) if est_gas_hex else 100000

        tx = {
            "chainId": NetworkConfig.CHAIN_ID,
            "nonce": nonce,
            "to": eth_utils.to_checksum_address(contract_addr),
            "value": 0,
            "gas": gas_limit,
            "gasPrice": gas_price,
            "data": call_data,
        }

        try:
            signed_tx = Account.sign_transaction(tx, self.private_key)
            raw_hex = signed_tx.raw_transaction.hex() if hasattr(signed_tx, "raw_transaction") else signed_tx.rawTransaction.hex()
            if not raw_hex.startswith("0x"):
                raw_hex = "0x" + raw_hex

            tx_hash = self.rpc_call("eth_sendRawTransaction", [raw_hex])
            if not tx_hash:
                return "Gửi tx Check-in thất bại"

            log(self.acc_idx, f"Đã gửi tx Check-in ({chosen_continent}): {tx_hash[:12]}...", Colors.YELLOW)
            receipt = self.wait_for_tx_receipt(tx_hash, timeout_sec=60)
            if receipt and int(receipt.get("status", "0x0"), 16) == 1:
                # Đợi Backend index sự kiện CheckIn từ contract (tối đa ~15s)
                for _ in range(5):
                    time.sleep(3)
                    st = self.get_my_checkin_status()
                    if st.get("checked_in_today") == 1:
                        break
                log(self.acc_idx, f"Check-in thành công tại {chosen_continent} (+5đ)!", Colors.GREEN)
                return f"Đã Check-in ({chosen_continent})"
            else:
                return f"Tx Check-in lỗi ({tx_hash[:10]})"
        except Exception as e:
            log(self.acc_idx, f"Lỗi ký/gửi tx Check-in: {e}", Colors.RED)
            return "Lỗi tx Check-in"


# ==================== LUỒNG XỬ LÝ TỪNG TÀI KHOẢN ====================
def process_account(idx: int, acc_data: dict, proxies: list, shared_task_cfg: dict) -> float:
    pk = acc_data["private_key"]
    client = FourDLabsClient(idx, pk, proxies)

    if not client.login():
        return time.time() + 600

    season_phase = (shared_task_cfg.get("season") or {}).get("season_phase") or CONFIG.get("SEASON_PHASE", "S1")

    # 1. Thực hiện Daily Check-in On-chain (nếu bật & ví có BNB)
    checkin_result_str = client.run_daily_checkin(shared_task_cfg)

    # 2. Thực hiện verify các nhiệm vụ Social (nếu ví đã liên kết OAuth)
    client.run_social_tasks()

    # 3. Lấy thông tin Điểm (Score), Thứ hạng (Rank) & Thống kê Ref 2 tầng
    rank_data = client.get_rank_me_by_season(season_phase) or client.get_rank_me()
    ref_cnt_data = client.get_invitees_count()
    my_ref = client.invitation_code or client.get_referral_code() or "N/A"

    total_score = rank_data.get("total_score", "0")
    checkin_score = rank_data.get("checkin_score", "0")
    social_score = rank_data.get("social_score", "0")
    refer_score = rank_data.get("refer_score", "0")
    s_rank = rank_data.get("season_rank") or rank_data.get("cumulative_rank") or 0

    direct_refs = ref_cnt_data.get("direct_invite_count", 0)
    indirect_refs = ref_cnt_data.get("indirect_invite_count", 0)

    score_str = f"{total_score} pts (Checkin:{checkin_score} | Social:{social_score} | Ref:{refer_score})"
    rank_str = f"#{s_rank} ({season_phase})" if s_rank else f"Unranked ({season_phase})"
    ref_count_str = f"Direct:{direct_refs} | Indirect:{indirect_refs}"

    append_log_file(
        wallet=client.checksum_address,
        my_ref=my_ref,
        score_str=score_str,
        rank_str=rank_str,
        ref_count_str=ref_count_str,
        checkin_str=checkin_result_str,
    )

    log(
        idx,
        f"Xong | {rank_str} | {Colors.GREEN}{total_score} pts{Colors.RESET} | Ref: {direct_refs}/{indirect_refs} | {checkin_result_str}",
    )

    min_wait = int(CONFIG.get("ROUND_DELAY_MIN_MINUTES", 720)) * 60
    max_wait = int(CONFIG.get("ROUND_DELAY_MAX_MINUTES", 1440)) * 60
    return time.time() + random.randint(min_wait, max(min_wait, max_wait))


VN_TZ = timezone(timedelta(hours=7))


def calculate_next_round_delay():
    """
    Tính thời gian nghỉ cho round tiếp theo:
    - Nếu bật RANDOM_DAILY_SCHEDULE_UTC7:
      Lên lịch một mốc giờ ngẫu nhiên trong khung giờ (SCHEDULE_HOUR_START_UTC7 -> SCHEDULE_HOUR_END_UTC7)
      của ngày tiếp theo theo múi giờ Việt Nam (UTC+7).
    - Nếu tắt:
      Dùng khoảng thời gian ngẫu nhiên giữa ROUND_DELAY_MIN_MINUTES và ROUND_DELAY_MAX_MINUTES.
    """
    if CONFIG.get("RANDOM_DAILY_SCHEDULE_UTC7", True):
        now_vn = datetime.now(VN_TZ)
        tomorrow = now_vn.date() + timedelta(days=1)
        h_start = int(CONFIG.get("SCHEDULE_HOUR_START_UTC7", 7))
        h_end = int(CONFIG.get("SCHEDULE_HOUR_END_UTC7", 22))
        if h_end <= h_start:
            h_end = min(23, h_start + 1)

        target_hour = random.randint(h_start, h_end - 1)
        target_minute = random.randint(0, 59)
        target_second = random.randint(0, 59)
        target_dt = datetime(
            tomorrow.year,
            tomorrow.month,
            tomorrow.day,
            target_hour,
            target_minute,
            target_second,
            tzinfo=VN_TZ,
        )
        sleep_sec = max(60, int((target_dt - now_vn).total_seconds()))
        target_str = target_dt.strftime("%H:%M:%S ngày %d/%m/%Y")
        return sleep_sec, target_str
    else:
        min_sec = int(CONFIG.get("ROUND_DELAY_MIN_MINUTES", 720)) * 60
        max_sec = int(CONFIG.get("ROUND_DELAY_MAX_MINUTES", 1440)) * 60
        sleep_sec = random.randint(min_sec, max(min_sec, max_sec))
        next_dt = datetime.now(VN_TZ) + timedelta(seconds=sleep_sec)
        target_str = next_dt.strftime("%H:%M:%S ngày %d/%m/%Y")
        return sleep_sec, target_str


# ==================== HÀM CHÍNH (MAIN) ====================
def main():
    global CONFIG
    CONFIG = get_config()

    accounts = load_accounts("account.txt")
    proxies = load_proxies("proxy.txt")

    if not accounts:
        log(None, "Không tìm thấy tài khoản trong account.txt!", Colors.RED)
        return

    threads = max(1, min(int(CONFIG.get("THREADS", 10)), len(accounts)))
    ref_default = CONFIG.get("INVITATION_CODE", "").strip()
    ref_info = f" | Ref: {ref_default}" if ref_default else ""
    print(
        f"{Colors.GREEN}{Colors.BOLD}=== 4DLABS TESTER BOT ({NetworkConfig.NETWORK_NAME} - ChainID {NetworkConfig.CHAIN_ID}) | Acc: {len(accounts)} | Proxy: {len(proxies)} | Luồng: {threads}{ref_info} ==={Colors.RESET}",
        flush=True,
    )

    # Tự động quét và rút BNB từ sàn Binance vào các ví có balance = 0
    withdraw_binance_to_zero_wallets(accounts, proxies)

    cycle = 1
    while True:
        reset_log_file(cycle)
        log(None, f"--- Bắt đầu chu kỳ #{cycle} (Đã làm mới {LOG_FILE}) ---", Colors.BOLD)

        # Lấy cấu hình task-config dùng chung cho cả round
        probe_client = FourDLabsClient(1, accounts[0]["private_key"], proxies)
        shared_task_cfg = probe_client.get_task_config()
        season_title = (shared_task_cfg.get("season") or {}).get("season_title") or "Season 1: Prelude"
        contract_addr = (shared_task_cfg.get("checkin-contract") or {}).get("contract_address") or NetworkConfig.DEFAULT_CHECKIN_CONTRACT
        log(None, f"Mùa giải: {season_title} | Check-in Contract (BSC): {contract_addr}", Colors.CYAN)

        earliest_ready_at = time.time() + 43200

        w_min = float(CONFIG.get("WALLET_DELAY_MIN_SECONDS", 15))
        w_max = float(CONFIG.get("WALLET_DELAY_MAX_SECONDS", 45))

        if threads == 1:
            for idx, acc in enumerate(accounts, 1):
                ready_at = process_account(idx, acc, proxies, shared_task_cfg)
                if ready_at < earliest_ready_at:
                    earliest_ready_at = ready_at
                if idx < len(accounts):
                    w_delay = round(random.uniform(min(w_min, w_max), max(w_min, w_max)), 1)
                    log(None, f"Nghỉ ngẫu nhiên {w_delay}s trước khi chuyển sang ví #{idx+1}...", Colors.DIM)
                    time.sleep(w_delay)
        else:
            def worker_task(idx, acc, initial_delay):
                if initial_delay > 0:
                    time.sleep(initial_delay)
                return process_account(idx, acc, proxies, shared_task_cfg)

            with ThreadPoolExecutor(max_workers=threads) as executor:
                futures = {}
                current_stagger = 0.0
                for idx, acc in enumerate(accounts, 1):
                    futures[executor.submit(worker_task, idx, acc, current_stagger)] = idx
                    stagger_step = random.uniform(min(w_min, w_max), max(w_min, w_max))
                    current_stagger += stagger_step

                for future in as_completed(futures):
                    try:
                        ready_at = future.result()
                        if ready_at and ready_at < earliest_ready_at:
                            earliest_ready_at = ready_at
                    except Exception as e:
                        idx = futures[future]
                        log(idx, f"Lỗi luồng: {e}", Colors.RED)

        cycle += 1
        sleep_sec, target_str = calculate_next_round_delay()
        hours = sleep_sec // 3600
        mins = (sleep_sec % 3600) // 60
        log(
            None,
            f"Hoàn tất chu kỳ. Chu kỳ tiếp theo được lên lịch lúc {Colors.GREEN}{target_str} (UTC+7){Colors.RESET} (Chờ ~{hours}h {mins}m)...",
            Colors.YELLOW,
        )
        try:
            while sleep_sec > 0:
                h = sleep_sec // 3600
                m = (sleep_sec % 3600) // 60
                s = sleep_sec % 60
                sys.stdout.write(f"\r{Colors.DIM}[Chờ round mới - UTC+7] Lên lịch lúc {target_str} | Còn lại: {h:02d}h {m:02d}m {s:02d}s {Colors.RESET}")
                sys.stdout.flush()
                time.sleep(1)
                sleep_sec -= 1
            sys.stdout.write("\r" + " " * 95 + "\r")
        except KeyboardInterrupt:
            print(f"\n{Colors.RED}Đã dừng bot theo yêu cầu người dùng.{Colors.RESET}")
            break


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Colors.RED}Đã dừng bot.{Colors.RESET}")

