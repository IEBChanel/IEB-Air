"""Thread-safe mail.tm client with domain caching, proxy rotation & retry support."""
import random
import re
import string
import threading
import time

import requests

API = "https://api.mail.tm"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
)

_DOMAIN_LOCK = threading.Lock()
_CACHED_DOMAINS = []
_CACHE_TS = 0.0


def _parse_proxy(proxy_raw: str) -> dict:
    if not proxy_raw:
        return None
    if "://" in proxy_raw:
        return {"http": proxy_raw, "https": proxy_raw}
    parts = proxy_raw.split(":")
    if len(parts) == 4:
        ip, port, user, pw = parts
        url = f"http://{user}:{pw}@{ip}:{port}"
        return {"http": url, "https": url}
    if len(parts) == 2:
        url = f"http://{parts[0]}:{parts[1]}"
        return {"http": url, "https": url}
    return None


class MailTM:
    def __init__(self, proxy=None, raw_proxies=None, start_idx=0):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": UA, "Accept": "application/json"})
        self.raw_proxies = raw_proxies or []
        self.proxy_idx = start_idx % len(self.raw_proxies) if self.raw_proxies else 0
        if proxy:
            self.session.proxies.update(proxy)
        elif self.raw_proxies:
            p = _parse_proxy(self.raw_proxies[self.proxy_idx])
            if p:
                self.session.proxies.update(p)
        self.address = None
        self.password = None
        self.token = None

    def rotate_proxy(self):
        if len(self.raw_proxies) > 1:
            self.proxy_idx = (self.proxy_idx + 1) % len(self.raw_proxies)
            p = _parse_proxy(self.raw_proxies[self.proxy_idx])
            if p:
                self.session.proxies.clear()
                self.session.proxies.update(p)

    def _domains(self, force_refresh: bool = False) -> list:
        global _CACHED_DOMAINS, _CACHE_TS
        with _DOMAIN_LOCK:
            now = time.time()
            if _CACHED_DOMAINS and not force_refresh and (now - _CACHE_TS < 300):
                return list(_CACHED_DOMAINS)

            for _ in range(5):
                try:
                    r = self.session.get(f"{API}/domains", timeout=15)
                    if r.status_code == 200:
                        data = r.json()
                        members = data.get("hydra:member", data) if isinstance(data, dict) else data
                        active = [m["domain"] for m in members if m.get("isActive", True) and m.get("domain")]
                        if not active and members:
                            active = [members[0]["domain"]]
                        if active:
                            _CACHED_DOMAINS = active
                            _CACHE_TS = time.time()
                            return list(_CACHED_DOMAINS)
                except Exception:
                    self.rotate_proxy()
                time.sleep(1.0)
            return list(_CACHED_DOMAINS)

    def _domain(self) -> str:
        domains = self._domains()
        if not domains:
            raise RuntimeError("Không lấy được domain từ api.mail.tm")
        return random.choice(domains)

    def create_account(self, retries: int = 6) -> str:
        last_err = ""
        for attempt in range(retries):
            try:
                domain = self._domain()
                user = "".join(random.choices(string.ascii_lowercase + string.digits, k=12))
                self.address = f"{user}@{domain}"
                self.password = "".join(random.choices(string.ascii_letters + string.digits, k=16))
                r = self.session.post(
                    f"{API}/accounts",
                    json={"address": self.address, "password": self.password},
                    timeout=15,
                )
                if r.status_code in (200, 201):
                    return self.address
                if r.status_code == 429:
                    self.rotate_proxy()
                    time.sleep(1.5 + attempt)
                    continue
                if r.status_code == 422:
                    self._domains(force_refresh=True)
                last_err = f"HTTP {r.status_code}: {r.text[:160]}"
            except Exception as e:
                last_err = f"{type(e).__name__}: {str(e)[:120]}"
                self.rotate_proxy()
            time.sleep(1.0)
        raise RuntimeError(f"create account failed ({last_err})")

    def login(self, retries: int = 5) -> str:
        last_err = ""
        for attempt in range(retries):
            try:
                r = self.session.post(
                    f"{API}/token",
                    json={"address": self.address, "password": self.password},
                    timeout=15,
                )
                if r.status_code == 200:
                    self.token = r.json()["token"]
                    return self.token
                if r.status_code == 429:
                    self.rotate_proxy()
                    time.sleep(1.5 + attempt)
                    continue
                last_err = f"HTTP {r.status_code}: {r.text[:160]}"
            except Exception as e:
                last_err = f"{type(e).__name__}: {str(e)[:120]}"
                self.rotate_proxy()
            time.sleep(1.0)
        raise RuntimeError(f"login failed ({last_err})")

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    def messages(self):
        try:
            r = self.session.get(f"{API}/messages", headers=self._headers(), timeout=15)
            if r.status_code != 200:
                return []
            data = r.json()
            return data.get("hydra:member", data) if isinstance(data, dict) else data
        except Exception:
            self.rotate_proxy()
            return []

    def message(self, msg_id):
        try:
            r = self.session.get(f"{API}/messages/{msg_id}", headers=self._headers(), timeout=15)
            return r.json() if r.status_code == 200 else {}
        except Exception:
            self.rotate_proxy()
            return {}

    def wait_for_link(self, timeout=120, poll=4, keyword=None):
        """Poll inbox, return (url, token, subject) from the first email containing a link."""
        start = time.time()
        seen = set()
        while time.time() - start < timeout:
            try:
                for m in self.messages():
                    mid = m.get("id")
                    if not mid or mid in seen:
                        continue
                    seen.add(mid)
                    subj_intro = (m.get("subject", "") + " " + m.get("intro", "")).lower()
                    if keyword and keyword.lower() not in subj_intro:
                        continue
                    full = self.message(mid)
                    html_part = full.get("html") or []
                    if isinstance(html_part, str):
                        html_part = [html_part]
                    text = (full.get("text") or "") + " " + " ".join(html_part)
                    urls = re.findall(r"https?://[^\s\"'<>]+", text)
                    token = None
                    mm = re.search(r"[?&]token=([A-Za-z0-9._\-]+)", text)
                    if mm:
                        token = mm.group(1)
                    if urls or token:
                        return urls[0] if urls else "", token, m.get("subject", "")
            except Exception:
                pass
            time.sleep(poll)
        return "", None, ""


if __name__ == "__main__":
    m = MailTM()
    print("created:", m.create_account())
    m.login()
    print("login ok, waiting 5s for any mail...")
    print(m.wait_for_link(timeout=8))
