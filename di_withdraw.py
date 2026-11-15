"""
BINANCE AUTO-WITHDRAW TO BSC WALLETS (withdraw.py)
-------------------------------------------------------------
- Thư mục: D:\\IEB\\2026\\di
- Tự động quét số dư BNB trên BSC Mainnet của toàn bộ ví trong account.txt.
- Điều kiện: Ví có balance < 0.002 BNB sẽ được tự động rút từ sàn Binance.
- Sử dụng Binance SAPI (/sapi/v1/capital/withdraw/apply) với chữ ký HMAC-SHA256.
- Rút ngẫu nhiên một chút trên mức min sàn để giữ pattern ví tự nhiên.
- Delay ngẫu nhiên giữa các lệnh rút để tránh rate limit Binance.
- Giao diện Log tinh gọn, chuẩn màu ANSI cho Windows CMD.
"""

import os
import sys
import time
import random
import hmac
import hashlib
import urllib.parse
import ctypes
import re
import requests
from eth_account import Account


# ==================== CẤU HÌNH BOT ====================
CONFIG = {
    # File cấu hình đầu vào
    "ACCOUNT_FILE": "account.txt",
    "BINANCE_KEY_FILE": "binance.txt",
    "PROXY_FILE": "proxy.txt",

    # Ngưỡng số dư để kích hoạt rút tiền (< 0.0002 BNB)
    # Rút 1 lần ~0.0005x BNB là đủ chạy cả DI.XYZ lẫn 4Dlabs liên tục hơn 1 tháng
    "THRESHOLD_BNB": 0.0002,

    # Tỷ lệ % rút ngẫu nhiên vượt mức min sàn (+5% đến +10% để tránh sybil giao dịch giống nhau)
    "WITHDRAW_MIN_PCT": 5,
    "WITHDRAW_MAX_PCT": 10,

    # Giãn cách giữa 2 lệnh rút liên tiếp từ Binance (giây)
    "DELAY_BETWEEN_WITHDRAWS_MIN": 20,
    "DELAY_BETWEEN_WITHDRAWS_MAX": 45,

    # Danh sách RPC BSC Mainnet dự phòng
    "BSC_RPC_URLS": [
        "https://bsc-dataseed.binance.org/",
        "https://bsc-dataseed1.defibit.io/",
        "https://bsc-dataseed1.ninicoin.io/",
        "https://bsc-dataseed2.binance.org/",
        "https://56.rpc.thirdweb.com/",
    ],
}


# ==================== KÍCH HOẠT ANSI & CONSOLE ====================
def init_console():
    """Kích hoạt UTF-8 và mã màu ANSI cho Windows CMD để không bị lỗi ký tự ←[..."""
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


def log(tag: str, msg: str, color=Colors.RESET):
    now = time.strftime("%H:%M:%S")
    t_str = f"[{tag}]" if tag else "[BINANCE]"
    if ANSI_ENABLED:
        formatted = f"{Colors.DIM}[{now}]{Colors.RESET} {Colors.CYAN}{t_str:<12}{Colors.RESET} {color}{msg}{Colors.RESET}"
    else:
        formatted = f"[{now}] {t_str:<12} {clean_ansi(msg)}"
    print(formatted, flush=True)


# ==================== PARSER & RPC ====================
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
        log("ERROR", f"Lỗi đọc {filename}: {e}", Colors.RED)
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
        log("ERROR", f"Lỗi đọc {filename}: {e}", Colors.RED)
    return proxies


