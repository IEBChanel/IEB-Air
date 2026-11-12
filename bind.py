"""
BULLSHOT GEM - ANTI-SYBIL SOCIAL BINDER (bind.py)
-------------------------------------------------------------
- Tự động liên kết X (Twitter) kèm chữ ký Web3.
- Tự động liên kết 4 mạng xã hội Anti-Sybil (Telegram, Instagram, TikTok, Facebook)
  với phong cách chuẩn từng MXH, tương đối giống với tên X.
- Xử lý mượt mà mã ANSI, chống lỗi "xẹt xẹt" (←[...) trên mọi loại Terminal Windows.
- Chạy độc lập đa luồng cho toàn bộ account.txt HOẶC import làm module cho bullshot.py / weekly_quest.py.
"""

import os
import sys
import time
import random
import re
import ctypes
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from eth_account import Account
from eth_account.messages import encode_defunct

# ==================== KÍCH HOẠT ANSI & CHỐNG LỖI HIỂN THỊ ====================
def init_console_env():
    """
    Bật VT100 mode trên Windows và cấu hình UTF-8.
    Trả về True nếu terminal hỗ trợ ANSI thực sự, ngược lại trả về False.
    """
    if sys.platform == "win32":
        try:
            os.system("")  # Bật ANSI escape sequences trên Windows 10/11
        except Exception:
            pass
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass
        try:
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            mode = ctypes.c_ulong()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                if kernel32.SetConsoleMode(handle, mode.value | 0x0004):
                    return True
        except Exception:
            pass

    # Nếu stdout bị redirect (piped, file, task runner không phải tty) thì tắt ANSI
    is_tty = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
    return is_tty


ANSI_SUPPORTED = init_console_env()

# Thử dùng colorama nếu có để bọc output an toàn
try:
    import colorama
    colorama.init(autoreset=True, strip=not ANSI_SUPPORTED)
except Exception:
    pass


class Colors:
    if ANSI_SUPPORTED:
        RESET = "\033[0m"
        BOLD = "\033[1m"
        DIM = "\033[2m"
        RED = "\033[91m"
        GREEN = "\033[92m"
        YELLOW = "\033[93m"
        BLUE = "\033[94m"
        MAGENTA = "\033[95m"
        CYAN = "\033[96m"
        WHITE = "\033[97m"
    else:
        RESET = ""
        BOLD = ""
        DIM = ""
        RED = ""
        GREEN = ""
        YELLOW = ""
        BLUE = ""
        MAGENTA = ""
        CYAN = ""
        WHITE = ""


print_lock = threading.Lock()
file_lock = threading.Lock()
OUTPUT_FILE = "social_accounts.txt"


def clean_ansi(text: str) -> str:
    """Xóa sạch các ký tự escape ANSI (chống hiện ←[...) nếu terminal không hỗ trợ"""
    if not ANSI_SUPPORTED:
        return re.sub(r"(\033|\x1b)\[[0-9;]*[a-zA-Z]", "", text)
    return text


def log(acc_idx, msg: str, color=""):
    """In log sạch sẽ, đồng bộ luồng và không bị xẹt xẹt đầu dòng"""
    now = datetime.now().strftime("%H:%M:%S")
    tag = f"[Acc {acc_idx}]" if acc_idx is not None else "[BIND]"

    if ANSI_SUPPORTED:
        raw_output = f"{Colors.DIM}[{now}]{Colors.RESET} {Colors.CYAN}{tag:<8}{Colors.RESET} {color}{msg}{Colors.RESET}"
    else:
        raw_output = f"[{now}] {tag:<8} {clean_ansi(msg)}"

    with print_lock:
        print(raw_output, flush=True)


# ==================== KHO TÊN GỐC (50 FIRST NAMES & 50 LAST NAMES) ====================
FIRST_NAMES = [
    "james", "john", "robert", "michael", "william", "david", "richard", "joseph", "thomas", "charles",
    "liam", "noah", "oliver", "lucas", "mateo", "leo", "hugo", "enzo", "luca", "marco",
    "hans", "erik", "ivan", "milan", "felix", "oscar", "louis", "theo", "max", "arthur",
    "emma", "olivia", "ava", "mia", "sofia", "chloe", "elena", "clara", "nina", "eva",
    "alice", "julia", "laura", "sara", "anna", "marie", "lucia", "paula", "marta", "lena",
]

