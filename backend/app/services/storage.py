import io
from minio import Minio
from app.core.config import settings
from loguru import logger


class StorageService:
    """
    Service layer wrapping MinIO (S3-compatible) client operations.
    Provides utility methods for file storage.
    """
    def __init__(self):
        # MinIO client initialization
        self.client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        self._ensure_bucket()

    def _ensure_bucket(self):
        """Creates the bucket if it does not already exist."""
        try:
            if not self.client.bucket_exists(settings.MINIO_BUCKET_NAME):
                self.client.make_bucket(settings.MINIO_BUCKET_NAME)
                logger.info(
                    f"MinIO storage bucket '{settings.MINIO_BUCKET_NAME}' created successfully."
                )
        except Exception as e:
            logger.error(
                f"Failed to check/create MinIO bucket '{settings.MINIO_BUCKET_NAME}': {e}"
            )
            # Do not raise during initialization, allow delayed failure on usage

    def upload_file(
        self, object_name: str, data: bytes, length: int, content_type: str
    ) -> str:
        """
        Uploads file bytes to the configured MinIO bucket.
        Returns the logical path to the stored object.
        """
        try:
            self.client.put_object(
                settings.MINIO_BUCKET_NAME,
                object_name,
                io.BytesIO(data),
                length,
                content_type=content_type,
            )
            logger.info(
                f"File '{object_name}' successfully uploaded to storage bucket '{settings.MINIO_BUCKET_NAME}'."
            )
            return f"{settings.MINIO_BUCKET_NAME}/{object_name}"
        except Exception as e:
            logger.error(f"Failed to upload object '{object_name}' to MinIO: {e}")
            raise

    def upload_stream(
        self, object_name: str, stream, length: int, content_type: str
    ) -> str:
        """
        Uploads a file-like stream directly to MinIO without loading entire object into memory.
        Uses 10MB multipart chunks for efficient streaming uploads of large files.
        """
        try:
            self.client.put_object(
                settings.MINIO_BUCKET_NAME,
                object_name,
                data=stream,
                length=length,
                part_size=10 * 1024 * 1024,
                content_type=content_type,
            )
            logger.info(
                f"Stream '{object_name}' ({length} bytes) successfully uploaded to bucket '{settings.MINIO_BUCKET_NAME}'."
            )
            return f"{settings.MINIO_BUCKET_NAME}/{object_name}"
        except Exception as e:
            logger.error(f"Failed to upload stream '{object_name}' to MinIO: {e}")
            raise

    def download_file_to_path(self, object_name: str, target_path: str) -> None:
        """
        Streams an object directly from MinIO to a local disk file path.
        Avoids buffering the full object payload into Python memory.
        """
        response = None
        try:
            response = self.client.get_object(
                settings.MINIO_BUCKET_NAME, object_name
            )
            with open(target_path, "wb") as f:
                for chunk in response.stream(amt=64 * 1024):
                    f.write(chunk)
            logger.info(f"Streamed object '{object_name}' from MinIO to '{target_path}'.")
        except Exception as e:
            logger.error(f"Failed to stream object '{object_name}' to path '{target_path}': {e}")
            raise
        finally:
            if response:
                response.close()
                response.release_conn()

    def download_file(self, object_name: str) -> bytes:
        """
        Downloads and reads file bytes from the configured MinIO bucket.
        """
        response = None
        try:
            response = self.client.get_object(
                settings.MINIO_BUCKET_NAME, object_name
            )
            return response.read()
        except Exception as e:
            logger.error(
                f"Failed to download object '{object_name}' from MinIO: {e}"
            )
            raise
        finally:
            if response:
                response.close()
                response.release_conn()

    def delete_file(self, object_name: str) -> None:
        """
        Deletes an object from the configured MinIO bucket.
        """
        try:
            self.client.remove_object(settings.MINIO_BUCKET_NAME, object_name)
            logger.info(
                f"File '{object_name}' successfully deleted from storage bucket '{settings.MINIO_BUCKET_NAME}'."
            )
        except Exception as e:
            logger.error(f"Failed to delete object '{object_name}' from MinIO: {e}")
            raise
