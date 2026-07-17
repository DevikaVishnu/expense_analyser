def format_amount(cents: int) -> str:
    """Render signed integer cents as a human-readable signed dollar string."""
    sign = "-" if cents < 0 else ""
    return f"{sign}${abs(cents) / 100:.2f}"