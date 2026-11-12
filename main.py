import csv
import json
import os
import re
import urllib.error
import urllib.request
 
JOBS_FILE = "jobs.csv"
STUDENTS_FILE = "students.csv"
PROMPT_FILE = "system_prompt.txt"
 
ALLOWED_BRANCHES = ["CSE", "IT", "AIDS", "ECE", "EEE", "MECH", "CIVIL"]
 
# Words that count as "the post names this branch"
BRANCH_WORDS = {
    "CSE": ["cse", "computer science"],
    "IT": ["it", "information technology"],
    "AIDS": ["aids", "ai&ds", "ai & ds", "ai and ds", "artificial intelligence"],
    "ECE": ["ece", "electronics and communication"],
    "EEE": ["eee", "electrical and electronics"],
    "MECH": ["mech", "mechanical"],
    "CIVIL": ["civil"],
}
 
 
# ---------- LOAD FUNCTIONS ----------
 
def normalize_branch(b):
    return b.strip().upper().replace("&", "").replace(" ", "")
 
 
def read_rows(path):
    """Read a CSV into a list of dictionaries.
    Handles a hidden BOM at the start of the file (utf-8-sig), tab-separated
    files, and spaces or capital letters in the header names."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        first_line = f.readline()
        f.seek(0)
        delimiter = "\t" if "\t" in first_line else ","
        rows = []
        for row in csv.DictReader(f, delimiter=delimiter):
            rows.append({k.strip().lower(): v for k, v in row.items() if k})
        return rows
 
 
def load_jobs(path):
    jobs = []
    try:
        for row in read_rows(path):
            try:
                jobs.append({"id": row["id"].strip(),
                             "company": row["company"].strip(),
                             "post": row["post"].strip()})
            except (KeyError, AttributeError):
                print("Skipping bad job row:", row)
    except FileNotFoundError:
        print("Cannot find", path)
    return jobs
 
 
def load_students(path):
    students = []
    try:
        for row in read_rows(path):
            try:
                students.append({"roll": row["roll"].strip(),
                                 "name": row["name"].strip(),
                                 "branch": normalize_branch(row["branch"]),
                                 "cgpa": float(row["cgpa"]),
                                 "backlogs": int(row["backlogs"]),
                                 "batch": int(row["batch"])})
            except (ValueError, KeyError, AttributeError):
                print("Skipping bad student row:", row)
    except FileNotFoundError:
        print("Cannot find", path)
    return students
 
 
# ---------- LLM CALL ----------
 
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# openrouter/free picks any available free model. To choose one yourself,
# use an id ending in ":free" from openrouter.ai/models?pricing=free
MODEL = "openrouter/free"
 
 
def load_env(path=".env"):
    """Read KEY=value lines from .env into environment variables."""
    try:
        with open(path, encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key.strip()] = value.strip()
    except FileNotFoundError:
        pass
 
 
def call_llm(system_prompt, post):
    """Send ONLY the post to OpenRouter and return the raw reply text."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY not found. Put it in .env")
 
    body = json.dumps({
        "model": MODEL,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": post},
        ],
    }).encode("utf-8")
 
    request = urllib.request.Request(
        OPENROUTER_URL, data=body,
        headers={"Authorization": "Bearer " + api_key,
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # show the reason OpenRouter gives, not just "Bad Request"
        raise RuntimeError("HTTP " + str(e.code) + ": " + e.read().decode("utf-8")[:300])
 
    message = data["choices"][0]["message"]
    text = (message.get("content") or "").strip()
    if not text:
        # some free models return an empty reply, show what came back
        raise RuntimeError("empty reply from model: " + str(data)[:300])
    # keep only the JSON object, in case the model added extra words or ``` fences
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        text = text[start:end + 1]
    return text
 
 
def is_valid(data):
    """Check the LLM reply has the right fields and values."""
    if not isinstance(data, dict):
        return False
    b = data.get("branches")
    if not isinstance(b, list) or not all(x in ALLOWED_BRANCHES + ["ALL"] for x in b):
        return False
    c = data.get("min_cgpa")
    if c is not None and (isinstance(c, bool) or not isinstance(c, (int, float)) or not 0 <= c <= 10):
        return False
    m = data.get("max_backlogs")
    if m is not None and (isinstance(m, bool) or not isinstance(m, int) or m < 0):
        return False
    y = data.get("batch")
    if y is not None and (isinstance(y, bool) or not isinstance(y, int)):
        return False
    s = data.get("summary")
    if not isinstance(s, str) or len(s.split()) > 12:
        return False
    return True
 
 
def read_criteria(post):
    """Ask the LLM, check the reply, retry once, fall back to None."""
    try:
        with open(PROMPT_FILE, encoding="utf-8") as f:
            system_prompt = f.read()
    except FileNotFoundError:
        print("Cannot find", PROMPT_FILE)
        return None
    for attempt in range(2):
        reply = ""
        try:
            reply = call_llm(system_prompt, post)
            data = json.loads(reply)
            if is_valid(data):
                # copy only the five fields
                return {k: data[k] for k in
                        ["branches", "min_cgpa", "max_backlogs", "batch", "summary"]}
        except Exception as e:
            print("  LLM attempt", attempt + 1, "failed:", e, "| reply:", repr(reply[:150]))
    return None
 
 
# ---------- PYTHON FACT CHECKS ----------
 
def word_in_text(word, text):
    return re.search(r"(?<![a-z0-9])" + re.escape(word) + r"(?![a-z0-9])", text) is not None
 
 
def numbers_written_in(post):
    """Numbers in the post that are NOT percentages."""
    found = []
    for num, pct in re.findall(r"(\d+(?:\.\d+)?)\s*(%|percent)?", post.lower()):
        if not pct:
            found.append(float(num))
    return found
 
 
def check_facts(criteria, post):
    """Keep only what the post really says. Everything else becomes empty/null."""
    text = post.lower()
    checked = dict(criteria)
 
    branches = []
    for b in criteria["branches"]:
        if b == "ALL":
            if "any branch" in text or "all branches" in text:
                branches.append("ALL")
        elif any(word_in_text(w, text) for w in BRANCH_WORDS[b]):
            branches.append(b)
    checked["branches"] = branches
 
    nums = numbers_written_in(post)
    if criteria["min_cgpa"] is not None and float(criteria["min_cgpa"]) not in nums:
        checked["min_cgpa"] = None
    if criteria["batch"] is not None and float(criteria["batch"]) not in nums:
        checked["batch"] = None
    return checked
 
 
def job_status(criteria):
    if not criteria["branches"] or criteria["min_cgpa"] is None:
        return "needs_review"
    return "matched"
 
 
def review_reason(criteria):
    reasons = []
    if not criteria["branches"]:
        reasons.append("no branch found")
    if criteria["min_cgpa"] is None:
        reasons.append("no CGPA found")
    return ", ".join(reasons)
 
 
# ---------- ELIGIBILITY ----------
 
def is_eligible(student, criteria):
    if "ALL" not in criteria["branches"] and student["branch"] not in criteria["branches"]:
        return False
    if student["cgpa"] < criteria["min_cgpa"]:
        return False
    if criteria["max_backlogs"] is not None and student["backlogs"] > criteria["max_backlogs"]:
        return False
    if criteria["batch"] is not None and student["batch"] != criteria["batch"]:
        return False
    return True
 
 
# ---------- OUTPUT ----------
 
def write_reports(results, students):
    with open("job_summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "company", "branches", "min_cgpa", "max_backlogs",
                    "batch", "status", "eligible_count"])
        for r in results:
            c = r["criteria"]
            w.writerow([r["id"], r["company"], "|".join(c["branches"]), c["min_cgpa"],
                        c["max_backlogs"], c["batch"], r["status"], len(r["eligible"])])
 
    with open("eligible.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["job_id", "company", "roll", "name", "branch", "cgpa"])
        for r in results:
            for s in r["eligible"]:
                w.writerow([r["id"], r["company"], s["roll"], s["name"], s["branch"], s["cgpa"]])
 
    with open("review.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "company", "reason", "post"])
        for r in results:
            if r["status"] == "needs_review":
                w.writerow([r["id"], r["company"], r["reason"], r["post"]])
 
    eligible_rolls = set()
    for r in results:
        for s in r["eligible"]:
            eligible_rolls.add(s["roll"])
    with open("summary.txt", "w", encoding="utf-8") as f:
        f.write("DRAFT - placement officer must check before sharing\n\n")
        for r in results:
            f.write(f'{r["id"]} {r["company"]}: {r["status"]}, {len(r["eligible"])} eligible\n')
        f.write("\nStudents eligible for no job yet:\n")
        for s in students:
            if s["roll"] not in eligible_rolls:
                f.write(f'{s["roll"]} {s["name"]}\n')
 
 
# ---------- MAIN ----------
 
def main():
    load_env()
    jobs = load_jobs(JOBS_FILE)
    students = load_students(STUDENTS_FILE)
    print("Read", len(jobs), "posts and", len(students), "students")
 
    results = []
    for job in jobs:
        criteria = read_criteria(job["post"])
        if criteria is None:
            # fallback: empty criteria, send to the officer
            criteria = {"branches": [], "min_cgpa": None, "max_backlogs": None,
                        "batch": None, "summary": ""}
            reason = "LLM reply invalid"
        else:
            criteria = check_facts(criteria, job["post"])
            reason = review_reason(criteria)
 
        status = job_status(criteria)
        eligible = []
        if status == "matched":
            eligible = [s for s in students if is_eligible(s, criteria)]
 
        results.append({"id": job["id"], "company": job["company"], "post": job["post"],
                        "criteria": criteria, "status": status,
                        "reason": reason, "eligible": eligible})
        print(job["id"], job["company"] + ":", status + ",", len(eligible), "eligible")
 
    write_reports(results, students)
    print("Done. 4 files written.")
 
 
if __name__ == "__main__":
    main()
 
