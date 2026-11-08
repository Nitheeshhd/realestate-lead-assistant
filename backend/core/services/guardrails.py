"""Server-side checks on what the assistant says. The prompt asks the model to behave,
this module makes sure it did, whatever the model returned."""
import re

DISCOUNT_RE = re.compile(
    r"discount|cashback|waiver|negotiab|special offer|best price|final price|deal\b|"
    r"छूट|डिस्काउंट|ऑफर|ડિસ્કાઉન્ટ|ઓફર|રાહત", re.I)
MONEY_RE = re.compile(
    r"(?:₹|\b(?:rs\.?|inr)\b)\s*[\d][\d,.]*\s*(?:lakhs?|lacs?|crores?|cr|k)?|"
    r"[\d][\d,.]*\s*(?:lakhs?|lacs?|crores?|cr)\b", re.I)
PERSON_RE = re.compile(
    r"(talk|speak|connect|call)\s+(to|with|me)?\s*(a\s+)?(real\s+)?(person|human|agent|executive|someone|salesperson)|"
    r"real person|call me|मुझसे बात|किसी इंसान|कॉल करें|इंसान से|व्यक्ति से|માણસ|વ્યક્તિ સાથે|ફોન કરો", re.I)
OPTOUT_RE = re.compile(r"\bstop\b|unsubscribe|opt[\s-]?out|do not contact|don't contact|मत भेजो|बंद करो|બંધ કરો", re.I)
DISCOUNT_ASK_RE = re.compile(r"discount|negotiat|best price|final price|छूट|डिस्काउंट|ડિસ્કાઉન્ટ|ભાવ ઓછો|कम कीमत", re.I)


def _norm(s):
    return re.sub(r"[\s,]", "", s.lower())


def check_reply(text, fact_values):
    """Return (ok, reason). Money amounts are allowed only if they appear verbatim in the
    fact sheet. Discount language is never allowed."""
    if DISCOUNT_RE.search(text):
        return False, "discount_language"
    facts = _norm(" ".join(fact_values))
    for m in MONEY_RE.finditer(text):
        if _norm(m.group(0)) not in facts:
            return False, "price_not_in_fact_sheet"
    return True, ""


def wants_person(text):
    return bool(PERSON_RE.search(text))


def wants_opt_out(text):
    return bool(OPTOUT_RE.search(text))


def asks_discount(text):
    return bool(DISCOUNT_ASK_RE.search(text))
