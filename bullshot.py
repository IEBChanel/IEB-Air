"""
BULLSHOT GEM AUTO-FARM BOT
-------------------------------------------------------------
- Đa luồng (Multi-threading): Tùy chỉnh số luồng trong hàm get_config()
- Giao diện Log tinh giản, tối ưu, tự động bật màu ANSI chuẩn trên Windows CMD
- Auto Quests: Daily, Weekly, One-Time
- Auto Mining: Đào mỏ 10 phút (Greenstone Quarry) & Auto Claim liên tục
- Auto Swap: Tự động đổi toàn bộ quặng thô sang GEMS
- Auto Upgrade: Tự động nâng cấp lấy +100 XP/lần để lên Level mục tiêu
- Auto Stake & Claim: Tự động nạp đá quý vào Staking Pool & thu hoạch lãi GEMS
- Hỗ trợ đa ví (account.txt) & đa proxy (proxy.txt)
"""

import os
import sys
import time
import random
import re
import ctypes
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import requests
from eth_account import Account
from eth_account.messages import encode_defunct


# ==================== HÀM CẤU HÌNH BOT ====================
def get_config():
    """
    Tùy chỉnh cấu hình chạy bot tại đây (tùy cấu hình máy và số lượng acc)
    """
    return {
        # Số luồng chạy cùng lúc (1 = chạy từng acc, 5-20 = chạy đa luồng tùy cấu hình máy & số acc)
        "THREADS": 5,

        # Cấp độ mục tiêu. Khi đạt >= TARGET_LEVEL, bot dừng mua upgrade để tích lũy 100% GEMS
        "TARGET_LEVEL": 15,

        # Tự động nâng cấp để lấy +100 XP mỗi lần (chỉ chạy khi level < TARGET_LEVEL)
        "AUTO_UPGRADE": True,

        # Tự động đổi toàn bộ quặng thô (Iron Ore, Coal, Copper Ore...) sang GEMS
        "AUTO_SWAP_ORES": True,

        # Tự động đem đá quý (Emerald, Sapphire, Ruby, Diamond...) đi Stake lấy lãi APY 18% - 35%
        "AUTO_STAKE_GEMS": True,

        # Tự động thu hoạch lãi GEMS từ các vị thế Staking
        "AUTO_CLAIM_STAKING": True,

        # Thời gian delay thêm khi làm nhiệm vụ (giây)
        "QUEST_DELAY_MIN": 5.0,
        "QUEST_DELAY_MAX": 7.0,

        # Số máy đào tối đa cho phép chạy cùng lúc trên 1 acc khi dư năng lượng (1-5 máy)
        "MAX_MINERS": 4,

        # Mỏ đào ưu tiên mặc định (Greenstone Quarry = 600 giây = 10 phút, tốn 10 Energy)
        "MINING_LOCATION_ID": "greenstone-quarry",

        # Mã Ref mặc định
        "DEFAULT_REF": "0x44aca053",
    }


CONFIG = get_config()


# ==================== KÍCH HOẠT MÀU & LOG TINH GIẢN ====================
def init_console():
    """Kích hoạt UTF-8 và mã màu ANSI cho Windows CMD để không bị lỗi ký tự ←[..."""
    if sys.platform == "win32":
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
                # 0x0004 = ENABLE_VIRTUAL_TERMINAL_PROCESSING
                if kernel32.SetConsoleMode(handle, mode.value | 0x0004):
                    return True
            return False
        except Exception:
            return False
    return True


ANSI_ENABLED = init_console()


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


def log(acc_idx, msg, color=Colors.RESET):
    """Hàm in log ngắn gọn, an toàn đa luồng: [Giờ] [Acc X] Nội dung"""
    now = datetime.now().strftime("%H:%M:%S")
    tag = f"[Acc {acc_idx}]" if acc_idx is not None else "[BOT]"
    with print_lock:
        print(f"{Colors.DIM}[{now}]{Colors.RESET} {Colors.CYAN}{tag:<8}{Colors.RESET} {color}{msg}{Colors.RESET}", flush=True)


