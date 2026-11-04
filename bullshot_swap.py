"""
swap.py — Tự động Swap GEMS <-> Iron Ore cày XP lên Level 20 cho toàn bộ ví Bullshot
Cơ chế:
  - 10 GEMS -> 40 Iron Ore (+25 XP)
  - 40 Iron Ore -> 10 GEMS (+25 XP)
  - Tổng mỗi chu kỳ: +50 XP, bảo toàn 100% số GEMS (không hao hụt)
  - Lặp lại liên tục cho đến khi tài khoản đạt Level 20 (hoặc TARGET_LEVEL cấu hình) thì tự động dừng.

Cách sử dụng:
  python swap.py                      # Chạy toàn bộ ví trong account.txt (25 luồng, đích Lv 20)
  python swap.py --threads 20         # Chạy với 20 luồng đồng thời
  python swap.py --target-level 20    # Cấu hình cấp độ mục tiêu
  python swap.py 1-50                 # Chạy dải ví từ 1 đến 50
  python swap.py 1,5,10,25            # Chạy các ví chỉ định
"""
import argparse
import os
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from eth_account import Account

from bullshot import (
    init_console,
    load_accounts,
    load_proxies,
    REF_MANAGER,
    REFCODE_FILE,
    BullshotClient,
    log,
    Colors,
)

init_console()

DEFAULT_THREADS = 25
DEFAULT_TARGET_LEVEL = 20
DEFAULT_SWAP_AMOUNT = 10  # 10 GEMS <-> 40 Iron Ore

stats_lock = threading.Lock()
stats = {
    "already_target": 0,
    "newly_reached": 0,
    "insufficient_gems": 0,
    "login_failed": 0,
    "total_cycles": 0,
    "total_xp_gained": 0,
}


def clean_leftover_iron_ore(client: BullshotClient) -> float:
    """Kiểm tra và đổi sạch quặng sắt tồn đọng trong rương về GEMS"""
    try:
        resp_inv = client.request("GET", "/user/inventory", retries=2)
        if not resp_inv or resp_inv.status_code != 200:
            return 0.0

        inventory = resp_inv.json() or []
        for item in inventory:
            if item.get("assetId") == "iron-ore" and item.get("quantity", 0) > 0:
                qty = item["quantity"]
                r_swap = client.request(
                    "POST",
                    "/trade/swap",
                    {"fromAssetId": "iron-ore", "toAssetId": "GEMS", "amount": qty},
                    retries=3,
                )
                if r_swap and r_swap.status_code == 200:
                    rcv = r_swap.json().get("received", 0)
                    log(client.acc_idx, f"Đã thu hồi {qty} Iron Ore dở dang -> {Colors.GREEN}+{rcv} GEMS{Colors.RESET}")
                    client.refresh_user()
                    return float(rcv)
    except Exception as e:
        log(client.acc_idx, f"Lỗi dọn quặng tồn đọng: {e}", Colors.YELLOW)
    return 0.0