LAST_NAMES = [
    "smith", "jones", "brown", "davis", "miller", "wilson", "moore", "taylor", "clark", "hall",
    "young", "king", "wright", "lopez", "hill", "scott", "green", "adams", "baker", "nelson",
    "carter", "perry", "rossi", "silva", "costa", "meyer", "weber", "novak", "kowal", "leblanc",
    "dupont", "moreau", "garcia", "gomez", "romano", "conti", "bruno", "ricci", "fischer", "wagner",
    "becker", "schulz", "bauer", "klein", "wolf", "braun", "hofer", "huber", "moser", "marino",
]


# ==================== BỘ TẠO USERNAME X (TWITTER) ====================
def generate_x_handle() -> str:
    """Tạo username X ngẫu nhiên 50 tên x 50 họ x 3 kiểu ghép + 5 chữ số"""
    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    digits = "".join(random.choices("0123456789", k=5))
    style = random.randint(1, 3)

    if style == 1:
        return f"{first}{last}{digits}"
    elif style == 2:
        return f"{first}_{last}{digits}"
    else:
        return f"{last}_{first}{digits}"


# ==================== BỘ TẠO IDENTITIES MXH ANTI-SYBIL ====================
def generate_social_identities(x_handle: str) -> dict:
    """
    Sinh 4 username MXH (Telegram, Instagram, TikTok, Facebook) dựa trên tên X,
    tuân thủ nghiêm ngặt regex và phong cách của từng nền tảng:
    - Telegram: ^[a-zA-Z0-9_]{5,32}$ (chữ cái, số, gạch dưới; không dùng dấu chấm)
    - Instagram: ^[a-zA-Z0-9._]{1,30}$ (chữ cái, số, chấm, gạch dưới; không có '..')
    - TikTok: ^[a-zA-Z0-9._]{2,24}$ (chữ cái, số, chấm, gạch dưới)
    - Facebook: ^[a-zA-Z0-9.]{5,50}$ (chữ cái, số, chấm; TUYỆT ĐỐI KHÔNG CÓ '_', không có '..')
    """
    raw = (x_handle or "miner_anon").strip().lstrip("@").lower()
    m = re.match(r"^([a-zA-Z_.]+?)(\d+)?$", raw)
    if m:
        name_core = m.group(1).strip("._")
    else:
        name_core = re.sub(r"[^a-zA-Z_.]", "", raw).strip("._") or "miner"

    first, second = None, None
    if "_" in name_core:
        parts = [p for p in name_core.split("_") if p]
        first = parts[0]
        second = parts[1] if len(parts) > 1 else ""
    elif "." in name_core:
        parts = [p for p in name_core.split(".") if p]
        first = parts[0]
        second = parts[1] if len(parts) > 1 else ""
    else:
        for fn in FIRST_NAMES:
            if name_core.startswith(fn) and len(name_core) > len(fn):
                first = fn
                second = name_core[len(fn):]
                break

    base_clean = re.sub(r"[^a-zA-Z0-9]", "", name_core) or "miner"
    if len(base_clean) < 4:
        base_clean = (base_clean + "user")[:12]

    short_tags = {"ieb", "eth", "sol", "btc", "x", "tg", "dev", "web3", "io", "ai", "vip"}
    if first and second and second in short_tags:
        main_name = first
    else:
        main_name = base_clean

    if not first or not second:
        if len(main_name) >= 6:
            mid = len(main_name) // 2
            first, second = main_name[:mid], main_name[mid:]
        else:
            first, second = main_name, "pro"

    # --- 1. Telegram: ^[a-zA-Z0-9_]{5,32}$ (Không dấu chấm) ---
    tg_candidates = [
        f"{main_name}x",
        f"{main_name}z",
        f"{main_name}_tg",
        f"{main_name}_official",
        f"{main_name}_dev",
        f"{main_name}_crypto",
        f"{first}_{second}",
        f"{first}_{second}_tg",
        f"{main_name}{random.randint(10, 99)}",
    ]
    tg = random.choice(tg_candidates)
    tg = re.sub(r"[^a-zA-Z0-9_]", "_", tg)[:32]
    if len(tg) < 5:
        tg = f"{tg}_{random.randint(100, 999)}"[:32]

    # --- 2. Instagram: ^[a-zA-Z0-9._]{1,30}$ (Không có '..') ---
    ig_exts = ["cte", "eth", "dev", "art", "c", "daily", "official", "vibes", "me", "io"]
    ig_candidates = [
        f"{main_name}.cte",
        f"{main_name}.{random.choice(ig_exts)}",
        f"{first}.{second}",
        f"{first}.{second}.{random.choice(ig_exts)}",
        f"{main_name}.official",
        f"{main_name}_",
        f"{first}_{second}.{random.randint(10, 99)}",
    ]
    ig = random.choice(ig_candidates)
    ig = re.sub(r"[^a-zA-Z0-9._]", "", ig)[:30].rstrip("._")
    while ".." in ig:
        ig = ig.replace("..", ".")
    if not ig:
        ig = f"{main_name}.cte"[:30]

    # --- 3. TikTok: ^[a-zA-Z0-9._]{2,24}$ ---
    tt_candidates = [
        f"{main_name}.tt",
        f"{main_name}_tok",
        f"{main_name}.clips",
        f"{main_name}.media",
        f"{first}_{second}{random.randint(10, 99)}",
        f"{main_name}{random.randint(100, 9999)}",
        f"{first}.{second}.tt",
    ]
    tt = random.choice(tt_candidates)
    tt = re.sub(r"[^a-zA-Z0-9._]", "", tt)[:24].rstrip("._")
    if len(tt) < 2:
        tt = f"{main_name}tt"[:24]

    # --- 4. Facebook: ^[a-zA-Z0-9.]{5,50}$ (TUYỆT ĐỐI KHÔNG DÙNG '_' và '..') ---
    fb_num = "".join(random.choices("0123456789", k=6))
    if len(first) >= 4:
        split_fb = f"{first[:3]}.{first[3:]}.{fb_num}"
    else:
        split_fb = f"{first}.{second}.{fb_num}"

    fb_candidates = [
        split_fb,
        f"{first}.{second}.{fb_num}",
        f"{main_name}.{fb_num}",
        f"{main_name}.profile.{random.randint(10, 99)}",
        f"{first}.{second}.official",
    ]
    fb = random.choice(fb_candidates)
    fb = re.sub(r"[^a-zA-Z0-9.]", ".", fb)[:50].strip(".")
    while ".." in fb:
        fb = fb.replace("..", ".")
    if len(fb) < 5:
        fb = f"{main_name}.{fb_num}"[:50]

    return {"telegram": tg, "instagram": ig, "tiktok": tt, "facebook": fb}


