from enum import Enum


class TaskPriority(str, Enum):
    HIGH = "HIGH"
    NORMAL = "NORMAL"
    BACKGROUND = "BACKGROUND"
    BULK = "BULK"