def run_swap_to_target(
    idx: int,
    acc_data: dict,
    proxies: list,
    target_level: int = DEFAULT_TARGET_LEVEL,
    swap_gems: float = DEFAULT_SWAP_AMOUNT,
) -> bool:
    pk = acc_data["private_key"]
    client = BullshotClient(idx, pk, proxies)

    if not client.login(silent=True):
        with stats_lock:
            stats["login_failed"] += 1
        log(idx, "Đăng nhập thất bại", Colors.RED)
        return False

    client.refresh_user()
    current_level = int(client.user_data.get("level", 1))
    current_xp = int(client.user_data.get("xp", 0))
    current_gems = float(client.user_data.get("gems", 0))

    if current_level >= target_level:
        with stats_lock:
            stats["already_target"] += 1
        log(
            idx,
            f"Đã đạt mục tiêu từ trước: {Colors.GREEN}Lv {current_level}{Colors.RESET} ({current_xp} XP | {current_gems:.2f} GEMS)",
            Colors.DIM,
        )
        return True

    # 1. Thu hồi sạch quặng sắt dở dang nếu có từ lần chạy trước
    clean_leftover_iron_ore(client)
    client.refresh_user()
    current_gems = float(client.user_data.get("gems", 0))

    # Nếu ví có ít hơn số GEMS tiêu chuẩn (10), linh hoạt dùng số GEMS hiện có (tối thiểu 1)
    use_amount = swap_gems
    if current_gems < use_amount:
        # Thử đổi các loại quặng thô khác nếu có sang GEMS
        try:
            client.run_swap_ores()
            client.refresh_user()
            current_gems = float(client.user_data.get("gems", 0))
        except Exception:
            pass

        if current_gems >= 1.0:
            use_amount = float(int(current_gems))
        else:
            with stats_lock:
                stats["insufficient_gems"] += 1
            log(idx, f"Không đủ GEMS để swap (Hiện có: {current_gems:.2f} GEMS, cần >= 1 GEMS)", Colors.RED)
            return False

    expected_ore = use_amount * 4  # Tỷ lệ: 1 GEMS = 4 Iron Ore
    log(
        idx,
        f"Bắt đầu cày Level: {Colors.YELLOW}Lv {current_level}{Colors.RESET} ({current_xp} XP) -> Mục tiêu {Colors.GREEN}Lv {target_level}{Colors.RESET} | Swap {use_amount} GEMS <-> {expected_ore} Iron Ore",
        Colors.CYAN,
    )

    cycles = 0
    xp_gained = 0
    last_reported_cycle = 0

    try:
        while current_level < target_level:
            # Bước 1: GEMS -> Iron Ore (+25 XP)
            r1 = client.request(
                "POST",
                "/trade/swap",
                {"fromAssetId": "GEMS", "toAssetId": "iron-ore", "amount": use_amount},
                retries=4,
            )
            if not r1 or r1.status_code != 200:
                time.sleep(1.0)
                continue

            j1 = r1.json() or {}
            ore_received = j1.get("received") or expected_ore
            user1 = j1.get("user") or {}
            if user1:
                client.user_data = user1
                current_level = int(user1.get("level", current_level))
                current_xp = int(user1.get("xp", current_xp))

            # Bước 2: Iron Ore -> GEMS (+25 XP)
            r2 = client.request(
                "POST",
                "/trade/swap",
                {"fromAssetId": "iron-ore", "toAssetId": "GEMS", "amount": ore_received},
                retries=4,
            )
            if not r2 or r2.status_code != 200:
                # Nếu bước 2 bị gián đoạn mạng, thử lại để đảm bảo thu hồi đủ GEMS
                time.sleep(1.0)
                clean_leftover_iron_ore(client)
                continue

            j2 = r2.json() or {}
            user2 = j2.get("user") or {}
            if user2:
                client.user_data = user2
                current_level = int(user2.get("level", current_level))
                current_xp = int(user2.get("xp", current_xp))
                current_gems = float(user2.get("gems", current_gems))

            cycles += 1
            xp_gained += 50

            # Báo cáo tiến độ mỗi 20 chu kỳ
            if cycles - last_reported_cycle >= 20:
                last_reported_cycle = cycles
                log(
                    idx,
                    f"Tiến độ: Lv {current_level} ({current_xp} XP) | Chu kỳ: {cycles} (+{xp_gained} XP) | GEMS: {current_gems:.2f}",
                    Colors.DIM,
                )

            # Đã đạt cấp độ mục tiêu
            if current_level >= target_level:
                break

    finally:
        # Luôn đảm bảo quặng dở dang được trả lại 100% thành GEMS
        clean_leftover_iron_ore(client)

    with stats_lock:
        stats["newly_reached"] += 1
        stats["total_cycles"] += cycles
        stats["total_xp_gained"] += xp_gained

    log(
        idx,
        f"{Colors.GREEN}{Colors.BOLD}ĐẠT LEVEL {current_level}{Colors.RESET} ({current_xp} XP) sau {cycles} chu kỳ swap (+{xp_gained} XP) | GEMS: {current_gems:.2f}",
        Colors.GREEN,
    )
    return True