# ==================== HÀM LIÊN KẾT CHO CLIENT ====================
def bind_twitter_for_client(client) -> str:
    """Tự động kiểm tra và liên kết X (Twitter) kèm Web3 signature nếu chưa có"""
    x_handle = client.user_data.get("twitterHandle")
    if x_handle:
        return x_handle

    for _ in range(3):
        auto_handle = generate_x_handle()
        timestamp = int(time.time())
        message = (
            f"Update X (Twitter) on Bull GEM:\n"
            f"Handle: @{auto_handle}\n"
            f"Wallet: {client.wallet_address}\n"
            f"Timestamp: {timestamp}"
        )
        signable_msg = encode_defunct(text=message)
        signed_obj = Account.sign_message(signable_msg, client.private_key)
        sig = signed_obj.signature.hex()
        if not sig.startswith("0x"):
            sig = "0x" + sig

        payload = {
            "twitterHandle": auto_handle,
            "signature": sig,
            "timestamp": timestamp,
        }
        resp = client.request("POST", "/user/link-twitter", payload)
        if resp and resp.status_code == 200:
            client.user_data["twitterHandle"] = auto_handle
            log(client.acc_idx, f"Đã liên kết X: @{auto_handle}", Colors.GREEN)
            return auto_handle
        time.sleep(1)

    return client.user_data.get("twitterHandle") or ""


