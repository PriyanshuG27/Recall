"""
backend/exceptions.py
=====================
Custom exceptions for the Recall application.
"""

class DuplicateItemException(Exception):
    """Raised when an item is identified as a duplicate and should not be saved."""
    def __init__(self, item_id: int):
        self.item_id = item_id
        super().__init__(f"Item already exists with ID {item_id}")
