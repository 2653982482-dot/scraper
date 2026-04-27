import subprocess
import json
import os
import glob

scripts = [
    ("X/Twitter", "python3 scraper.py"),
    ("9to5Mac", "python3 scraper_9to5mac.py"),
    ("TechCrunch & Social Media Today", "python3 scraper_combined_pw.py"),
    ("Reuters Technology", "python3 scraper_reuters.py"),
    ("SiliconANGLE", "python3 scraper_siliconangle.py"),
    ("AI中文网", "python3 scraper_aizws.py"),
    ("量子位", "python3 scraper_qbitai.py"),
    ("新智元", "python3 scraper_xinzhiyuan.py"),
    ("腾讯研究院", "python3 scraper_tencent.py"),
    ("Reddit", "python3 scraper_reddit.py"),
    ("AIBase", "python3 scraper_aibase.py"),
    ("Newsletter", "python3 scraper_newsletter.py"),
]

def run_script(name, cmd):
    print(f"[{name}] Starting...")
    try:
        # First attempt
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            print(f"[{name}] Success on first try.")
            return True
        else:
            print(f"[{name}] First try failed. Retrying...")
            # Retry
            result2 = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
            if result2.returncode == 0:
                print(f"[{name}] Success on second try.")
                return True
            else:
                print(f"[{name}] Failed after retry. Error: {result2.stderr.strip()[:200]}")
                return False
    except subprocess.TimeoutExpired:
        print(f"[{name}] Timeout. Retrying...")
        try:
            result2 = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
            if result2.returncode == 0:
                print(f"[{name}] Success on second try.")
                return True
            else:
                print(f"[{name}] Failed after retry (timeout/error).")
                return False
        except subprocess.TimeoutExpired:
            print(f"[{name}] Failed after retry (timeout).")
            return False

# Run in parallel using ThreadPoolExecutor
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=9) as executor:
    futures = {executor.submit(run_script, name, cmd): name for name, cmd in scripts}
    for future in futures:
        future.result()

print("\n--- Collection Results ---")
json_files = glob.glob("*_raw.json")
for jf in json_files:
    try:
        with open(jf, "r", encoding="utf-8") as f:
            data = json.load(f)
            count = len(data) if isinstance(data, list) else len(data.get("items", data.get("data", [])))
            print(f"File: {jf} -> {count} items")
    except Exception as e:
        print(f"File: {jf} -> Error reading: {e}")
