"""Guardrails: input filter, out-of-corpus refusal, PII masking, budgets."""
import re

INJECTION_PATTERNS = [
    r"ignore (all |the |previous |above )?(instructions|prompts|rules)",
    r"disregard (all |the |previous )?(instructions|prompts|rules)",
    r"you are now (a|an|the)",
    r"system prompt",
    r"reveal (your|the) (system|hidden|secret)",
    r"jailbreak",
    r"do anything now",
    r"pretend (you are|to be)",
    r"override (your|the) (instructions|rules|guidelines)",
    r"\[SYSTEM\]",
    r"as an ai language model.*ignore",
]
_INJECTION = [re.compile(p, re.I) for p in INJECTION_PATTERNS]

# Words that mark a question as plausibly about this college corpus.
ON_TOPIC_HINTS = [
    "attendance", "exam", "placement", "hostel", "fee", "fees", "library",
    "notice", "handbook", "semester", "credit", "cgpa", "backlog", "leave",
    "dress", "id card", "ragging", "discipline", "re-evaluation",
    "revaluation", "scholarship", "mess", "transport", "bus", "internship",
    "offer", "drive", "company", "eligib", "rule", "regulation", "timing",
    "hours", "holiday", "syllabus", "grade", "detain", "condonation",
    "admission", "refund", "fine", "late", "certificate", "transcript",
    "college", "campus", "student", "faculty", "department", "course",
    "class", "lecture", "lab", "project", "viva", "sessional", "midterm",
    "university", "degree", "convocation",
    # Exam acronyms and terms students type without the word "exam"
    # (B-06: "pass marks for ESE and CIE" was refused as off-topic).
    "ese", "mse", "cie", "pass", "marks",
]

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?<!\d)(?:\+91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\d)")
AADHAAR_RE = re.compile(r"(?<!\d)\d{4}[\s-]?\d{4}[\s-]?\d{4}(?!\d)")
ROLL_RE = re.compile(r"\b\d{2,4}[A-Z]{2,4}\d{3,6}\b")


def mask_pii(text: str) -> str:
    text = EMAIL_RE.sub("[email masked]", text)
    text = PHONE_RE.sub("[phone masked]", text)
    text = AADHAAR_RE.sub("[id masked]", text)
    text = ROLL_RE.sub("[roll no. masked]", text)
    return text


def check_injection(text: str):
    for pat in _INJECTION:
        if pat.search(text):
            return True
    return False


def is_on_topic(question: str) -> bool:
    q = question.lower()
    return any(h in q for h in ON_TOPIC_HINTS)


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class GuardrailError(ValueError):
    pass


def guard_input(question: str, budget: int = 4000):
    """Raise GuardrailError with a safe refusal reason, else return cleaned."""
    q = (question or "").strip()
    if not q:
        raise GuardrailError("Please ask a question.")
    if len(q) > 2000:
        raise GuardrailError("Question too long — please keep it under 2000 characters.")
    if check_injection(q):
        raise GuardrailError(
            "I can't follow instructions embedded in a question. "
            "Please ask a plain question about college rules, notices or placements.")
    if estimate_tokens(q) > budget:
        raise GuardrailError("Question exceeds the per-request token budget.")
    return q


OUT_OF_CORPUS_REPLY = (
    "I don't know — that isn't covered in the college documents I have access to. "
    "I can only answer from the official KIET documents in this system "
    "(ordinances, fee structure, hostel rules, placement records and FAQ). "
    "Try rephrasing, or ask the college office for anything "
    "outside those documents."
)