def bind_all_socials_for_client(client) -> dict:
    """
    Liên kết đủ 4 mạng xã hội Anti-Sybil (Telegram, Instagram, TikTok, Facebook)
    với chữ ký Web3 theo chuẩn Miner Center.
    """
    twitter_handle = bind_twitter_for_client(client) or "miner"

    resp = client.request("GET", "/user/socials")
    if not resp or resp.status_code != 200:
        return {}

    current_socials = resp.json() or {}
    missing = [p for p in ["telegram", "instagram", "tiktok", "facebook"] if not current_socials.get(p)]

    if not missing:
        return current_socials

    generated = generate_social_identities(twitter_handle)
    updated_socials = dict(current_socials)

    for platform in missing:
        handle = generated.get(platform)
        if not handle:
            continue

        timestamp = int(time.time())
        message = (
            f"Update {platform} on Bull GEM:\n"
            f"Handle: @{handle}\n"
            f"Wallet: {client.wallet_address}\n"
            f"Timestamp: {timestamp}"
        )
        signable_msg = encode_defunct(text=message)
        signed_obj = Account.sign_message(signable_msg, client.private_key)
        sig = signed_obj.signature.hex()
        if not sig.startswith("0x"):
            sig = "0x" + sig

        payload = {
            "platform": platform,
            "handle": handle,
            "signature": sig,
            "timestamp": timestamp,
        }
        resp_update = client.request("POST", "/user/socials", payload)
        if resp_update and resp_update.status_code == 200:
            updated_socials[platform] = handle
            log(client.acc_idx, f"Anti-Sybil Bound [{platform.title()}]: @{handle}", Colors.GREEN)
            time.sleep(0.5)
        else:
            err_msg = resp_update.text if resp_update else "Timeout"
            log(client.acc_idx, f"Lỗi bind [{platform.title()}]: {err_msg}", Colors.RED)

    return updated_socials


def append_social_account(wallet: str, x_h: str, tg: str, ig: str, tt: str, fb: str):
    """Ghi danh sách tài khoản đã liên kết ra file (Thread-safe, chống trùng ví)"""
    w_clean = wallet.strip().lower()
    line = f"{w_clean} | @{x_h} | @{tg} | @{ig} | @{tt} | @{fb}\n"
    with file_lock:
        try:
            existing = set()
            if os.path.exists(OUTPUT_FILE):
                with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                    for l in f:
                        if l.strip() and not l.startswith("#"):
                            existing.add(l.split("|")[0].strip().lower())
            if w_clean not in existing:
                with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
                    f.write(line)
                    f.flush()
        except Exception:
            pass


# ==================== CHẠY ĐỘC LẬP ĐA LUỒNG (STANDALONE CLI) ====================
def process_single_bind(idx: int, acc_data: dict, proxies: list):
    """Xử lý bind đầy đủ cho 1 ví"""
    from bullshot import BullshotClient

    pk = acc_data["private_key"]
    client = BullshotClient(idx, pk, proxies)

    if not client.login(silent=True):
        log(idx, "Đăng nhập thất bại, bỏ qua", Colors.RED)
        return False

    # Bind X & Socials
    x_handle = bind_twitter_for_client(client)
    socials = bind_all_socials_for_client(client)

    append_social_account(
        wallet=client.wallet_address,
        x_h=x_handle,
        tg=socials.get("telegram") or "",
        ig=socials.get("instagram") or "",
        tt=socials.get("tiktok") or "",
        fb=socials.get("facebook") or "",
    )
    return True


def run_standalone():
    """Hàm main khi chạy trực tiếp `python bind.py`"""
    from bullshot import load_accounts, load_proxies

    log(None, "Khởi động tool Auto-Bind Anti-Sybil Socials", Colors.CYAN)
    accounts = load_accounts("account.txt")
    proxies = load_proxies("proxy.txt")

    if not accounts:
        log(None, "Không tìm thấy tài khoản trong account.txt!", Colors.RED)
        return

    log(None, f"Tìm thấy {len(accounts)} tài khoản | {len(proxies)} proxies", Colors.YELLOW)

    # Khởi tạo file xuất
    if not os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("# Wallet | X (Twitter) | Telegram | Instagram | TikTok | Facebook\n")

    threads_count = 15
    completed = 0
    total = len(accounts)

    with ThreadPoolExecutor(max_workers=threads_count) as executor:
        futures = {
            executor.submit(process_single_bind, idx + 1, acc, proxies): idx
            for idx, acc in enumerate(accounts)
        }
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                pass
            completed += 1
            if completed % 10 == 0 or completed == total:
                log(None, f"Tiến độ: {completed}/{total} ví đã xử lý", Colors.YELLOW)

    log(None, f"Hoàn tất toàn bộ {total} ví! Dữ liệu xuất tại {OUTPUT_FILE}", Colors.GREEN)


if __name__ == "__main__":
    run_standalone()

