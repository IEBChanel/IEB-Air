# -*- coding: utf-8 -*-
"""
USERNAME GENERATOR UTILITY
- Sinh username tự nhiên (English Names / Social Handles) cho Twitter, Telegram, Discord, Web3 accounts.
- Hỗ trợ nhiều phong cách: ghép Tên + Họ + số, handle viết thường có dấu gạch dưới, v.v.
- Dễ dàng tái sử dụng cho nhiều kèo airdrop / bot khác nhau tương tự tempmail.py.
"""

import random
import string

FIRST_NAMES = [
    "James", "John", "Robert", "Michael", "William", "David", "Richard", "Joseph", "Thomas", "Charles",
    "Christopher", "Daniel", "Matthew", "Anthony", "Mark", "Donald", "Steven", "Paul", "Andrew", "Joshua",
    "Kenneth", "Kevin", "Brian", "George", "Timothy", "Ronald", "Edward", "Jason", "Jeffrey", "Ryan",
    "Jacob", "Gary", "Nicholas", "Eric", "Jonathan", "Stephen", "Larry", "Justin", "Scott", "Brandon",
    "Benjamin", "Samuel", "Gregory", "Alexander", "Patrick", "Frank", "Raymond", "Jack", "Dennis", "Jerry",
    "Tyler", "Aaron", "Henry", "Douglas", "Peter", "Adam", "Nathan", "Zachary", "Walter", "Harold",
    "Emma", "Olivia", "Ava", "Sophia", "Isabella", "Mia", "Charlotte", "Amelia", "Harper", "Evelyn",
    "Abigail", "Emily", "Elizabeth", "Mila", "Ella", "Avery", "Sofia", "Camila", "Aria", "Scarlett"
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez",
    "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
    "Lee", "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson",
    "Walker", "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores",
    "Green", "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell", "Mitchell", "Carter", "Roberts",
    "Gomez", "Phillips", "Evans", "Turner", "Diaz", "Parker", "Cruz", "Edwards", "Collins", "Reyes"
]


def generate_random_username(style: str = "camel", min_digits: int = 100, max_digits: int = 99999) -> str:
    """
    Sinh username tự nhiên:
    - style='camel': JohnSmith8321 (phù hợp Web3 profile, Game username)
    - style='lower': johnsmith8321 (phù hợp Twitter / X username)
    - style='snake': john_smith_83 (phù hợp Telegram username)
    """
    fn = random.choice(FIRST_NAMES)
    ln = random.choice(LAST_NAMES)
    num = random.randint(min_digits, max_digits)

    if style == "lower":
        return f"{fn.lower()}{ln.lower()}{num}"
    elif style == "snake":
        return f"{fn.lower()}_{ln.lower()}{random.randint(10, 999)}"
    else:
        # Mặc định: CamelCase (First + Last + Digits)
        return f"{fn}{ln}{num}"


def generate_social_handle(platform: str = "twitter") -> str:
    """Sinh username theo chuẩn đặc thù của từng mạng xã hội"""
    if platform.lower() in ("x", "twitter"):
        return generate_random_username(style="lower", min_digits=10, max_digits=9999)
    elif platform.lower() in ("tele", "telegram"):
        return generate_random_username(style="snake")
    return generate_random_username(style="camel")


if __name__ == "__main__":
    print("=== TEST USERNAME GENERATOR ===")
    print("Web3 / Profile:", [generate_random_username() for _ in range(3)])
    print("Twitter / X   :", [generate_social_handle("twitter") for _ in range(3)])
    print("Telegram      :", [generate_social_handle("telegram") for _ in range(3)])

