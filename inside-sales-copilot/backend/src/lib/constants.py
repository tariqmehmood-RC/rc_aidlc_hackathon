"""Constants shared by the backend. Values come from requirements.md and design.md."""

# --- Brief lifecycle (design section 3) -------------------------------------------------
STATUS_QUEUED = "queued"
STATUS_PROCESSING = "processing"
STATUS_AWAITING_CONFIRMATION = "awaiting_confirmation"
STATUS_READY = "ready"
STATUS_APPROVED = "approved"
STATUS_FAILED = "failed"
STATUSES = (
    STATUS_QUEUED,
    STATUS_PROCESSING,
    STATUS_AWAITING_CONFIRMATION,
    STATUS_READY,
    STATUS_APPROVED,
    STATUS_FAILED,
)

STEP_PARSING = "Parsing"
STEP_RESEARCHING = "Researching"
STEP_MATCHING = "Matching case studies"
STEP_WRITING = "Writing brief"
STEPS = (STEP_PARSING, STEP_RESEARCHING, STEP_MATCHING, STEP_WRITING)  # attendee check removed

RULES_STATUSES = ("none", "pending", "ready", "failed")
JOB_TYPES = ("parse", "pipeline", "extract_rules")

# --- Business units and size tiers ------------------------------------------------------
BUSINESS_UNITS = ("AWS", "ServiceNow", "Salesforce", "Data & AI")
SIZE_TIERS = ("Enterprise", "Mid-market", "SMB", "Boutique", "Unknown")

# Enterprise: employees above 5,000 or revenue above $1B. Then by employees:
# Mid-market 500 to 5,000, SMB 50 to 499, Boutique below 50.
ENTERPRISE_EMPLOYEES_ABOVE = 5_000
ENTERPRISE_REVENUE_USD_ABOVE = 1_000_000_000
MID_MARKET_EMPLOYEES_MIN = 500
SMB_EMPLOYEES_MIN = 50

# --- Limits ------------------------------------------------------------------------------
MAX_INVITE_CHARS = 10_000
MAX_ATTENDEES = 20
MAX_NEWS_ITEMS = 3
MAX_RULES_APPLIED = 10
MAX_RULE_PROPOSALS = 3
MAX_RULE_CHARS = 200
MAX_CASE_STUDIES = 3
CASE_STUDY_MIN_SCORE = 60
CASE_STUDY_CANDIDATES = 8
AGENDA_TOTAL_MINUTES = 30
QUESTIONS_MIN = 8
QUESTIONS_MAX = 10
PAGE_SIZE = 20
STUCK_SECONDS = 120
RESEARCH_CACHE_DAYS = 7
BRIEF_TTL_DAYS = 30

# --- Bedrock -----------------------------------------------------------------------------
BEDROCK_MAX_REQUESTS_PER_SECOND = 1
BEDROCK_MAX_ATTEMPTS = 4
MODEL_HAIKU = "haiku"
MODEL_SONNET = "sonnet"
ENV_MODEL_HAIKU = "BEDROCK_MODEL_HAIKU"
ENV_MODEL_SONNET = "BEDROCK_MODEL_SONNET"
# max_tokens per prompt (design section 10)
MAX_TOKENS = {"parse": 1500, "research": 2500, "score": 1500, "write": 2500, "rules": 800}
# Which model writes the brief (prompt P4). The CDK context `briefModel` sets it for Lambda;
# the BRIEF_MODEL environment variable overrides it locally.
ENV_BRIEF_MODEL = "BRIEF_MODEL"
BRIEF_MODELS = (MODEL_HAIKU, MODEL_SONNET)
DEFAULT_BRIEF_MODEL = MODEL_HAIKU  # decided after the Wave 3 rerun; Sonnet is available via config
MAX_SNAPSHOT_ITEMS = 5

# --- Research fetching -------------------------------------------------------------------
# Default User-Agent for company research (Wikimedia asks for a contact). The same value is the
# CDK context default `researchUserAgent`. A deployment or a shell can override it with the
# RESEARCH_USER_AGENT environment variable.
RESEARCH_USER_AGENT_DEFAULT = (
    "InsideSalesCopilot/0.1 (Royal Cyber AWS AI-DLC hackathon; +https://github.com/tariqmehmood-RC/rc_aidlc_hackathon)"
)
ENV_RESEARCH_USER_AGENT = "RESEARCH_USER_AGENT"

# --- Invite parsing ----------------------------------------------------------------------
# A free mail domain does not name a company (requirement R2).
FREE_MAIL_DOMAINS = frozenset({
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com", "msn.com",
    "yahoo.com", "ymail.com", "icloud.com", "me.com", "aol.com", "proton.me",
    "protonmail.com", "gmx.com", "mail.com",
})
INVITE_WARNINGS = ("company_domain_mismatch", "only_free_email_domains")
