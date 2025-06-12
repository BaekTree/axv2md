import json
import os
import tarfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import arxiv
from tqdm import tqdm


def fetch_arxiv_tex(arxiv_id):
    assert isinstance(arxiv_id, str), "type of arxiv_id must be str."

    paper = next(arxiv.Client().results(arxiv.Search(id_list=[arxiv_id])))
    paper.download_source(filename="downloaded-paper.tar.gz")

    # Path to your .tar.gz file
    file_path = "downloaded-paper.tar.gz"

    # Directory where you want to extract the contents
    extract_path = os.path.join("paper_sources", arxiv_id, "latex")
    os.makedirs(extract_path, exist_ok=True)

    # Open and extract
    with tarfile.open(file_path, "r:gz") as tar:
        tar.extractall(path=extract_path)

    print(f"Extraction completed to {extract_path}")


def search_batch_arxiv_id(query):
    # Construct the default API client.
    client = arxiv.Client()

    # Search for the 10 most recent articles matching the keyword "quantum."
    search = arxiv.Search(
        query=query, max_results=1000, sort_by=arxiv.SortCriterion.SubmittedDate
    )

    results = client.results(search)
    all_results = list(results)
    return [r.entry_id.split("/")[-1] for r in all_results]


# 글로벌 락 + 타이밍을 이용한 rate limiter
class RateLimiter:
    def __init__(self, min_interval):
        self.lock = threading.Lock()
        self.min_interval = min_interval
        self.last_time_called = 0.0

    def wait(self):
        with self.lock:
            elapsed = time.time() - self.last_time_called
            wait_time = self.min_interval - elapsed
            if wait_time > 0:
                time.sleep(wait_time)
            self.last_time_called = time.time()


# fetch_arxiv_tex는 유저가 정의한 함수
def parallel_arxiv_fetch(to_go_id_list, num_threads=4):
    rate_limiter = RateLimiter(min_interval=3.0)  # 3초 제한

    def safe_fetch(arxiv_id):
        try:
            rate_limiter.wait()  # 요청 전에 wait
            fetch_arxiv_tex(arxiv_id)
        except Exception:
            pass  # 예외 무시 또는 logging

    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(safe_fetch, arxiv_id) for arxiv_id in to_go_id_list]
        for _ in tqdm(as_completed(futures), total=len(futures)):
            pass


if __name__ == "__main__":
    # 1000개 id list 저장
    id_list = search_batch_arxiv_id("LLM")

    with open("id_list.json", "w", encoding="utf-8") as f:
        json.dump(id_list, f, indent=4, ensure_ascii=False)

    # retry if needed
    # 1000개 id list load
    with open("id_list.json", "r", encoding="utf-8") as f:
        id_list = json.load(f)
    already_paper_id_list = set(os.listdir("paper_sources"))
    to_go_id_list = set(id_list) - already_paper_id_list

    parallel_arxiv_fetch(to_go_id_list, num_threads=5)

    # each arxiv id fetch data
    # arxiv_id = "2506.02089v1"
    # fetch_arxiv_tex(arxiv_id)
