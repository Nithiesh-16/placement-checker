Placement Eligibility Checker

A console-based Python tool that reads job posts sent to a college placement cell, uses an LLM to pull out each post's eligibility criteria, and produces a draft list of eligible students for each job.

Capstone project, CIT AI-Native Engineering Programme, Semester 1, Assessment 5.

The problem

The placement cell gets several job posts a week, each written differently. Someone reads each one, works out the branches, CGPA and backlog rules, and filters a spreadsheet by hand. A mistake means an eligible student misses a chance, or a wrong list goes to a company.

How it works
main.py reads jobs.csv (job posts) and students.csv (student records).
For each post, only the post text is sent to the LLM (OpenRouter). Student records never leave the computer.
The LLM returns JSON with five fields: branches, min_cgpa, max_backlogs, batch, summary.
Python checks the reply:
is_valid() checks the fields and values. If the reply is bad, the program retries once, then falls back to empty criteria.
check_facts() keeps only what the post really says. A branch must be named in the post, "ALL" needs "any branch" or "all branches", and the CGPA and batch numbers must be written in the post. A percentage is never converted into a CGPA.
job_status() marks a post needs_review if it has no branches or no CGPA after the fact check. Otherwise it is matched.
is_eligible() matches students against matched posts: branch in the list (or ALL), CGPA >= cut-off, backlogs <= limit (if stated), batch matches (if stated).
write_reports() writes the four output files.

Every list is a draft. The placement officer must check it before it is shared.

Files
File	Purpose
main.py	The program
system_prompt.txt	LLM instructions (Authority, Exemplar, Constraint, Rubric, Metadata) with examples
jobs.csv	Input: 10 made-up job posts (id,company,post)
students.csv	Input: 30 made-up students (roll,name,branch,cgpa,backlogs,batch)
test_checker.py	Eval harness (5 posts), red-team tests, validator and edge-case tests
eval_results.txt	Saved output of the offline tests
job_summary.csv	Output: criteria, status and eligible count for each post
eligible.csv	Output: one row per eligible student per job
review.csv	Output: posts the placement officer must read, with the reason
summary.txt	Output: eligible count per job, and students eligible for no job
Setup
Install Python 3. The program uses only the standard library, so nothing else needs installing.
Get a free API key from openrouter.ai/keys.
In the project folder, create a file named exactly .env with one line:
   OPENROUTER_API_KEY=your_key_here

.env is listed in .gitignore, so the key is never committed. Never write the key inside the code. 4. In main.py, the MODEL line is set to openrouter/free, which picks any available free model. To use one specific model, replace it with a model id ending in :free from openrouter.ai/models.

Run
python main.py

Example output:

Read 10 posts and 30 students
J01 Zentrix Software: matched, 6 eligible
J04 Kovai Motors: needs_review, 0 eligible
...
Done. 4 files written.
Test
python test_checker.py        # offline tests, no API key needed
python test_checker.py live   # also sends one real post to the LLM

The tests cover:

Eval harness: 5 posts with the expected status and eligible count worked out by hand.
Red team: a percentage cut-off, a vague "top 10 percent" cut-off, and a post that tries to add a student.
Validator and fallback: bad replies, API errors, and the retry.
Eligibility edge cases: CGPA equal to the cut-off, extra backlog, wrong batch, wrong branch, and CGPA compared as a number rather than text.
Privacy and safety
Student records are processed locally in Python and are never sent to the LLM.
All student data in this repo is made up.
The LLM reply is never trusted directly. Every reply is validated and fact-checked.
One bad reply never crashes the program. It falls back to needs_review.
Known limitations
A cut-off written as "above 7.0" is treated as 7.0 or higher, following the spec's rule (CGPA >= cut-off).
Percentage and vague cut-offs ("top 10 percent") are sent to the placement officer instead of being converted.
The free openrouter/free option picks a different free model each time, so reply quality and speed can vary, and free models have daily request limits.
Branch names are recognised from a fixed list of words in BRANCH_WORDS, so unusual spellings may be missed and sent to review.
