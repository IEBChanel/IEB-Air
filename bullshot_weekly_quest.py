import sys
import time
import random
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
    generate_x_handle,
    log,
    Colors,
)

init_console()

THREADS = 25
stats_lock = threading.Lock()
stats = {
    "already_done": 0,
    "newly_completed": 0,
    "still_missed": 0,
    "login_failed": 0,
}


def run_weekly_only(idx: int, acc_data: dict, proxies: list):
    pk = acc_data["private_key"]
    client = BullshotClient(idx, pk, proxies)

    if not client.login(silent=True):
        with stats_lock:
            stats["login_failed"] += 1
        log(idx, "Đăng nhập thất bại", Colors.RED)
        return False

    resp = client.request("GET", "/quests")
    if not resp or resp.status_code != 200:
        log(idx, "Lỗi lấy danh sách nhiệm vụ /quests", Colors.RED)
        with stats_lock:
            stats["still_missed"] += 1
        return False

    weekly = (resp.json() or {}).get("weekly") or []
    pending = [q for q in weekly if q.get("status") != "claimed"]

    if not pending:
        with stats_lock:
            stats["already_done"] += 1
        log(idx, f"Đã xong đủ 3/3 nhiệm vụ tuần trước đó (Lv.{client.user_data.get('level', 1)})", Colors.DIM)
        return True

    # Đảm bảo đã liên kết X và Socials Anti-Sybil trước khi làm nhiệm vụ
    client.ensure_twitter_linked()
    try:
        client.ensure_socials_linked()
    except Exception:
        pass

    # Thử tối đa 3 vòng quét lại nếu còn sót nhiệm vụ tuần chưa claimed
    claimed_titles = []
    for round_try in range(3):
        if round_try > 0:
            r_check = client.request("GET", "/quests")
            if r_check and r_check.status_code == 200:
                weekly = (r_check.json() or {}).get("weekly") or []
                pending = [q for q in weekly if q.get("status") != "claimed"]
            if not pending:
                break

        for q in pending:
            qid = q.get("id")
            title = q.get("title", qid)
            status = q.get("status")
            reward_gems = q.get("rewardGems", 0)
            reward_xp = q.get("rewardXp", 0)
            action_type = q.get("actionType")
            delay_seconds = q.get("delaySeconds", 10)
            seconds_left = q.get("secondsLeft", delay_seconds)

            if status not in ("started", "ready"):
                r_start = client.request("POST", "/quests/start", {"questId": qid})
                if not r_start or r_start.status_code != 200:
                    continue
                delay_seconds = r_start.json().get("delaySeconds", delay_seconds)
                time.sleep(float(delay_seconds) + 1.5)
            elif status == "started" and seconds_left > 0:
                time.sleep(float(seconds_left) + 1.5)
            else:
                time.sleep(0.5)

            is_tweet_quest = action_type == "verify_tweet" or qid in ("tw_weekly_post", "tw_weekly_qrt")
            max_attempts = 5 if is_tweet_quest else 2

            for attempt in range(max_attempts):
                tweet_url = ""
                if is_tweet_quest:
                    handle = client.user_data.get("twitterHandle") or generate_x_handle()
                    fake_status_id = random.randint(1885000000000000000, 1889999999999999999)
                    tweet_url = f"https://x.com/{handle}/status/{fake_status_id}"

                r_claim = client.request("POST", "/quests/claim", {"questId": qid, "tweetUrl": tweet_url})
                if r_claim is not None and r_claim.status_code == 200:
                    claimed_titles.append(f"{title} (+{reward_gems} GEMS)")
                    break
                time.sleep(2.0)

    # Kiểm tra chốt cuối cùng xem đã đủ 3/3 claimed chưa
    r_final = client.request("GET", "/quests")
    still_pending = []
    if r_final and r_final.status_code == 200:
        w_final = (r_final.json() or {}).get("weekly") or []
        still_pending = [q.get("id") for q in w_final if q.get("status") != "claimed"]

    if not still_pending:
        with stats_lock:
            stats["newly_completed"] += 1
        log(
            idx,
            f"Hoàn tất 3/3 Weekly Quest: {Colors.GREEN}{', '.join(claimed_titles) or 'OK'}{Colors.RESET}",
        )
        return True
    else:
        with stats_lock:
            stats["still_missed"] += 1
        log(
            idx,
            f"Còn sót Weekly Quest chưa claim được: {still_pending} (Đã claim: {', '.join(claimed_titles) or '0'})",
            Colors.YELLOW,
        )
        return False


def main():
    accounts = load_accounts("account.txt")
    proxies = load_proxies("proxy.txt")

    if not accounts:
        log(None, "Không tìm thấy tài khoản trong account.txt!", Colors.RED)
        return

    REF_MANAGER.init_from_file(REFCODE_FILE)
    # Khởi tạo trước ánh xạ mã ref theo đúng thứ tự ví từ 1 -> N để đa luồng không bị nhảy thứ tự
    for acc in accounts:
        w = Account.from_key(acc["private_key"]).address.lower()
        REF_MANAGER.get_login_ref_code(w)

    # Hỗ trợ truyền danh sách index cần chạy lại qua tham số dòng lệnh (VD: python weekly_quest.py 18,162,421)
    if len(sys.argv) > 1:
        target_indices = [int(x.strip()) for x in sys.argv[1].split(",") if x.strip().isdigit()]
        work_items = [(idx, accounts[idx - 1]) for idx in target_indices if 1 <= idx <= len(accounts)]
    else:
        work_items = [(idx, acc) for idx, acc in enumerate(accounts, 1)]

    print(
        f"{Colors.GREEN}{Colors.BOLD}=== CHẠY ĐỘC LẬP NHIỆM VỤ TUẦN (WEEKLY QUESTS) | Số ví: {len(work_items)} | Luồng: {THREADS} ==={Colors.RESET}",
        flush=True,
    )

    for pass_num in range(1, 4):
        if not work_items:
            break
        if pass_num > 1:
            print(
                f"\n{Colors.YELLOW}{Colors.BOLD}=== VÒNG QUÉT VÉT #{pass_num} CHO {len(work_items)} VÍ CÒN SÓT / LỖI LOGIN ==={Colors.RESET}",
                flush=True,
            )
            stats["still_missed"] = 0
            stats["login_failed"] = 0

        failed_items = []
        with ThreadPoolExecutor(max_workers=THREADS) as executor:
            futures = {
                executor.submit(run_weekly_only, idx, acc, proxies): (idx, acc)
                for idx, acc in work_items
            }
            for future in as_completed(futures):
                idx, acc = futures[future]
                try:
                    ok = future.result()
                    if not ok:
                        failed_items.append((idx, acc))
                except Exception as e:
                    log(idx, f"Lỗi ngoại lệ: {e}", Colors.RED)
                    failed_items.append((idx, acc))

        work_items = sorted(failed_items, key=lambda x: x[0])

    print(
        f"\n{Colors.GREEN}{Colors.BOLD}=== TỔNG KẾT CHẠY NHIỆM VỤ TUẦN ==={Colors.RESET}\n"
        f"- Đã xong 3/3 từ trước : {stats['already_done']} ví\n"
        f"- Mới hoàn tất bổ sung : {stats['newly_completed']} ví\n"
        f"- Còn sót chưa xong    : {stats['still_missed']} ví\n"
        f"- Lỗi đăng nhập        : {stats['login_failed']} ví",
        flush=True,
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Colors.RED}Đã dừng theo yêu cầu người dùng.{Colors.RESET}")