def format_rewards(rewards_data) -> str:
    """Rút gọn thông tin phần thưởng mỏ để hiển thị trên 1 dòng"""
    if not rewards_data:
        return "OK"
    if isinstance(rewards_data, str):
        return rewards_data
    if isinstance(rewards_data, list):
        items = []
        for r in rewards_data:
            if isinstance(r, dict):
                qty = r.get("quantity") or r.get("amount") or 1
                name = r.get("name") or r.get("assetId") or "item"
                items.append(f"+{qty} {name}")
            else:
                items.append(str(r))
        return ", ".join(items) if items else "OK"
    if isinstance(rewards_data, dict):
        items = [f"+{v} {k}" for k, v in rewards_data.items() if v]
        return ", ".join(items) if items else "OK"
    return str(rewards_data)


# ==================== BỘ TẠO USERNAME X (TWITTER) NGẪU NHIÊN ====================
# 50 tên phổ biến (Anh, Mỹ & Châu Âu hệ Latin)
FIRST_NAMES = [
    "james", "john", "robert", "michael", "william", "david", "richard", "joseph", "thomas", "charles",
    "liam", "noah", "oliver", "lucas", "mateo", "leo", "hugo", "enzo", "luca", "marco",
    "hans", "erik", "ivan", "milan", "felix", "oscar", "louis", "theo", "max", "arthur",
    "emma", "olivia", "ava", "mia", "sofia", "chloe", "elena", "clara", "nina", "eva",
    "alice", "julia", "laura", "sara", "anna", "marie", "lucia", "paula", "marta", "lena",
]

# 50 họ phổ biến (Anh, Mỹ & Châu Âu hệ Latin)
LAST_NAMES = [
    "smith", "jones", "brown", "davis", "miller", "wilson", "moore", "taylor", "clark", "hall",
    "young", "king", "wright", "lopez", "hill", "scott", "green", "adams", "baker", "nelson",
    "carter", "perry", "rossi", "silva", "costa", "meyer", "weber", "novak", "kowal", "leblanc",
    "dupont", "moreau", "garcia", "gomez", "romano", "conti", "bruno", "ricci", "fischer", "wagner",
    "becker", "schulz", "bauer", "klein", "wolf", "braun", "hofer", "huber", "moser", "marino",
]


def generate_x_handle() -> str:
    """
    Tạo username X ngẫu nhiên giống tool reg X thật:
    50 tên x 50 họ x 3 kiểu ghép + 5 chữ số ngẫu nhiên (750 triệu biến thể)
    """
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
            host, port, user, password = parts[0], parts[1], parts[2], parts[3]
            return f"{protocol}://{user}:{password}@{host}:{port}"
        else:
            user, password, host, port = parts[0], parts[1], parts[2], parts[3]
            return f"{protocol}://{user}:{password}@{host}:{port}"
    elif len(parts) == 2:
        return f"{protocol}://{parts[0]}:{parts[1]}"

    return f"{protocol}://{rest}"


def parse_account(line: str):
    line = line.strip()
    if not line or line.startswith("#"):
        return None

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

    if not pk_candidate:
        last = parts[-1].strip()
        if len(last) in (64, 66):
            pk_candidate = last if last.startswith("0x") else "0x" + last

    if pk_candidate:
        return {"address": expected_addr, "private_key": pk_candidate}
    return None


