import threading
import time

from tubetape.jobs import Limit


def test_limit_caps_running_work_across_callers() -> None:
    limit = Limit(2)
    running, peak, lock = 0, 0, threading.Lock()

    def work() -> None:
        nonlocal running, peak
        with limit:
            with lock:
                running += 1
                peak = max(peak, running)
            time.sleep(0.02)
            with lock:
                running -= 1

    threads = [threading.Thread(target=work) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert peak == 2
