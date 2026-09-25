class LedgerImportError(Exception):
    """Raised anywhere in the import pipeline (parser, planner, positions)
    when a file must be rejected whole. The route layer (step 6) is the
    only place that catches this and turns it into an HTTPException —
    nothing below it knows about HTTP."""

    def __init__(self, code: str, message: str, **details):
        self.code = code
        self.message = message
        self.details = details
        super().__init__(message)
