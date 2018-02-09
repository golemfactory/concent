from enum import Enum
from enum import unique


@unique
class HashingAlgorithm(Enum):
    SHA1 = 'sha1'
