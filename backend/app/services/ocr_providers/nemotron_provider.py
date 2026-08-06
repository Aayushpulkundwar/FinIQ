import base64
import time
from typing import Optional
from loguru import logger
from openai import OpenAI, APIError, APIConnectionError, RateLimitError
from app.core.config import settings
from app.services.ocr_providers.base import BaseOCRProvider


class NemotronProvider(BaseOCRProvider):
    """
    OCR provider implementation for NVIDIA Nemotron Parse v1.2 using the OpenAI Python SDK.
    Sends high-resolution rendered page images to the Nemotron endpoint and retrieves structured Markdown/text.
    Implements configurable exponential backoff retries for network resilience.
    """
    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        max_retries: Optional[int] = None,
        retry_backoff: Optional[float] = None,
    ):
        self.host = host or settings.NEMOTRON_HOST
        self.port = port or settings.NEMOTRON_PORT
        self.model = model or settings.NEMOTRON_MODEL
        self.api_key = api_key or settings.NEMOTRON_API_KEY or "dummy_key"
        self.max_retries = max_retries if max_retries is not None else settings.OCR_RETRY_COUNT
        self.retry_backoff = retry_backoff if retry_backoff is not None else settings.OCR_RETRY_BACKOFF

        base_url = f"http://{self.host}:{self.port}/v1"
        logger.info(f"NemotronProvider: Initializing OpenAI SDK client targeting endpoint '{base_url}' with model='{self.model}'")
        self.client = OpenAI(
            base_url=base_url,
            api_key=self.api_key,
            timeout=120.0,
        )

    def process_page_image(self, image_bytes: bytes, page_num: int) -> str:
        """
        Submits rendered page PNG image to NVIDIA Nemotron Parse v1.2 and extracts Markdown text.
        Retries up to `max_retries` attempts with exponential backoff on failure.
        """
        if not image_bytes:
            return ""

        b64_image = base64.b64encode(image_bytes).decode("utf-8")
        data_uri = f"data:image/png;base64,{b64_image}"

        prompt_messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Extract all text, headings, paragraphs, bullet lists, and tables from this document page image. "
                            "Preserve document structure and format tables as Markdown tables."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": data_uri},
                    },
                ],
            }
        ]

        attempt = 0
        current_delay = 1.0

        while attempt < self.max_retries:
            attempt += 1
            try:
                t0 = time.time()
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=prompt_messages,
                    temperature=0.0,
                )
                elapsed = time.time() - t0

                if response.choices and len(response.choices) > 0:
                    text_content = response.choices[0].message.content or ""
                    text_clean = text_content.strip()
                    logger.info(
                        f"NemotronProvider: Page {page_num} OCR completed in {elapsed:.2f}s "
                        f"(attempt={attempt}/{self.max_retries}, extracted chars={len(text_clean)})"
                    )
                    return text_clean
                else:
                    logger.warning(f"NemotronProvider: Page {page_num} received empty choices from API response (attempt={attempt})")
            except (APIError, APIConnectionError, RateLimitError, Exception) as err:
                logger.warning(
                    f"NemotronProvider: Page {page_num} OCR request failed (attempt {attempt}/{self.max_retries}): {err}"
                )
                if attempt >= self.max_retries:
                    logger.error(f"NemotronProvider: Exhausted all {self.max_retries} attempts for page {page_num}.")
                    raise RuntimeError(f"OCR failed after {self.max_retries} attempts for page {page_num}: {err}") from err

                time.sleep(current_delay)
                current_delay *= self.retry_backoff

        raise RuntimeError(f"OCR failed after {self.max_retries} attempts for page {page_num}.")