# ==================== BULLSHOT API CLIENT ====================
class BullshotClient:
    BASE_URL = "https://gemapi.bullshot.io/api"

    RAW_ORES = {
        "iron-ore": 0.25,
        "coal": 0.35,
        "copper-ore": 0.6,
        "sulfur": 1.2,
        "cryo-shard": 3.0,
        "void-dust": 8.0,
        "steel-ingot": 2.5,
        "bronze-wire": 3.5,
    }

    GEMSTONE_POOLS = {
        "emerald": "emerald-pool",
        "sapphire": "sapphire-pool",
        "ruby": "ruby-pool",
        "diamond": "diamond-pool",
        "obsidian": "obsidian-pool",
        "void-gem": "void-gem-pool",
    }

    def __init__(self, acc_idx: int, private_key: str, proxies: list):
        self.acc_idx = acc_idx
        if not private_key.startswith("0x"):
            private_key = "0x" + private_key
        self.private_key = private_key
        self.account = Account.from_key(private_key)
        self.wallet_address = self.account.address.lower()

        self.raw_proxies = proxies or []
        self.proxy_index = (acc_idx - 1) % len(self.raw_proxies) if self.raw_proxies else 0
        self.token = None
        self.session = requests.Session()
        self.user_data = {}

        self.update_session_headers()
        self.set_proxy()

    def update_session_headers(self):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
            "Origin": "https://gem.bullshot.io",
            "Referer": "https://gem.bullshot.io/",
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
            headers["X-Wallet-Address"] = self.wallet_address
        self.session.headers.clear()
        self.session.headers.update(headers)

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

    def request(self, method: str, endpoint: str, json_data: dict = None, retries: int = 4):
        url = f"{self.BASE_URL}{endpoint}"
        for _ in range(retries):
            try:
                response = self.session.request(method, url, json=json_data, timeout=25)
                if response.status_code == 401 and endpoint != "/auth/login":
                    if self.login(silent=True):
                        return self.request(method, endpoint, json_data, retries=retries - 1)
                return response
            except (requests.exceptions.ProxyError, requests.exceptions.Timeout, requests.exceptions.ConnectionError):
                self.rotate_proxy()
                time.sleep(1.5)
            except Exception:
                time.sleep(1.5)
        return None

    def login(self, silent: bool = False) -> bool:
        resp_nonce = self.request("POST", "/auth/nonce", {"walletAddress": self.wallet_address})
        if not resp_nonce or resp_nonce.status_code != 200:
            log(self.acc_idx, "Lỗi lấy nonce đăng nhập", Colors.RED)
            return False

        nonce_data = resp_nonce.json()
        nonce = nonce_data.get("nonce")
        message = nonce_data.get("message") or f"Sign in to Bull GEM on Base: {nonce}"

        signable_msg = encode_defunct(text=message)
        signed_obj = Account.sign_message(signable_msg, self.private_key)
        signature = signed_obj.signature.hex()
        if not signature.startswith("0x"):
            signature = "0x" + signature

        login_payload = {
            "walletAddress": self.wallet_address,
            "signature": signature,
            "message": message,
            "refCode": CONFIG["DEFAULT_REF"],
        }
        resp_login = self.request("POST", "/auth/login", login_payload)
        if not resp_login or resp_login.status_code != 200:
            log(self.acc_idx, "Đăng nhập thất bại", Colors.RED)
            return False

        data = resp_login.json()
        self.token = data.get("token")
        self.user_data = data.get("user") or {}
        self.update_session_headers()

        if not silent:
            gems = self.user_data.get("gems", 0)
            level = self.user_data.get("level", 1)
            xp = self.user_data.get("xp", 0)
            energy = self.user_data.get("energy", 0)
            energy_cap = self.user_data.get("energyCapacity", 100)
            short_wallet = f"{self.wallet_address[:6]}..{self.wallet_address[-4:]}"
            log(
                self.acc_idx,
                f"Login ({short_wallet}) | Lv {level} ({xp} XP) | {Colors.GREEN}{gems} GEMS{Colors.RESET} | NL: {energy}/{energy_cap}",
            )
        return True

    def refresh_user(self):
        resp = self.request("GET", "/user/me")
        if resp and resp.status_code == 200:
            self.user_data = resp.json()
        return self.user_data

    def ensure_twitter_linked(self):
        twitter_handle = self.user_data.get("twitterHandle")
        if not twitter_handle:
            for _ in range(3):
                auto_handle = generate_x_handle()
                resp = self.request("POST", "/user/link-twitter", {"twitterHandle": auto_handle})
                if resp and resp.status_code == 200:
                    self.user_data["twitterHandle"] = auto_handle
                    log(self.acc_idx, f"Liên kết X: @{auto_handle}", Colors.GREEN)
                    break

    def run_quests(self):
        resp = self.request("GET", "/quests")
        if not resp or resp.status_code != 200:
            return

        quests_data = resp.json()
        quest_list = (quests_data.get("daily") or []) + (quests_data.get("weekly") or []) + (quests_data.get("oneTime") or [])
        pending_quests = [q for q in quest_list if q.get("status") != "claimed"]

        if not pending_quests:
            return

        claimed_count = 0
        total_gems = 0
        total_xp = 0

        for q in pending_quests:
            qid = q.get("id")
            title = q.get("title", qid)
            status = q.get("status")
            reward_gems = q.get("rewardGems", 0)
            reward_xp = q.get("rewardXp", 0)
            action_type = q.get("actionType")
            delay_seconds = q.get("delaySeconds", 10)

            if status not in ("started", "ready"):
                r_start = self.request("POST", "/quests/start", {"questId": qid})
                if not r_start or r_start.status_code != 200:
                    continue
                delay_seconds = r_start.json().get("delaySeconds", delay_seconds)

            wait_time = max(random.uniform(CONFIG["QUEST_DELAY_MIN"], CONFIG["QUEST_DELAY_MAX"]), float(delay_seconds))
            time.sleep(wait_time)

            tweet_url = ""
            if action_type == "verify_tweet" or qid in ("tw_weekly_post", "tw_weekly_qrt", "tw_start_mining_tweet"):
                handle = self.user_data.get("twitterHandle") or generate_x_handle()
                fake_status_id = random.randint(1885000000000000000, 1889999999999999999)
                tweet_url = f"https://x.com/{handle}/status/{fake_status_id}"

            r_claim = self.request("POST", "/quests/claim", {"questId": qid, "tweetUrl": tweet_url})
            if r_claim and r_claim.status_code == 200:
                claimed_count += 1
                total_gems += reward_gems
                total_xp += reward_xp
                log(
                    self.acc_idx,
                    f"Nhiệm vụ: {title} -> {Colors.GREEN}+{reward_gems} GEMS, +{reward_xp} XP{Colors.RESET}",
                )

    def get_mining_locations(self) -> list:
        """Lấy danh sách các mỏ đào từ server (kèm mỏ mặc định dự phòng)"""
        default_loc = {
            "id": CONFIG["MINING_LOCATION_ID"],
            "name": "Greenstone Quarry",
            "energyCost": 10,
            "requiredPower": 10,
            "requiredLevel": 1,
            "durationSeconds": 600,
            "unlocked": True,
        }
        resp = self.request("GET", "/mining/locations")
        if not resp or resp.status_code != 200:
            return [default_loc]

        data = resp.json()
        raw_list = data if isinstance(data, list) else (data.get("locations") or [])
        if not raw_list:
            return [default_loc]

        locations = []
        for loc in raw_list:
            if not isinstance(loc, dict):
                continue
            loc_id = loc.get("id") or loc.get("locationId")
            if not loc_id:
                continue
            locations.append({
                "id": loc_id,
                "name": loc.get("name") or loc_id,
                "energyCost": int(loc.get("energyCost") or loc.get("energy") or loc.get("cost") or 10),
                "requiredPower": int(loc.get("requiredPower") or loc.get("minPower") or loc.get("powerRequired") or loc.get("reqPower") or 10),
                "requiredLevel": int(loc.get("requiredLevel") or loc.get("minLevel") or loc.get("levelRequired") or 1),
                "durationSeconds": int(loc.get("durationSeconds") or loc.get("duration") or 600),
                "unlocked": bool(loc.get("unlocked", loc.get("isUnlocked", True))),
            })

        locations.sort(key=lambda x: x["energyCost"])
        return locations if locations else [default_loc]

    def run_mining(self) -> int:
        resp_pos = self.request("GET", "/mining/positions")
        if not resp_pos or resp_pos.status_code != 200:
            return 600

        positions = resp_pos.json() or []
        active_positions = []

        # 1. Claim toàn bộ các máy đào đã hoàn thành
        claimed_any = False
        for pos in positions:
            pos_id = pos.get("id")
            status = pos.get("status")
            remaining = pos.get("remainingSeconds", 0)
            loc_name = pos.get("locationName") or pos.get("locationId")

            if status in ("ready", "completed") or remaining <= 0:
                resp_claim = self.request("POST", f"/mining/positions/{pos_id}/claim")
                if resp_claim and resp_claim.status_code == 200:
                    claimed_any = True
                    claim_data = resp_claim.json()
                    rw_str = format_rewards(claim_data.get("rewards") or claim_data.get("expectedRewards"))
                    log(self.acc_idx, f"Claim mỏ: {loc_name} -> {Colors.GREEN}{rw_str}{Colors.RESET}")
            elif status == "active":
                active_positions.append(pos)

        # Nếu vừa thu hoạch mỏ, tự động Swap quặng & Nâng cấp luôn để có thêm Power/NL trước khi thả máy mới
        if claimed_any:
            self.run_swap_ores()
            self.run_upgrades()

        max_miners = max(1, int(CONFIG.get("MAX_MINERS", 4)))

        # 2. Nếu chưa đạt số máy tối đa, kiểm tra NL và thả thêm máy đào
        if len(active_positions) < max_miners:
            self.refresh_user()
            energy = int(self.user_data.get("energy", 0))
            mining_power = int(self.user_data.get("miningPower") or self.user_data.get("power") or 10)
            user_level = int(self.user_data.get("level", 1))

            locations = self.get_mining_locations()
            min_cost = min((loc["energyCost"] for loc in locations), default=10)

            if energy >= min_cost:
                active_loc_ids = {p.get("locationId") for p in active_positions if p.get("locationId")}
                blocked_loc_ids = set()
                deployed_summary = []

                while len(active_positions) < max_miners and energy >= min_cost:
                    # Tìm danh sách mỏ đủ điều kiện (ưu tiên mỏ chưa có máy đang chạy trước)
                    eligible_unoccupied = [
                        loc for loc in locations
                        if loc["id"] not in blocked_loc_ids
                        and loc["id"] not in active_loc_ids
                        and loc["unlocked"]
                        and user_level >= loc["requiredLevel"]
                        and mining_power >= loc["requiredPower"]
                        and energy >= loc["energyCost"]
                    ]
                    eligible_any = [
                        loc for loc in locations
                        if loc["id"] not in blocked_loc_ids
                        and loc["unlocked"]
                        and user_level >= loc["requiredLevel"]
                        and mining_power >= loc["requiredPower"]
                        and energy >= loc["energyCost"]
                    ]

                    target_loc = (eligible_unoccupied or eligible_any or [None])[0]
                    if not target_loc:
                        break

                    loc_id = target_loc["id"]
                    resp_deploy = self.request("POST", "/mining/positions", {"locationId": loc_id})
                    if resp_deploy and resp_deploy.status_code == 200:
                        dep_data = resp_deploy.json()
                        pos_info = dep_data.get("position") or {}
                        dur = int(pos_info.get("durationSeconds") or target_loc["durationSeconds"] or 600)
                        user_info = dep_data.get("user") or {}
                        energy = int(user_info.get("energy", energy - target_loc["energyCost"]))

                        active_positions.append({
                            "locationId": loc_id,
                            "locationName": target_loc["name"],
                            "remainingSeconds": dur,
                        })
                        active_loc_ids.add(loc_id)
                        deployed_summary.append(f"{target_loc['name']} ({dur // 60}p)")
                    else:
                        # Nếu mỏ này không cho thả thêm hoặc đã đạt giới hạn vị trí
                        blocked_loc_ids.add(loc_id)
                        err_text = (resp_deploy.text.lower() if resp_deploy and resp_deploy.text else "")
                        if "max" in err_text or "limit" in err_text:
                            break

                if deployed_summary:
                    log(
                        self.acc_idx,
                        f"Đào {len(deployed_summary)} máy: {', '.join(deployed_summary)} (NL còn: {energy})",
                        Colors.YELLOW,
                    )

        # 3. Trả về thời gian chờ của máy đào sẽ chín sớm nhất
        if active_positions:
            min_rem = min(int(p.get("remainingSeconds", 600)) for p in active_positions)
            if not locals().get("deployed_summary"):
                log(
                    self.acc_idx,
                    f"Đang chạy {len(active_positions)} máy đào (xong sớm nhất sau {min_rem // 60}p {min_rem % 60}s)",
                    Colors.YELLOW,
                )
            return max(5, min_rem)

        energy = int(self.user_data.get("energy", 0))
        log(self.acc_idx, f"Chờ hồi năng lượng đào (NL: {energy})", Colors.YELLOW)
        return 300

    def run_swap_ores(self):
        if not CONFIG["AUTO_SWAP_ORES"]:
            return

        resp_inv = self.request("GET", "/user/inventory")
        if not resp_inv or resp_inv.status_code != 200:
            return

        inventory = resp_inv.json() or []
        total_swapped_gems = 0
        swapped_items = []

        for item in inventory:
            asset_id = item.get("assetId")
            quantity = item.get("quantity", 0)

            if asset_id in self.RAW_ORES and quantity > 0:
                rate = self.RAW_ORES[asset_id]
                if quantity * rate >= 0.5:
                    r_swap = self.request(
                        "POST",
                        "/trade/swap",
                        {"fromAssetId": asset_id, "toAssetId": "GEMS", "amount": quantity},
                    )
                    if r_swap and r_swap.status_code == 200:
                        rcv = r_swap.json().get("received", 0)
                        total_swapped_gems += rcv
                        swapped_items.append(f"{quantity} {item.get('name', asset_id)}")

        if swapped_items:
            log(
                self.acc_idx,
                f"Swap quặng: {', '.join(swapped_items)} -> {Colors.GREEN}+{total_swapped_gems:.2f} GEMS{Colors.RESET}",
            )

    def run_upgrades(self):
        if not CONFIG["AUTO_UPGRADE"]:
            return

        self.refresh_user()
        current_level = self.user_data.get("level", 1)
        target_level = CONFIG["TARGET_LEVEL"]

        if current_level >= target_level:
            return

        resp_upg = self.request("GET", "/upgrades")
        if not resp_upg or resp_upg.status_code != 200:
            return

        upgrades = resp_upg.json() or []
        priority_order = ["upg-power-1", "upg-energy-1", "upg-speed-1"]

        for upg_id in priority_order:
            self.refresh_user()
            if self.user_data.get("level", 1) >= target_level:
                break

            current_gems = self.user_data.get("gems", 0)
            target_upg = next((u for u in upgrades if u.get("id") == upg_id), None)
            if not target_upg:
                continue

            cost = target_upg.get("cost", 999999)
            if current_gems >= cost:
                resp_buy = self.request("POST", f"/upgrades/{upg_id}")
                if resp_buy and resp_buy.status_code == 200:
                    new_user = resp_buy.json().get("user") or {}
                    new_lvl = new_user.get("level", current_level)
                    new_xp = new_user.get("xp", 0)
                    log(
                        self.acc_idx,
                        f"Nâng cấp: {target_upg.get('name')} (-{cost} GEMS) -> Lv {new_lvl} ({new_xp} XP)",
                        Colors.MAGENTA,
                    )
                else:
                    break

    def run_staking(self):
        if CONFIG["AUTO_CLAIM_STAKING"]:
            resp_stk = self.request("GET", "/staking/positions")
            if resp_stk and resp_stk.status_code == 200:
                stk_positions = resp_stk.json() or []
                claimed_stake = 0
                for sp in stk_positions:
                    pos_id = sp.get("id")
                    accrued = sp.get("accruedRewards", 0)
                    if accrued > 0:
                        r_clm = self.request("POST", f"/staking/positions/{pos_id}/claim")
                        if r_clm and r_clm.status_code == 200:
                            claimed_stake += accrued
                if claimed_stake > 0:
                    log(self.acc_idx, f"Claim lãi Stake: {Colors.GREEN}+{claimed_stake} GEMS{Colors.RESET}")

        if CONFIG["AUTO_STAKE_GEMS"]:
            resp_inv = self.request("GET", "/user/inventory")
            if not resp_inv or resp_inv.status_code != 200:
                return

            inventory = resp_inv.json() or []
            staked_list = []
            for item in inventory:
                asset_id = item.get("assetId")
                qty = item.get("quantity", 0)

                if asset_id in self.GEMSTONE_POOLS and qty > 0:
                    pool_id = self.GEMSTONE_POOLS[asset_id]
                    r_stk = self.request("POST", "/staking/positions", {"poolId": pool_id, "amount": qty})
                    if r_stk and r_stk.status_code == 200:
                        staked_list.append(f"{qty} {item.get('name', asset_id)}")
            if staked_list:
                log(self.acc_idx, f"Stake đá quý: {', '.join(staked_list)}", Colors.GREEN)

    def check_referrals(self):
        resp = self.request("GET", "/referral/stats")
        if resp and resp.status_code == 200:
            stats = resp.json()
            pending = stats.get("pendingGems", 0)
            if pending > 0:
                r_c = self.request("POST", "/referral/claim")
                if r_c and r_c.status_code == 200:
                    log(self.acc_idx, f"Claim Ref: {Colors.GREEN}+{pending} GEMS{Colors.RESET}")