def bsc_rpc_call(method: str, params: list, proxies: list = None, retries: int = 4):
    """Gọi JSON-RPC tới BSC Mainnet có fallback nhiều node"""
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    for attempt in range(retries):
        rpc_url = CONFIG["BSC_RPC_URLS"][attempt % len(CONFIG["BSC_RPC_URLS"])]
        proxy_dict = None
        if proxies:
            p_url = parse_proxy(random.choice(proxies))
            if p_url:
                proxy_dict = {"http": p_url, "https": p_url}
        try:
            resp = requests.post(rpc_url, json=payload, timeout=10, proxies=proxy_dict)
            if resp.status_code == 200:
                data = resp.json()
                if "error" not in data:
                    return data.get("result")
        except Exception:
            pass

    # Fallback trực tiếp không proxy
    for rpc_url in CONFIG["BSC_RPC_URLS"]:
        try:
            resp = requests.post(rpc_url, json=payload, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if "error" not in data:
                    return data.get("result")
        except Exception:
            pass
    return None


def get_wallet_bnb_balance(address: str, proxies: list = None) -> float:
    """Lấy số dư BNB của ví trên BSC Mainnet"""
    res = bsc_rpc_call("eth_getBalance", [address, "latest"], proxies)
    if not res:
        return 0.0
    try:
        return int(res, 16) / 10**18
    except Exception:
        return 0.0


# ==================== BINANCE SAPI WITHDRAWAL ====================
def load_binance_credentials(filename=CONFIG["BINANCE_KEY_FILE"]):
    """Đọc API Key và Secret Key từ binance.txt"""
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
        log("ERROR", f"Lỗi đọc {filename}: {e}", Colors.RED)
    return api_key, secret_key


def binance_sign(params: dict, secret: str) -> str:
    """Tạo chữ ký HMAC-SHA256 chuẩn cho Binance API"""
    query_string = urllib.parse.urlencode(params)
    return hmac.new(secret.encode("utf-8"), query_string.encode("utf-8"), hashlib.sha256).hexdigest()


def get_binance_bnb_info(api_key: str, secret_key: str) -> dict:
    """Lấy giá BNB/USDT và min rút mạng BSC từ Binance API"""
    info = {"min_withdraw": 0.005, "fee": 0.0001, "bnb_price": 650.0}

    # 1. Giá BNB
    try:
        r_p = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=BNBUSDT", timeout=10)
        if r_p.status_code == 200:
            info["bnb_price"] = float(r_p.json().get("price", 650.0))
    except Exception:
        pass

    # 2. Thông số rút mạng BSC
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


def execute_binance_withdraw(api_key: str, secret_key: str, address: str, amount: float):
    """Gửi yêu cầu rút BNB mạng BSC qua endpoint SAPI /sapi/v1/capital/withdraw/apply"""
    url = "https://api.binance.com/sapi/v1/capital/withdraw/apply"
    ts = int(time.time() * 1000)
    params = {
        "coin": "BNB",
        "network": "BSC",
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


# ==================== MAIN RUNNER ====================
def main():
    print(f"\n{Colors.GREEN}{Colors.BOLD}=== BINANCE AUTO-WITHDRAW TO BSC WALLETS (DI.XYZ) ==={Colors.RESET}\n")

    api_key, secret_key = load_binance_credentials(CONFIG["BINANCE_KEY_FILE"])
    if not api_key or not secret_key:
        log("ERROR", f"Chưa cấu hình API Key & Secret trong file {CONFIG['BINANCE_KEY_FILE']}!", Colors.RED)
        log("HƯỚNG DẪN", "Vui lòng mở file binance.txt và điền API Key (dòng 1) và Secret Key (dòng 2) có quyền [Enable Withdrawals].", Colors.YELLOW)
        return

    accounts = load_accounts(CONFIG["ACCOUNT_FILE"])
    proxies = load_proxies(CONFIG["PROXY_FILE"])

    if not accounts:
        log("ERROR", f"Không tìm thấy ví nào trong {CONFIG['ACCOUNT_FILE']}!", Colors.RED)
        return

    log("SETUP", f"Đã nạp {len(accounts)} ví từ {CONFIG['ACCOUNT_FILE']} | {len(proxies)} proxies", Colors.CYAN)
    log("QUÉT SỐ DƯ", f"Đang kiểm tra số dư BNB (ngưỡng nạp: < {CONFIG['THRESHOLD_BNB']} BNB)...", Colors.CYAN)

    low_wallets = []
    for idx, acc in enumerate(accounts, 1):
        addr = acc["address"]
        bal = get_wallet_bnb_balance(addr, proxies)
        short_addr = f"{addr[:6]}...{addr[-4:]}"
        if bal < CONFIG["THRESHOLD_BNB"]:
            log(f"Acc {idx}", f"Ví {short_addr}: {Colors.RED}{bal:.6f} BNB{Colors.RESET} (< {CONFIG['THRESHOLD_BNB']} BNB) -> Cần nạp gas!", Colors.YELLOW)
            low_wallets.append((idx, addr, bal))
        else:
            log(f"Acc {idx}", f"Ví {short_addr}: {Colors.GREEN}{bal:.6f} BNB{Colors.RESET} (Đủ điều kiện check-in)", Colors.DIM)

    if not low_wallets:
        print(f"\n{Colors.GREEN}{Colors.BOLD}🎉 TẤT CẢ {len(accounts)} VÍ ĐỀU ĐÃ ĐỦ SỐ DƯ (>= {CONFIG['THRESHOLD_BNB']} BNB). KHÔNG CẦN RÚT THÊM!{Colors.RESET}\n")
        return

    # Lấy thông số min rút từ Binance
    bnb_info = get_binance_bnb_info(api_key, secret_key)
    min_w = bnb_info["min_withdraw"]
    price = bnb_info["bnb_price"]

    min_pct = CONFIG["WITHDRAW_MIN_PCT"] / 100.0
    max_pct = CONFIG["WITHDRAW_MAX_PCT"] / 100.0
    range_min = min_w * (1.0 + min_pct)
    range_max = min_w * (1.0 + max_pct)

    print(f"\n{Colors.YELLOW}{Colors.BOLD}Phát hiện {len(low_wallets)}/{len(accounts)} ví thiếu gas (< {CONFIG['THRESHOLD_BNB']} BNB)!{Colors.RESET}")
    log("INFO", f"Giá BNB: ${price:.2f} | Min rút Binance mạng BSC: {min_w} BNB (~${min_w * price:.2f})", Colors.CYAN)
    log("INFO", f"Số lượng rút ngẫu nhiên mỗi ví: {range_min:.5f} - {range_max:.5f} BNB (~${range_min * price:.2f} - ${range_max * price:.2f})", Colors.CYAN)
    print()

    d_min = CONFIG["DELAY_BETWEEN_WITHDRAWS_MIN"]
    d_max = CONFIG["DELAY_BETWEEN_WITHDRAWS_MAX"]
    success_count = 0

    for i, (acc_idx, dest_addr, cur_bal) in enumerate(low_wallets, 1):
        rand_amount = round(random.uniform(range_min, range_max), 5)
        usd_val = rand_amount * price
        short_addr = f"{dest_addr[:6]}...{dest_addr[-4:]}"

        log(f"Acc {acc_idx}", f"[{i}/{len(low_wallets)}] Đang gửi lệnh rút {Colors.GREEN}{rand_amount} BNB{Colors.RESET} (~${usd_val:.2f}) tới ví {short_addr}...", Colors.CYAN)
        ok, res = execute_binance_withdraw(api_key, secret_key, dest_addr, rand_amount)

        if ok:
            success_count += 1
            log(f"Acc {acc_idx}", f"Lệnh rút THÀNH CÔNG! Withdraw ID: {Colors.GREEN}{res}{Colors.RESET}", Colors.GREEN)
        else:
            log(f"Acc {acc_idx}", f"Lỗi rút BNB tới {short_addr}: {Colors.RED}{res}{Colors.RESET}", Colors.RED)

        if i < len(low_wallets):
            sleep_delay = round(random.uniform(d_min, d_max), 1)
            log("DELAY", f"Chờ {sleep_delay}s trước khi gửi lệnh tiếp theo để tránh rate limit...", Colors.DIM)
            time.sleep(sleep_delay)

    print(f"\n{Colors.GREEN}{Colors.BOLD}=== HOÀN TẤT RÚT BNB: ĐÃ GỬI {success_count}/{len(low_wallets)} LỆNH THÀNH CÔNG ==={Colors.RESET}\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Đã dừng chương trình.{Colors.RESET}")
