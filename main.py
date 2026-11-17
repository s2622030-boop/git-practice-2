
import sqlite3
import time
import requests
from bs4 import BeautifulSoup

# ----------------------------------
# 1. 設定
# ----------------------------------

BASE_URL = "https://github.com/orgs/google/repositories"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    )
}

DB_NAME = "google_repos.db"


# ----------------------------------
# 2. スター数を数値に変換
# ----------------------------------

def convert_stars(text):

    text = text.strip().lower().replace(",", "")

    try:
        if text.endswith("k"):
            return int(float(text[:-1]) * 1000)

        elif text.endswith("m"):
            return int(float(text[:-1]) * 1000000)

        return int(text)

    except ValueError:
        return 0


# ----------------------------------
# 3. データベースの準備
# ----------------------------------

conn = sqlite3.connect(DB_NAME)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS repositories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    language TEXT,
    stars INTEGER
)
""")

conn.commit()


# ----------------------------------
# 4. スクレイピング
# ----------------------------------

session = requests.Session()
session.headers.update(HEADERS)

repo_list = []

# 取得済みページを記録
seen_pages = {}

# 取得済みリポジトリ名を記録
seen_names = set()

page = 1
pages_checked = 0
stop_reason = ""

print("Googleのリポジトリ情報を取得します。", flush=True)

while True:

    url = f"{BASE_URL}?page={page}"

    print(f"\n========== {page}ページ目 ==========", flush=True)

    try:

        response = session.get(url, timeout=30)
        response.raise_for_status()

        # 課題指定の待機時間
        time.sleep(1)

        pages_checked += 1

        soup = BeautifulSoup(response.text, "html.parser")

        # HTMLの基本情報
        print("リクエストURL:", url, flush=True)
        print("実際のURL:", response.url, flush=True)
        print("ステータスコード:", response.status_code, flush=True)
        print("HTMLサイズ:", len(response.text), "文字", flush=True)

        title = soup.title.get_text(strip=True) if soup.title else "タイトルなし"
        print("ページタイトル:", title, flush=True)

        # リポジトリ名を取得
        repo_links = soup.select(
            'li h3 a[href^="/google/"]'
        )

        print(
            "ページ内のリポジトリ数:",
            len(repo_links),
            flush=True
        )

        # リポジトリが存在しない場合
        if not repo_links:

            stop_reason = "リポジトリが見つからなかった"

            print("\nリポジトリが見つかりません。", flush=True)
            print("HTMLの一部:", response.text[:300], flush=True)

            break

        # ページの内容を識別
        page_signature = tuple(
            link.get("href") for link in repo_links
        )

        # 同じページを検出
        if page_signature in seen_pages:

            stop_reason = "同じページが返された"

            print("\n同じページを検出しました。", flush=True)
            print(
                "今回のページ番号:",
                page,
                flush=True
            )
            print(
                "前回取得したページ番号:",
                seen_pages[page_signature],
                flush=True
            )
            print(
                "最後のリポジトリ:",
                repo_links[-1].get_text(strip=True),
                flush=True
            )

            break

        seen_pages[page_signature] = page

        page_count = 0
        new_count = 0

        # ----------------------------------
        # リポジトリ情報の取得
        # ----------------------------------

        for link in repo_links:

            name = link.get_text(strip=True)

            if not name:
                continue

            container = link.find_parent("li")

            if container is None:
                continue

            # 主要なプログラミング言語
            language_tag = container.select_one(
                'span[class*="PrimaryLanguageName"]'
            )

            if language_tag:
                language = language_tag.get_text(strip=True)
            else:
                language = "不明"

            # スター数
            star_tag = container.select_one(
                'a[href$="/stargazers"]'
            )

            if star_tag:
                star_text = star_tag.get_text(strip=True)
                stars = convert_stars(star_text)
            else:
                stars = 0

            page_count += 1

            # 重複登録を防止
            if name not in seen_names:

                repo_list.append(
                    (name, language, stars)
                )

                seen_names.add(name)
                new_count += 1

        print("今回のページ取得件数:", page_count, flush=True)
        print("新規取得件数:", new_count, flush=True)

        print(
            "最後のリポジトリ:",
            repo_links[-1].get_text(strip=True),
            flush=True
        )

        print(
            "累計取得件数:",
            len(repo_list),
            flush=True
        )

        page += 1

    except requests.exceptions.RequestException as e:

        stop_reason = f"通信エラー: {e}"

        print("\n通信エラーが発生しました。", flush=True)
        print(stop_reason, flush=True)

        break


# ----------------------------------
# 5. SQLiteにデータを保存
# ----------------------------------

print("\n================================")
print("スクレイピング終了")
print("終了理由:", stop_reason)
print("確認したページ数:", pages_checked)
print("新規取得件数:", len(repo_list))
print("================================")

if repo_list:

    # 既存データは削除せず、新規データを追加・更新
    cursor.executemany("""
        INSERT INTO repositories
        (name, language, stars)
        VALUES (?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            language = excluded.language,
            stars = excluded.stars
    """, repo_list)

    conn.commit()

    print("\nデータベースへの保存が完了しました。")

else:

    print("\n今回新しく取得したデータはありません。")


# ----------------------------------
# 6. SELECT文でデータを表示
# ----------------------------------

print("\n--- 保存されたリポジトリ情報 ---")

cursor.execute("""
    SELECT id, name, language, stars
    FROM repositories
    ORDER BY id
""")

results = cursor.fetchall()

for row in results:

    print(
        f"ID:{row[0]:>4} | "
        f"リポジトリ名:{row[1]:<40} | "
        f"言語:{row[2]:<15} | "
        f"スター数:{row[3]}"
    )

print("\nSELECT取得件数:", len(results), "件")


# ----------------------------------
# 7. 終了処理
# ----------------------------------

conn.close()

print("\nすべての処理が終了しました。", flush=True)