# ==================== XỬ LÝ TỪNG ACC (WORKER) ====================
def process_account(idx: int, acc: dict, proxies: list) -> float:
    """
    Xử lý trọn vẹn 1 tài khoản rồi thoát ngay để luồng nhảy sang acc tiếp theo (6, 7, 8...).
    Trả về mốc thời gian (timestamp) mà mỏ của acc này sẽ đào xong.
    """
    client = BullshotClient(acc_idx=idx, private_key=acc["private_key"], proxies=proxies)

    if not client.login():
        return time.time() + 600

    client.ensure_twitter_linked()

    try:
        client.run_quests()
    except Exception as e:
        log(idx, f"Lỗi nhiệm vụ: {e}", Colors.RED)

    try:
        client.run_swap_ores()
    except Exception as e:
        log(idx, f"Lỗi swap: {e}", Colors.RED)

    try:
        client.run_upgrades()
    except Exception as e:
        log(idx, f"Lỗi nâng cấp: {e}", Colors.RED)

    wait_time = 600
    try:
        wait_time = client.run_mining()
    except Exception as e:
        log(idx, f"Lỗi đào mỏ: {e}", Colors.RED)

    try:
        client.run_staking()
    except Exception as e:
        log(idx, f"Lỗi stake: {e}", Colors.RED)

    try:
        client.check_referrals()
    except Exception:
        pass

    user = client.refresh_user()
    lvl = user.get("level", 1)
    xp = user.get("xp", 0)
    gems = user.get("gems", 0)
    energy = user.get("energy", 0)
    energy_cap = user.get("energyCapacity", 100)
    log(idx, f"Xong | Lv {lvl} ({xp} XP) | {Colors.GREEN}{gems} GEMS{Colors.RESET} | NL: {energy}/{energy_cap}")

    return time.time() + wait_time


