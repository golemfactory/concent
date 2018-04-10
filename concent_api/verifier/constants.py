from enum import Enum


class VerificationResult(Enum):
    MATCH       = 'match'
    MISMATCH    = 'mismatch'
    ERROR       = 'error'
