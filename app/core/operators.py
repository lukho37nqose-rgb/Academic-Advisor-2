"""
Shared operator registry to ensure the compiler and engine stay strictly in sync.
"""

SUPPORTED_LEAF_OPERATORS = {
    "==",
    "!=",
    ">",
    "<",
    ">=",
    "<=",
    "includes"
}

SUPPORTED_BRANCH_OPERATORS = {
    "AND",
    "OR",
    "NOT"
}

class UnsupportedOperatorError(ValueError):
    """Raised when an unrecognized operator is encountered."""
    pass