# ==================== ĐỌC DỮ LIỆU ĐẦU VÀO ====================
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


def main():
    global CONFIG
    CONFIG = get_config()

    accounts = load_accounts("account.txt")
    proxies = load_proxies("proxy.txt")

    if not accounts:
        log(None, "Không tìm thấy tài khoản trong account.txt!", Colors.RED)
        return

    threads = max(1, min(int(CONFIG.get("THREADS", 5)), len(accounts)))
    print(
        f"{Colors.GREEN}{Colors.BOLD}=== BULLSHOT AUTO BOT | Acc: {len(accounts)} | Proxy: {len(proxies)} | Luồng: {threads} | Target Lv: {CONFIG['TARGET_LEVEL']} ==={Colors.RESET}",
        flush=True,
    )

    cycle = 1
    while True:
        log(None, f"--- Bắt đầu chu kỳ #{cycle} ---", Colors.BOLD)
        earliest_ready_at = time.time() + 600

        if threads == 1:
            for idx, acc in enumerate(accounts, 1):
                ready_at = process_account(idx, acc, proxies)
                if ready_at < earliest_ready_at:
                    earliest_ready_at = ready_at
        else:
            with ThreadPoolExecutor(max_workers=threads) as executor:
                futures = {
                    executor.submit(process_account, idx, acc, proxies): idx
                    for idx, acc in enumerate(accounts, 1)
                }
                for future in as_completed(futures):
                    try:
                        ready_at = future.result()
                        if ready_at and ready_at < earliest_ready_at:
                            earliest_ready_at = ready_at
                    except Exception as e:
                        idx = futures[future]
                        log(idx, f"Lỗi luồng: {e}", Colors.RED)

        cycle += 1
        remaining_wait = int(earliest_ready_at - time.time()) + 5
        if remaining_wait <= 5:
            log(None, "Mỏ của các acc đầu đã đào xong! Chuyển sang chu kỳ tiếp theo ngay...", Colors.CYAN)
            continue

        log(None, f"Đã chạy xong toàn bộ {len(accounts)} acc. Nghỉ {remaining_wait // 60}p {remaining_wait % 60}s chờ mỏ chín...", Colors.CYAN)

        for s in range(remaining_wait, 0, -10):
            sys.stdout.write(f"\r{Colors.DIM}[Đếm ngược] Chờ {s // 60}p {s % 60}s...{Colors.RESET}   ")
            sys.stdout.flush()
            time.sleep(min(10, s))
        sys.stdout.write("\r" + " " * 50 + "\r")
        sys.stdout.flush()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Đã dừng bot.{Colors.RESET}")
