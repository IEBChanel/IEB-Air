"""
miningmachine.py — Auto Registration, EVM Wallet Creation, Ref Binder & X Linker
Target: https://miningmachine.io/r/JeS5fG7_

Chức năng:
  1. Chỉ đăng ký tài khoản (reg acc).
  2. Hỗ trợ cấu hình số lượng (--count) và số luồng đồng thời (--threads).
  3. Tự động sinh ví EVM chuẩn bằng eth_account (Address & Private Key).
  4. Đăng ký / Đăng nhập qua EIP-4361 (Sign-In with Ethereum - SIWE EIP-191).
  5. Tự động liên kết mã giới thiệu (Referral Code).
  6. Tự động xác thực Twitter OAuth 2.0 và liên kết tài khoản X (auth_token & ct0 từ x.txt).
  7. CHỈ XUẤT RA account.txt KHI LIÊN KẾT X THÀNH CÔNG!
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import json
import os
import queue
import random
import re
import secrets
import sys
import threading
import time
from urllib.parse import urlparse, parse_qs

from eth_account import Account
from eth_account.messages import encode_defunct
import requests

# ==================== CẤU HÌNH MẶC ĐỊNH (CONFIG) ====================
BASE = "https://miningmachine.io"
API_BASE = "https://api.miningmachine.io"
DEFAULT_REF = "JeS5fG7_"

DEFAULT_COUNT = 100
DEFAULT_THREADS = 20
DEFAULT_DELAY_MIN = 2.0
DEFAULT_DELAY_MAX = 5.0

ACCOUNTS_FILE = "account.txt"
X_DIE_FILE = "x_die.txt"
X_FILE = "x.txt"
PROXIES_FILE = "proxy.txt"

TWITTER_BEARER = (
    "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
)


class Colors:
    RESET = "\033[0m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    DIM = "\033[2m"
    BOLD = "\033[1m"


print_lock = threading.Lock()
file_lock = threading.Lock()
die_lock = threading.Lock()
count_lock = threading.Lock()


def init_console():
    if os.name == "nt":
        os.system("")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def log(worker_id, msg: str, color: str = Colors.RESET):
    now = datetime.now().strftime("%H:%M:%S")
    prefix = f"[Thread-{worker_id}]" if worker_id is not None else "[SYSTEM]"
    with print_lock:
        print(
            f"{Colors.DIM}[{now}]{Colors.RESET} {Colors.CYAN}{prefix:<12}{Colors.RESET} {color}{msg}{Colors.RESET}",
            flush=True,
        )


def load_proxies(filepath: str = PROXIES_FILE) -> list:
    if not os.path.exists(filepath):
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]


def parse_proxy(proxy_raw: str) -> dict:
    if not proxy_raw:
        return None
    proxy_raw = proxy_raw.strip()
    if "://" in proxy_raw:
        return {"http": proxy_raw, "https": proxy_raw}
    if "@" in proxy_raw:
        url = f"http://{proxy_raw}"
        return {"http": url, "https": url}
    parts = proxy_raw.split(":")
    if len(parts) == 4:
        ip, port, user, pw = parts
        url = f"http://{user}:{pw}@{ip}:{port}"
        return {"http": url, "https": url}
    if len(parts) == 2:
        url = f"http://{parts[0]}:{parts[1]}"
        return {"http": url, "https": url}
    return None


def load_x_accounts(filepath: str = X_FILE) -> list:
    """Trích xuất username, auth_token và ct0 từ file x.txt."""
    if not os.path.exists(filepath):
        return []
    accounts = []
    with open(filepath, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("|")
            username = parts[0] if parts else f"x_acc_{idx}"

            ct0_m = re.search(r'ct0=([a-f0-9]+)', line)
            auth_token_m = re.search(r'auth_token=([a-f0-9]+)', line)

            ct0 = ct0_m.group(1) if ct0_m else ""
            auth_token = auth_token_m.group(1) if auth_token_m else ""

            if auth_token and ct0:
                accounts.append({
                    "id": idx,
                    "username": username,
                    "ct0": ct0,
                    "auth_token": auth_token,
                    "raw": line,
                })
    return accounts


def generate_evm_wallet() -> tuple[str, str, Account]:
    """Sinh cặp ví EVM chuẩn bằng eth_account: (address, private_key, account_obj)."""
    private_key = "0x" + secrets.token_hex(32)
    acct = Account.from_key(private_key)
    return acct.address, private_key, acct


def get_next_account_index(filepath: str = ACCOUNTS_FILE) -> int:
    """Đếm số dòng hợp lệ hiện tại trong file account.txt để tạo STT tiếp theo."""
    if not os.path.exists(filepath):
        return 1
    count = 0
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip() and not line.strip().startswith("#"):
                count += 1
    return count + 1


# ==================== LỚP GIAO TIẾP VỚI MININGMACHINE API ====================
class MiningMachineClient:
    def __init__(self, proxy=None, worker_id=1):
        self.worker_id = worker_id
        self.s = requests.Session()
        if proxy:
            self.s.proxies.update(proxy)
        self.s.headers.update({
            "User-Agent": UA,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": BASE,
            "Referer": f"{BASE}/app",
        })
        self.token = None
        self.address = None

    def auth_with_wallet(self, acct: Account) -> tuple[bool, str]:
        """Thực hiện đăng nhập ví EVM (EIP-4361 SIWE)."""
        self.address = acct.address.lower()
        try:
            r_nonce = self.s.get(
                f"{API_BASE}/api/auth/wallet/nonce?address={self.address}",
                timeout=25,
            )
            if r_nonce.status_code != 200:
                return False, f"Lỗi lấy nonce ({r_nonce.status_code}): {r_nonce.text[:100]}"

            data = r_nonce.json()
            message = data.get("message")
            if not message:
                return False, "Không có trường message trong phản hồi nonce"

            msghash = encode_defunct(text=message)
            signed = acct.sign_message(msghash)
            signature = signed.signature.hex()
            if not signature.startswith("0x"):
                signature = "0x" + signature

            r_ver = self.s.post(
                f"{API_BASE}/api/auth/wallet/verify",
                json={"address": self.address, "signature": signature},
                timeout=25,
            )
            if r_ver.status_code != 200:
                return False, f"Lỗi verify ví ({r_ver.status_code}): {r_ver.text[:100]}"

            j_ver = r_ver.json()
            self.token = j_ver.get("accessToken")
            if not self.token:
                return False, "Không nhận được accessToken"

            self.s.headers["Authorization"] = f"Bearer {self.token}"
            return True, self.token
        except Exception as e:
            return False, f"Exception auth: {e}"

    def bind_referral(self, ref_code: str = DEFAULT_REF) -> tuple[bool, str]:
        """Gán mã giới thiệu."""
        try:
            r = self.s.post(
                f"{API_BASE}/api/mining/referral/bind",
                json={"code": ref_code},
                timeout=20,
            )
            if r.status_code == 200:
                return True, "Liên kết Ref thành công"
            return False, f"HTTP {r.status_code}: {r.text[:80]}"
        except Exception as e:
            return False, f"Exception bind_ref: {e}"

    def get_x_status(self) -> dict:
        """Kiểm tra trạng thái liên kết X."""
        try:
            r = self.s.get(f"{API_BASE}/api/x/status", timeout=20)
            return r.json() if r.status_code == 200 else {}
        except Exception:
            return {}

    def get_profile(self) -> dict:
        """Lấy thông tin profile người dùng."""
        try:
            r = self.s.get(f"{API_BASE}/api/mining/me", timeout=20)
            return r.json() if r.status_code == 200 else {}
        except Exception:
            return {}

    def link_x_account(self, x_acc: dict, proxy_raw: str = None) -> tuple[bool, str]:
        """
        Thực hiện toàn bộ quy trình Twitter OAuth 2.0 tự động:
          1. Gọi /api/x/link-start lấy OAuth URL.
          2. Dùng auth_token và ct0 gọi Twitter OAuth API để phê duyệt quyền.
          3. Đón redirect_uri chứa code và state gửi ngược về callback của MiningMachine.
        """
        try:
            r_start = self.s.post(f"{API_BASE}/api/x/link-start", timeout=25)
            if r_start.status_code != 200:
                return False, f"Lỗi gọi link-start ({r_start.status_code}): {r_start.text[:80]}"

            oauth_url = r_start.json().get("url")
            if not oauth_url:
                return False, "Không có url trong phản hồi link-start"

            parsed = urlparse(oauth_url)
            qs = parse_qs(parsed.query)
            client_id = qs.get("client_id", [""])[0]
            redirect_uri = qs.get("redirect_uri", [""])[0]
            state = qs.get("state", [""])[0]
            code_challenge = qs.get("code_challenge", [""])[0]
            code_challenge_method = qs.get("code_challenge_method", [""])[0]
            scope = qs.get("scope", [""])[0]

            s_tw = requests.Session()
            if proxy_raw:
                p = parse_proxy(proxy_raw)
                if p:
                    s_tw.proxies.update(p)

            s_tw.headers.update({
                "User-Agent": UA,
                "x-csrf-token": x_acc["ct0"],
                "authorization": TWITTER_BEARER,
                "content-type": "application/x-www-form-urlencoded",
                "Origin": "https://x.com",
                "Referer": oauth_url,
            })
            for dom in [".x.com", ".twitter.com"]:
                s_tw.cookies.set("auth_token", x_acc["auth_token"], domain=dom)
                s_tw.cookies.set("ct0", x_acc["ct0"], domain=dom)

            api_auth_url = (
                f"https://x.com/i/api/2/oauth2/authorize?client_id={client_id}&code_challenge={code_challenge}"
                f"&code_challenge_method={code_challenge_method}&redirect_uri={redirect_uri}&response_type=code"
                f"&scope={scope}&state={state}"
            )
            r_get_auth = s_tw.get(api_auth_url, timeout=30)
            if r_get_auth.status_code != 200:
                return False, f"Twitter GET authorize thất bại ({r_get_auth.status_code}): {r_get_auth.text[:80]}"

            auth_code = r_get_auth.json().get("auth_code")
            if not auth_code:
                return False, "Không lấy được auth_code từ Twitter"

            r_approve = s_tw.post(
                "https://x.com/i/api/2/oauth2/authorize",
                data={"approval": "true", "code": auth_code},
                timeout=30,
            )
            if r_approve.status_code != 200:
                return False, f"Lỗi approve Twitter ({r_approve.status_code}): {r_approve.text[:80]}"

            redirect_to = r_approve.json().get("redirect_uri")
            if not redirect_to:
                return False, "Không nhận được redirect_uri sau khi approve"

            cb_qs = parse_qs(urlparse(redirect_to).query)
            cb_code = cb_qs.get("code", [""])[0]
            cb_state = cb_qs.get("state", [""])[0]

            cb_url = f"{API_BASE}/api/auth/x/callback?code={cb_code}&state={cb_state}"
            r_cb = self.s.get(cb_url, timeout=25)
            if r_cb.status_code == 200 and r_cb.json().get("linked"):
                status_x = self.get_x_status()
                handle = status_x.get("handle") or x_acc["username"]
                return True, f"@{handle.lstrip('@')}"

            return False, f"Lỗi callback MiningMachine ({r_cb.status_code}): {r_cb.text[:80]}"
        except Exception as e:
            return False, f"Exception link_x: {e}"


# ==================== ĐĂNG KÝ 1 TÀI KHOẢN (WORKER TASK) ====================
def remove_x_from_file(filepath: str, raw_line: str):
    """Xóa một dòng tài khoản X die khỏi file x.txt (Thread-safe)."""
    if not os.path.exists(filepath):
        return
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
        target = raw_line.strip()
        new_lines = [l for l in lines if l.strip() and l.strip() != target]
        with open(filepath, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
    except Exception as e:
        log(None, f"Lỗi khi xóa tài khoản X khỏi {filepath}: {e}", Colors.RED)


# ==================== MAIN WORKER & STANDBY WALLET THREAD POOL ====================
def main():
    init_console()
    ap = argparse.ArgumentParser(
        description="Mining Machine Reg Acc — Chỉ đăng ký tài khoản & xuất ra file khi bind X thành công (Không tạo ref ảo)"
    )
    ap.add_argument("--count", "-n", type=int, default=DEFAULT_COUNT, help=f"Số tài khoản mục tiêu cần tạo thành công (mặc định: {DEFAULT_COUNT})")
    ap.add_argument("--threads", "-t", type=int, default=DEFAULT_THREADS, help=f"Số luồng đồng thời (mặc định: {DEFAULT_THREADS})")
    ap.add_argument("--ref", default=DEFAULT_REF, help=f"Mã giới thiệu (mặc định: {DEFAULT_REF})")
    ap.add_argument("--output", "-o", default=ACCOUNTS_FILE, help=f"File lưu tài khoản thành công (mặc định: {ACCOUNTS_FILE})")
    ap.add_argument("--die-file", default=X_DIE_FILE, help=f"File lưu tài khoản X die/lỗi (mặc định: {X_DIE_FILE})")
    ap.add_argument("--delay-min", type=float, default=DEFAULT_DELAY_MIN, help=f"Giãn cách min giữa các lượt (giây, mặc định: {DEFAULT_DELAY_MIN})")
    ap.add_argument("--delay-max", type=float, default=DEFAULT_DELAY_MAX, help=f"Giãn cách max giữa các lượt (giây, mặc định: {DEFAULT_DELAY_MAX})")
    args = ap.parse_args()

    x_accounts = load_x_accounts(X_FILE)
    proxies = load_proxies(PROXIES_FILE)

    print(
        f"{Colors.GREEN}{Colors.BOLD}=====================================================\n"
        f"  MINING MACHINE — REGISTRATION (ANTI-FAKE REF)\n"
        f"====================================================={Colors.RESET}\n"
        f"  Mục tiêu tài khoản LIVE : {Colors.BOLD}{args.count}{Colors.RESET}\n"
        f"  Số luồng đồng thời      : {Colors.BOLD}{args.threads}{Colors.RESET}\n"
        f"  Mã giới thiệu (Ref)     : {args.ref}\n"
        f"  Tổng nick X trong hàng  : {len(x_accounts)} (từ {X_FILE})\n"
        f"  Số lượng Proxies        : {len(proxies)} (từ {PROXIES_FILE})\n"
        f"  File acc thành công     : {Colors.GREEN}{args.output}{Colors.RESET}\n"
        f"  File lưu acc X DIE      : {Colors.RED}{args.die_file}{Colors.RESET} (tự động xóa khỏi {X_FILE})\n"
        f"  Cơ chế bảo vệ Ref       : {Colors.CYAN}GIỮ VÍ STANDBY, CHỈ BIND REF KHI X SỐNG 100%{Colors.RESET}\n"
        f"=====================================================\n",
        flush=True,
    )

    if not x_accounts:
        print(f"{Colors.RED}[LỖI] Không tìm thấy tài khoản X nào trong file {X_FILE}! Cần có tài khoản X để bind.{Colors.RESET}")
        return

    # Nạp toàn bộ nick X vào Queue để các luồng rút an toàn
    x_queue = queue.Queue()
    for x_acc in x_accounts:
        x_queue.put(x_acc)

    stop_event = threading.Event()
    success_count = 0
    fail_count = 0
    total_x_tested = 0

    def worker_loop(thread_idx: int):
        nonlocal success_count, fail_count, total_x_tested
        while not stop_event.is_set():
            # Kiểm tra nếu đã đủ số lượng tài khoản mục tiêu
            with count_lock:
                if success_count >= args.count:
                    break

            # 1. Sinh 1 ví EVM mới và giữ ở trạng thái STANDBY (CHƯA BIND REF!)
            addr, priv, acct = generate_evm_wallet()
            short_addr = f"{addr[:8]}...{addr[-6:]}"
            client = MiningMachineClient(worker_id=thread_idx)
            ok_auth, msg_auth = client.auth_with_wallet(acct)
            if not ok_auth:
                log(thread_idx, f"Đăng nhập SIWE thất bại: {msg_auth}", Colors.RED)
                time.sleep(1)
                continue

            log(thread_idx, f"Đã sinh ví mới [STANDBY]: {short_addr} (CHƯA BIND REF, chờ nick X sống)...", Colors.CYAN)

            # 2. Vòng lặp thử lần lượt từng nick X vào ví này
            while not stop_event.is_set():
                with count_lock:
                    if success_count >= args.count:
                        break

                try:
                    x_acc = x_queue.get_nowait()
                except queue.Empty:
                    stop_event.set()
                    log(thread_idx, "Đã hết tài khoản X trong hàng chờ để test!", Colors.YELLOW)
                    break

                with count_lock:
                    total_x_tested += 1

                # Lấy proxy
                proxy_raw = random.choice(proxies) if proxies else None
                if proxy_raw:
                    p = parse_proxy(proxy_raw)
                    if p:
                        client.s.proxies.update(p)

                log(thread_idx, f"Thử bind nick X @{x_acc['username']} vào ví {short_addr}...", Colors.BLUE)
                ok_x, res_x = client.link_x_account(x_acc, proxy_raw=proxy_raw)

                if not ok_x:
                    # BIND X THẤT BẠI -> NICK X DIE!
                    log(thread_idx, f"-> X DIE [@{x_acc['username']}]: {res_x} -> XUẤT RA {args.die_file} & XÓA KHỎI {X_FILE}!", Colors.RED)
                    with die_lock:
                        with open(args.die_file, "a", encoding="utf-8") as f:
                            f.write(f"{x_acc['raw']}\n")
                        remove_x_from_file(X_FILE, x_acc["raw"])
                    with count_lock:
                        fail_count += 1
                    # VÍ NÀY VẪN GIỮ NGUYÊN (CHƯA BIND REF)! Tiếp tục thử nick X tiếp theo vào ví này
                    time.sleep(random.uniform(args.delay_min, args.delay_max))
                    continue

                # BIND X THÀNH CÔNG!
                x_handle = res_x
                log(thread_idx, f"-> LIÊN KẾT X THÀNH CÔNG: {x_handle} vào ví {short_addr}!", Colors.GREEN + Colors.BOLD)

                # CHỈ BÂY GIỜ MỚI GỌI BIND REF (ĐẢM BẢO 100% LÀ REF THẬT, KHÔNG TẠO REF ẢO/RÁC)!
                ok_ref, msg_ref = client.bind_referral(args.ref)
                log(thread_idx, f"Gán mã Ref ({args.ref}): {msg_ref}", Colors.GREEN if ok_ref else Colors.YELLOW)

                # Lấy nickname
                profile = client.get_profile()
                nickname = profile.get("nickname", "Miner")

                # Lưu vào account.txt (Thread-safe)
                with file_lock:
                    stt = get_next_account_index(args.output)
                    account_line = f"{stt}|{addr}|{priv}|{client.token}|{x_handle}|OFFLINE|0MP|{nickname}\n"
                    with open(args.output, "a", encoding="utf-8") as f:
                        f.write(account_line)

                with count_lock:
                    success_count += 1

                log(
                    thread_idx,
                    f"-> [HOÀN TẤT ACC #{stt}] Ví: {short_addr} | X: {x_handle} | Ref: {args.ref} | Lưu: {args.output}",
                    Colors.GREEN + Colors.BOLD,
                )

                # Đã hoàn tất ví này -> Thoát vòng lặp thử X để sinh ví mới cho acc tiếp theo
                time.sleep(random.uniform(args.delay_min, args.delay_max))
                break

    threads = []
    active_workers = min(args.threads, len(x_accounts))
    log(None, f"Khởi động {active_workers} luồng xử lý đồng thời...", Colors.CYAN)

    for w_id in range(1, active_workers + 1):
        t = threading.Thread(target=worker_loop, args=(w_id,), daemon=True)
        threads.append(t)
        t.start()
        time.sleep(0.3)

    for t in threads:
        t.join()

    print(
        f"\n{Colors.GREEN}{Colors.BOLD}================ BÁO CÁO TỔNG KẾT REG ACC ================{Colors.RESET}\n"
        f"  Tổng nick X đã test         : {total_x_tested}\n"
        f"  Tài khoản LIVE (Đã lưu)     : {Colors.GREEN}{success_count}{Colors.RESET} -> Đã lưu vào {args.output}\n"
        f"  Nick X DIE (Đã xóa khỏi x)  : {Colors.RED}{fail_count}{Colors.RESET} -> Đã lưu vào {args.die_file}\n"
        f"  Số Ref ảo phát sinh         : {Colors.GREEN}0 (Bảo vệ 100% tỷ lệ chuyển đổi sạch){Colors.RESET}\n"
        f"==========================================================\n",
        flush=True,
    )


if __name__ == "__main__":
    main()
