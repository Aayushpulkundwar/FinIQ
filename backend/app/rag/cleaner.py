import re


class TextCleaner:
    """
    Utility class for normalising and cleaning text extracted from files.
    """
    @staticmethod
    def clean(text: str) -> str:
        """
        Cleans and normalizes raw document text:
        - Normalizes horizontal spaces.
        - Strips spaces adjacent to newlines.
        - Collapses repeated newlines.
        - Strips overall margins.
        """
        if not text:
            return ""

        # Normalize unicode non-breaking spaces
        text = text.replace("\xa0", " ")

        # Normalize repeated horizontal whitespaces to a single space
        text = re.sub(r"[ \t]+", " ", text)

        # Strip spaces at the start/end of lines
        text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)

        # Collapse multiple empty/whitespace lines to double newlines to preserve paragraphs
        text = re.sub(r"\n\s*\n", "\n\n", text)

        # Remove overall leading and trailing spaces
        return text.strip()
