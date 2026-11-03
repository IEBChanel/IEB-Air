"""
run_tasks.py / run_task.py — MiningMachine Task Runner & Auto-Mining Scheduler
Chức năng chính:
  1. Đọc tài khoản từ account.txt (chỉ chạy các acc đã bind X thành công).
  2. Tự động đăng nhập lại bằng Private Key (SIWE EIP-191) để refresh token.
  3. Tự động hoàn thành toàn bộ nhiệm vụ (Tasks) theo cơ chế hiện tại:
     - Follow RigGrid trên Twitter bằng session cookie.
     - Bypass verify nhiệm vụ like/retweet/engagement.
     - Chờ dwell time cho nhiệm vụ visit / time_on_page.
     - Tự động claim phần thưởng nhiệm vụ.
  4. Quản lý khai thác máy đào (Mining):
     - Kiểm tra trạng thái máy đào qua /api/mining/me.
     - Nếu OFFLINE hoặc phiên đào cũ đã kết thúc -> gọi /api/mining/farm/start để claim và khởi động phiên đào mới.
     - Lấy mốc thời gian sessionEndsAt.
  5. Schedule đến phiên claim / khai thác tiếp theo:
     - Tính toán thời gian kết thúc sớm nhất giữa tất cả các tài khoản.
     - Hiển thị đồng hồ đếm ngược sinh động trên console.
     - Tự động thức dậy kích hoạt phiên claim/khai thác mới khi đến giờ.
  6. Hỗ trợ chạy đa luồng (--threads) và chế độ chạy 1 lần (--once).
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
import queue
import re
import sys
import threading
import time
from urllib.parse import urlparse

from eth_account import Account
from eth_account.messages import encode_defunct
import requests

# ==================== CẤU HÌNH (CONFIG) ====================
BASE = "https://miningmachine.io"
API_BASE = "https://api.miningmachine.io"
ACCOUNTS_FILE = "account.txt"
X_FILE = "x.txt"
PROXIES_FILE = "proxy.txt"

DEFAULT_THREADS = 20
DEFAULT_CHECK_INTERVAL = 300  # Fallback 5 phút nếu không lấy được sessionEndsAt
BUFFER_SECONDS = 15           # Chờ thêm 15s sau khi sessionEndsAt để server đóng block

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


def init_console():
    if os.name == "nt":
        os.system("")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def log(acc_id, msg: str, color: str = Colors.RESET):
    now = datetime.now().strftime("%H:%M:%S")
    prefix = f"[Acc #{acc_id:<2}]" if acc_id is not None else "[SCHEDULER]"
    with print_lock:
        print(
            f"{Colors.DIM}[{now}]{Colors.RESET} {Colors.CYAN}{prefix:<12}{Colors.RESET} {color}{msg}{Colors.RESET}",
            flush=True,
        )


def format_seconds(secs: float) -> str:
    secs = max(0, int(secs))
    hours, remainder = divmod(secs, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}h {minutes:02d}m {seconds:02d}s"
    if minutes > 0:
        return f"{minutes}m {seconds:02d}s"
    return f"{seconds}s"


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


def load_proxies(filepath: str = PROXIES_FILE) -> list:
    if not os.path.exists(filepath):
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip() and not l.strip().startswith("#")]


def load_x_accounts(filepath: str = X_FILE) -> dict:
    """Trả về dict: { 'username_lowercase': account_dict } để map nhanh chóng theo handle."""
    if not os.path.exists(filepath):
        return {}
    x_map = {}
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("|")
            uname = parts[0].strip() if parts else ""
            ct0_m = re.search(r'ct0=([a-f0-9]+)', line)
            auth_token_m = re.search(r'auth_token=([a-f0-9]+)', line)
            ct0 = ct0_m.group(1) if ct0_m else ""
            auth_token = auth_token_m.group(1) if auth_token_m else ""
            if auth_token and ct0 and uname:
                x_map[uname.lower().lstrip("@")] = {
                    "username": uname,
                    "ct0": ct0,
                    "auth_token": auth_token,
                    "raw": line,
                }
    return x_map


def load_accounts(filepath: str = ACCOUNTS_FILE) -> list:
    """Đọc danh sách tài khoản từ account.txt, bỏ qua các tài khoản chưa liên kết X."""
    if not os.path.exists(filepath):
        return []
    accounts = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("|")
            if len(parts) < 3:
                continue

            try:
                stt = int(parts[0])
            except ValueError:
                stt = len(accounts) + 1

            addr = parts[1].strip()
            priv = parts[2].strip()
            token = parts[3].strip() if len(parts) > 3 else ""
            x_handle = parts[4].strip() if len(parts) > 4 else ""
            farm_status = parts[5].strip() if len(parts) > 5 else "OFFLINE"
            mining_power = parts[6].strip() if len(parts) > 6 else "0MP"
            nickname = parts[7].strip() if len(parts) > 7 else "Miner"

            if "Chưa liên kết" in x_handle or not x_handle:
                continue

            accounts.append({
                "stt": stt,
                "address": addr,
                "private_key": priv,
                "token": token,
                "x_handle": x_handle,
                "farm_status": farm_status,
                "mining_power": mining_power,
                "nickname": nickname,
            })
    return accounts


def parse_session_ends_at(ends_val) -> datetime:
    """Chuyển đổi sessionEndsAt từ API (ISO format hoặc millisecond timestamp) thành UTC datetime."""
    if not ends_val or ends_val == "N/A":
        return None
    if isinstance(ends_val, (int, float)):
        ts = ends_val / 1000.0 if ends_val > 1e11 else ends_val
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    if isinstance(ends_val, str):
        ends_val = ends_val.strip()
        if ends_val.isdigit():
            val = float(ends_val)
            ts = val / 1000.0 if val > 1e11 else val
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        try:
            val = ends_val.replace("Z", "+00:00")
            return datetime.fromisoformat(val)
        except Exception:
            pass
    return None


# ==================== LỚP GIAO TIẾP VỚI MININGMACHINE API ====================
class TaskClient:
    def __init__(self, acc: dict, proxy_raw: str = None, x_acc: dict = None, all_proxies: list = None):
        self.acc = acc
        self.stt = acc["stt"]
        self.addr = acc["address"]
        self.priv = acc["private_key"]
        self.x_handle = acc["x_handle"]
        self.x_acc = x_acc
        self.proxy_raw = proxy_raw
        self.all_proxies = all_proxies or []

        self.s = requests.Session()
        p = parse_proxy(proxy_raw)
        if p:
            self.s.proxies.update(p)

        self.s.headers.update({
            "User-Agent": UA,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": BASE,
            "Referer": f"{BASE}/app",
        })
        self.token = acc.get("token")
        if self.token:
            self.s.headers["Authorization"] = f"Bearer {self.token}"

    def safe_request(self, method: str, url: str, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", 25)
        for attempt in range(1, 4):
            try:
                if method.lower() == "get":
                    return self.s.get(url, **kwargs)
                return self.s.post(url, **kwargs)
            except Exception as e:
                if attempt == 3:
                    raise e
                time.sleep(2)

    def login_with_wallet(self) -> bool:
        """Đăng nhập lại qua SIWE (EIP-191) để luôn có token mới nhất."""
        try:
            acct = Account.from_key(self.priv)
            r_nonce = self.safe_request("get", f"{API_BASE}/api/auth/wallet/nonce?address={self.addr.lower()}")
            if r_nonce.status_code != 200:
                return False
            data = r_nonce.json()
            message = data.get("message")
            if not message:
                return False

            msghash = encode_defunct(text=message)
            signed = acct.sign_message(msghash)
            sig = signed.signature.hex()
            if not sig.startswith("0x"):
                sig = "0x" + sig

            r_ver = self.safe_request(
                "post",
                f"{API_BASE}/api/auth/wallet/verify",
                json={"address": self.addr.lower(), "signature": sig},
            )
            if r_ver.status_code != 200:
                return False

            token = r_ver.json().get("accessToken")
            if token:
                self.token = token
                self.s.headers["Authorization"] = f"Bearer {self.token}"
                return True
            return False
        except Exception as e:
            log(self.stt, f"Lỗi đăng nhập SIWE: {e}", Colors.RED)
            return False

    def get_profile(self) -> dict:
        try:
            r = self.safe_request("get", f"{API_BASE}/api/mining/me")
            return r.json() if r.status_code == 200 else {}
        except Exception:
            return {}

    def get_tasks(self) -> list:
        try:
            r = self.safe_request("get", f"{API_BASE}/api/tasks")
            if r.status_code == 200:
                data = r.json()
                return data.get("tasks", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            return []
        except Exception:
            return []

    def follow_riggrid_twitter(self) -> tuple[bool, str]:
        """Gọi Twitter API trực tiếp bằng session cookie để follow @RigGrid, tự động xoay proxy nếu gặp lỗi 502/ProxyError."""
        if not self.x_acc:
            return False, "Không có cookie X account"

        proxy_candidates = []
        if self.proxy_raw:
            proxy_candidates.append(self.proxy_raw)
        if self.all_proxies:
            import random
            shuffled = [p for p in self.all_proxies if p != self.proxy_raw]
            random.shuffle(shuffled)
            proxy_candidates.extend(shuffled[:4])  # Thử thêm tối đa 4 proxy khác từ proxy.txt
        proxy_candidates.append(None)  # Thử trực tiếp (direct) nếu tất cả proxy đều lỗi

        last_error = ""
        for p_raw in proxy_candidates:
            s_tw = requests.Session()
            if p_raw:
                p = parse_proxy(p_raw)
                if p:
                    s_tw.proxies.update(p)

            s_tw.headers.update({
                "User-Agent": UA,
                "x-csrf-token": self.x_acc["ct0"],
                "authorization": TWITTER_BEARER,
                "content-type": "application/x-www-form-urlencoded",
                "Origin": "https://x.com",
                "Referer": "https://x.com/",
            })
            for dom in [".x.com", ".twitter.com"]:
                s_tw.cookies.set("auth_token", self.x_acc["auth_token"], domain=dom)
                s_tw.cookies.set("ct0", self.x_acc["ct0"], domain=dom)

            try:
                r = s_tw.post(
                    "https://x.com/i/api/1.1/friendships/create.json",
                    data={"screen_name": "RigGrid"},
                    timeout=15,
                )
                if r.status_code == 200:
                    return True, "Follow thành công"
                # Nếu đã follow rồi hoặc request pending
                if "already" in r.text.lower() or "following" in r.text.lower():
                    return True, "Đã follow trước đó"
                last_error = f"HTTP {r.status_code}: {r.text[:80]}"
                # Lỗi xác thực tài khoản X (401/403) thì đổi proxy không giải quyết được
                if r.status_code in [401, 403]:
                    return False, last_error
            except Exception as e:
                last_error = str(e)
                # Proxy lỗi (502 Bad Gateway, timeout, connect fail) -> Thử proxy tiếp theo
                continue

        return False, last_error

    def execute_tasks(self):
        """Xử lý và claim toàn bộ nhiệm vụ có sẵn."""
        tasks = self.get_tasks()
        if not tasks:
            log(self.stt, "Không có nhiệm vụ nào.", Colors.DIM)
            return

        unclaimed = [t for t in tasks if t.get("status") != "CLAIMED"]
        if not unclaimed:
            log(self.stt, f"Toàn bộ {len(tasks)} nhiệm vụ đã CLAIMED.", Colors.GREEN)
            return

        log(self.stt, f"Tìm thấy {len(unclaimed)} nhiệm vụ chưa hoàn thành. Bắt đầu xử lý...", Colors.MAGENTA)
        claimed_success = 0
        claimed_failed = 0

        for t in unclaimed:
            tid = t.get("id")
            ttype = t.get("type")
            title = t.get("title", tid)
            vtype = t.get("verification", {}).get("type")

            # 1. Kích hoạt Tracking Link nếu có (đặc biệt quan trọng với nhiệm vụ visit/time_on_page)
            action_url = t.get("actionUrl") or t.get("trackingUrl")
            if action_url:
                track_url = f"{API_BASE}{action_url}" if action_url.startswith("/") else action_url
                try:
                    self.safe_request("get", track_url, allow_redirects=True)
                except Exception:
                    pass

            # 2. Start task
            try:
                self.safe_request("post", f"{API_BASE}/api/tasks/{tid}/start")
            except Exception:
                pass

            # 3. Xử lý verify theo từng loại nhiệm vụ
            if ttype == "x_follow" or vtype == "x_follow":
                if self.x_acc:
                    log(self.stt, f"  -> [Follow Twitter] Gọi Twitter API để @{self.x_acc['username']} follow @RigGrid...", Colors.BLUE)
                    ok_fl, msg_fl = self.follow_riggrid_twitter()
                    log(self.stt, f"     Kết quả Twitter follow: {ok_fl} ({msg_fl})", Colors.GREEN if ok_fl else Colors.YELLOW)
                    if ok_fl:
                        time.sleep(2.0)  # Đợi 2s để Twitter đồng bộ trạng thái follow
                else:
                    log(
                        self.stt,
                        f"  -> [CẢNH BÁO] Không có cookie của {self.x_handle} trong {X_FILE}! Nếu chưa follow @RigGrid, task sẽ bị từ chối.",
                        Colors.YELLOW,
                    )
                try:
                    self.safe_request("post", f"{API_BASE}/api/tasks/{tid}/verify", json={})
                except Exception:
                    pass

            elif ttype in ["x_like", "x_retweet", "x_engagement"]:
                log(self.stt, f"  -> [Bypass Like/Repost] Verify body rỗng cho [{title}]...", Colors.DIM)
                try:
                    self.safe_request("post", f"{API_BASE}/api/tasks/{tid}/verify", json={})
                except Exception:
                    pass

            elif vtype == "time_on_page" or ttype == "visit":
                v_cfg = t.get("verification", {}).get("config", {})
                dwell = v_cfg.get("minDwellSeconds", 10)
                wait_time = max(12, dwell + 2)
                log(self.stt, f"  -> [Dwell Timer] Đang chờ {wait_time}s duyệt trang cho [{title}]...", Colors.BLUE)
                time.sleep(wait_time)
                r_vf = None
                try:
                    r_vf = self.safe_request("post", f"{API_BASE}/api/tasks/{tid}/verify", json={})
                except Exception:
                    pass

                # Nếu bị lỗi dwell_time_missing do server yêu cầu retryAfterSeconds
                if r_vf is not None and r_vf.status_code == 409:
                    try:
                        j_err = r_vf.json()
                        retry_after = j_err.get("retryAfterSeconds", 15)
                        log(self.stt, f"  -> Server yêu cầu đợi thêm {retry_after}s cho dwell time...", Colors.YELLOW)
                        time.sleep(retry_after + 2)
                        self.safe_request("post", f"{API_BASE}/api/tasks/{tid}/verify", json={})
                    except Exception:
                        pass

            else:
                try:
                    self.safe_request("post", f"{API_BASE}/api/tasks/{tid}/verify", json={})
                except Exception:
                    pass

            # 4. Claim phần thưởng
            try:
                r_claim = self.safe_request("post", f"{API_BASE}/api/tasks/{tid}/claim")
                if r_claim.status_code == 200:
                    claimed_success += 1
                    log(self.stt, f"  [CLAIM THÀNH CÔNG] [{title}]", Colors.GREEN + Colors.BOLD)
                else:
                    claimed_failed += 1
                    err_detail = r_claim.text[:100]
                    try:
                        err_json = r_claim.json()
                        err_detail = err_json.get("error") or err_json.get("kind") or err_detail
                    except Exception:
                        pass
                    log(self.stt, f"  [CLAIM CHƯA ĐẠT] [{title}]: {err_detail}", Colors.YELLOW)
            except Exception as e:
                claimed_failed += 1
                log(self.stt, f"  [CLAIM EXCEPTION] [{title}]: {e}", Colors.RED)

            time.sleep(1.0)

        log(
            self.stt,
            f"Tổng kết Tasks lượt này: Nhận mới {Colors.GREEN}{claimed_success}{Colors.RESET} | Chưa đạt/Lỗi: {Colors.YELLOW}{claimed_failed}{Colors.RESET}",
            Colors.CYAN,
        )

    def manage_mining(self) -> tuple[float, str]:
        """
        Kiểm tra và kích hoạt máy đào (Start Farm):
          - Nếu chưa đào hoặc đã hết phiên (sessionEndsAt <= now): gọi /api/mining/farm/start
          - Trả về: (remaining_seconds_until_ends, session_ends_at_str)
        """
        profile = self.get_profile()
        farm = profile.get("farm", {})
        status = farm.get("status", "OFFLINE")
        mining_power = farm.get("miningPower", 0)
        session_ends_raw = farm.get("sessionEndsAt")

        ends_dt = parse_session_ends_at(session_ends_raw)
        now_utc = datetime.now(timezone.utc)

        needs_start = False
        if status != "ACTIVE":
            needs_start = True
            log(self.stt, f"Máy đào đang {status} -> Cần kích hoạt phiên đào mới!", Colors.YELLOW)
        elif ends_dt is None:
            needs_start = True
            log(self.stt, "Chưa có sessionEndsAt -> Cần kích hoạt phiên đào mới!", Colors.YELLOW)
        elif now_utc >= ends_dt:
            needs_start = True
            log(self.stt, f"Phiên đào cũ đã kết thúc lúc {session_ends_raw} -> Claim & kích hoạt phiên mới!", Colors.MAGENTA)

        if needs_start:
            log(self.stt, "Đang gửi yêu cầu /api/mining/farm/start...", Colors.CYAN)
            try:
                r_start = self.safe_request("post", f"{API_BASE}/api/mining/farm/start")
                if r_start.status_code == 200:
                    log(self.stt, "KÍCH HOẠT MÁY ĐÀO THÀNH CÔNG!", Colors.GREEN + Colors.BOLD)
                else:
                    log(self.stt, f"Start Farm response: {r_start.status_code} -> {r_start.text[:80]}", Colors.YELLOW)
            except Exception as e:
                log(self.stt, f"Lỗi gọi Start Farm: {e}", Colors.RED)

            # Cập nhật lại thông tin sau khi start
            profile = self.get_profile()
            farm = profile.get("farm", {})
            status = farm.get("status", "ACTIVE")
            mining_power = farm.get("miningPower", mining_power)
            session_ends_raw = farm.get("sessionEndsAt")
            ends_dt = parse_session_ends_at(session_ends_raw)

        # Tính thời gian còn lại
        now_utc = datetime.now(timezone.utc)
        if ends_dt and ends_dt > now_utc:
            remaining_seconds = (ends_dt - now_utc).total_seconds()
            log(
                self.stt,
                f"Máy đào ACTIVE ({mining_power} MP) | Phiên kết thúc sau: {format_seconds(remaining_seconds)} ({session_ends_raw})",
                Colors.GREEN,
            )
            return remaining_seconds, session_ends_raw
        else:
            log(self.stt, f"Máy đào: {status} ({mining_power} MP) | Không xác định được sessionEndsAt", Colors.YELLOW)
            return DEFAULT_CHECK_INTERVAL, "N/A"


# ==================== WORKER XỬ LÝ 1 TÀI KHOẢN ====================
def process_single_account(acc: dict, proxy_raw: str, x_acc: dict, all_proxies: list = None) -> float:
    """Xử lý đăng nhập, hoàn thành nhiệm vụ và kiểm tra/kích hoạt máy đào cho 1 acc."""
    short_addr = f"{acc['address'][:8]}...{acc['address'][-6:]}"
    log(acc["stt"], f"=== Bắt đầu tài khoản [{acc['nickname']}] | Ví: {short_addr} | X: {acc['x_handle']} ===", Colors.CYAN)

    client = TaskClient(acc, proxy_raw=proxy_raw, x_acc=x_acc, all_proxies=all_proxies)

    # 1. Đăng nhập để lấy token mới
    if not client.login_with_wallet():
        log(acc["stt"], "Đăng nhập SIWE thất bại! Sẽ thử lại ở lượt tiếp theo.", Colors.RED)
        return DEFAULT_CHECK_INTERVAL

    # 2. Làm toàn bộ nhiệm vụ
    client.execute_tasks()

    # 3. Kích hoạt & kiểm tra máy đào
    remaining, ends_at_str = client.manage_mining()
    return remaining


# ==================== MAIN SCHEDULER & RUNNER ====================
def run_all_accounts_batch(accounts: list, x_map: dict, proxies: list, threads_count: int) -> float:
    """Chạy toàn bộ danh sách tài khoản theo số luồng đã định, trả về min_remaining_time."""
    log(None, f"Bắt đầu xử lý {len(accounts)} tài khoản với {threads_count} luồng...", Colors.BOLD + Colors.CYAN)
    rem_times = []

    def task_worker(acc, idx):
        uname = acc["x_handle"].lstrip("@").lower()
        x_acc = x_map.get(uname)
        p_raw = proxies[(idx - 1) % len(proxies)] if proxies else None
        return process_single_account(acc, proxy_raw=p_raw, x_acc=x_acc, all_proxies=proxies)

    with ThreadPoolExecutor(max_workers=threads_count) as executor:
        futures = {
            executor.submit(task_worker, acc, i + 1): acc["stt"]
            for i, acc in enumerate(accounts)
        }
        for future in futures:
            try:
                rem = future.result()
                if rem and rem > 0:
                    rem_times.append(rem)
            except Exception as e:
                log(None, f"Lỗi luồng worker: {e}", Colors.RED)

    if rem_times:
        return min(rem_times)
    return DEFAULT_CHECK_INTERVAL


def main():
    init_console()
    ap = argparse.ArgumentParser(
        description="MiningMachine Task Runner & Continuous Auto-Mining Scheduler"
    )
    ap.add_argument("--accounts", "-a", default=ACCOUNTS_FILE, help=f"File danh sách tài khoản (mặc định: {ACCOUNTS_FILE})")
    ap.add_argument("--threads", "-t", type=int, default=DEFAULT_THREADS, help=f"Số luồng xử lý đồng thời (mặc định: {DEFAULT_THREADS})")
    ap.add_argument("--once", action="store_true", help="Chỉ chạy 1 lần rồi thoát (không bật schedule đếm ngược)")
    args = ap.parse_args()

    print(
        f"{Colors.GREEN}{Colors.BOLD}=====================================================\n"
        f"     MINING MACHINE — TASK RUNNER & SCHEDULER\n"
        f"====================================================={Colors.RESET}\n"
        f"  File tài khoản       : {Colors.CYAN}{args.accounts}{Colors.RESET}\n"
        f"  Số luồng đồng thời   : {args.threads}\n"
        f"  Chế độ Schedule      : {'Chạy 1 lần (--once)' if args.once else 'Tự động lặp lại theo phiên đào (24/7)'}\n"
        f"=====================================================\n",
        flush=True,
    )

    x_map = load_x_accounts(X_FILE)
    proxies = load_proxies(PROXIES_FILE)

    round_count = 1
    while True:
        accounts = load_accounts(args.accounts)
        if not accounts:
            print(f"{Colors.RED}[LỖI] Không tìm thấy tài khoản hợp lệ (đã liên kết X) trong file {args.accounts}!{Colors.RESET}")
            print(f"{Colors.YELLOW}Vui lòng chạy 'python miningmachine.py' trước để reg và bind X thành công.{Colors.RESET}")
            break

        print(
            f"\n{Colors.BOLD}{Colors.MAGENTA}=== VÒNG CHẠY #{round_count} (Tổng: {len(accounts)} tài khoản) ==={Colors.RESET}",
            flush=True,
        )

        min_wait = run_all_accounts_batch(
            accounts=accounts,
            x_map=x_map,
            proxies=proxies,
            threads_count=min(args.threads, len(accounts)),
        )

        if args.once:
            print(f"\n{Colors.GREEN}[HOÀN TẤT] Chế độ --once đã kết thúc.{Colors.RESET}")
            break

        # Thêm buffer an toàn để server đóng phiên
        wait_seconds = max(10, int(min_wait + BUFFER_SECONDS))
        next_claim_time = datetime.now().timestamp() + wait_seconds
        next_claim_str = datetime.fromtimestamp(next_claim_time).strftime("%H:%M:%S (%d/%m/%Y)")

        print(
            f"\n{Colors.CYAN}{Colors.BOLD}[SCHEDULE] Đã hoàn thành vòng #{round_count}!\n"
            f"Phiên claim / khai thác tiếp theo vào lúc: {Colors.GREEN}{next_claim_str}{Colors.CYAN}\n"
            f"Thời gian chờ: {Colors.BOLD}{format_seconds(wait_seconds)}{Colors.RESET}\n",
            flush=True,
        )

        # Đếm ngược sinh động
        try:
            start_wait = time.time()
            while True:
                elapsed = time.time() - start_wait
                remaining = wait_seconds - elapsed
                if remaining <= 0:
                    break
                print(
                    f"\r{Colors.YELLOW}[ĐANG CHỜ TIẾP TỤC] Còn lại: {format_seconds(remaining)} | Nhấn Ctrl+C để dừng...{Colors.RESET}   ",
                    end="",
                    flush=True,
                )
                time.sleep(1)
            print()
        except KeyboardInterrupt:
            print(f"\n\n{Colors.YELLOW}[THOÁT] Đã nhận tín hiệu dừng từ người dùng.{Colors.RESET}")
            break

        round_count += 1


if __name__ == "__main__":
    main()