def parse_target_indices(arg: str, total_accounts: int) -> list:
    """Hỗ trợ cú pháp 1-50 hoặc 1,2,5 hoặc 10"""
    indices = set()
    parts = arg.split(",")
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if "-" in p:
            sub = p.split("-")
            if len(sub) == 2 and sub[0].isdigit() and sub[1].isdigit():
                start, end = int(sub[0]), int(sub[1])
                for i in range(max(1, start), min(total_accounts, end) + 1):
                    indices.add(i)
        elif p.isdigit():
            val = int(p)
            if 1 <= val <= total_accounts:
                indices.add(val)
    return sorted(indices)


def main():
    ap = argparse.ArgumentParser(description="Bullshot XP Farming via Swap Loop (Target Level 20)")
    ap.add_argument("wallets", nargs="?", default=None, help="Chỉ định ví: VD 1-50 hoặc 1,5,10 (Mặc định: toàn bộ)")
    ap.add_argument("--threads", type=int, default=DEFAULT_THREADS, help=f"Số luồng chạy đồng thời (mặc định: {DEFAULT_THREADS})")
    ap.add_argument("--target-level", type=int, default=DEFAULT_TARGET_LEVEL, help=f"Cấp độ mục tiêu cần đạt (mặc định: {DEFAULT_TARGET_LEVEL})")
    ap.add_argument("--amount", type=float, default=DEFAULT_SWAP_AMOUNT, help=f"Số GEMS swap mỗi lần (mặc định: {DEFAULT_SWAP_AMOUNT})")
    args = ap.parse_args()

    accounts = load_accounts("account.txt")
    proxies = load_proxies("proxy.txt")

    if not accounts:
        log(None, "Không tìm thấy tài khoản trong account.txt!", Colors.RED)
        return

    # Khởi tạo trước Round-Robin ref code
    REF_MANAGER.init_from_file(REFCODE_FILE)
    for acc in accounts:
        w = Account.from_key(acc["private_key"]).address.lower()
        REF_MANAGER.get_login_ref_code(w)

    if args.wallets:
        target_indices = parse_target_indices(args.wallets, len(accounts))
        work_items = [(idx, accounts[idx - 1]) for idx in target_indices]
    else:
        work_items = [(idx, acc) for idx, acc in enumerate(accounts, 1)]

    print(
        f"{Colors.GREEN}{Colors.BOLD}=== BULLSHOT AUTO SWAP EXP FARMER | Số ví: {len(work_items)}/{len(accounts)} | "
        f"Luồng: {args.threads} | Mục tiêu: Lv {args.target_level} | Swap: {args.amount} GEMS <-> Iron Ore ==={Colors.RESET}",
        flush=True,
    )

    start_time = time.time()
    try:
        with ThreadPoolExecutor(max_workers=args.threads) as executor:
            futures = {
                executor.submit(
                    run_swap_to_target,
                    idx,
                    acc,
                    proxies,
                    args.target_level,
                    args.amount,
                ): idx
                for idx, acc in work_items
            }
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    future.result()
                except Exception as e:
                    log(idx, f"Lỗi ngoại lệ: {e}", Colors.RED)
    except KeyboardInterrupt:
        print(f"\n{Colors.RED}Đã tạm dừng theo lệnh người dùng. Đang kiểm tra an toàn ví...{Colors.RESET}")

    elapsed = time.time() - start_time
    print(
        f"\n{Colors.GREEN}{Colors.BOLD}=== TỔNG KẾT TIẾN TRÌNH SWAP LÊN LV {args.target_level} ==={Colors.RESET}\n"
        f"- Đã đạt Lv {args.target_level} từ trước  : {stats['already_target']} ví\n"
        f"- Mới cày đạt Lv {args.target_level}      : {stats['newly_reached']} ví\n"
        f"- Không đủ GEMS (< 1 GEMS) : {stats['insufficient_gems']} ví\n"
        f"- Đăng nhập thất bại       : {stats['login_failed']} ví\n"
        f"- Tổng số chu kỳ swap      : {stats['total_cycles']} chu kỳ\n"
        f"- Tổng XP thu được         : +{stats['total_xp_gained']} XP\n"
        f"- Thời gian thực hiện      : {elapsed:.1f} giây",
        flush=True,
    )


if __name__ == "__main__":
    main()

