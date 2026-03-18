import os
import logging
import tempfile
from contextlib import contextmanager

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fix 7 — ContentType map (extension → MIME type)
# Used by upload_file to set correct Content-Type on every object.
# ---------------------------------------------------------------------------
_CONTENT_TYPES: dict[str, str] = {
    ".pdf":  "application/pdf",
    ".txt":  "text/plain; charset=utf-8",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc":  "application/msword",
    ".csv":  "text/csv",
    ".json": "application/json",
    ".md":   "text/markdown",
}

# Fix 8 — Temp directory driven by env var (default /tmp)
# Override with TEMP_DIR if you mount a dedicated emptyDir volume.
_TEMP_DIR = os.getenv("TEMP_DIR", "/tmp")


class MinIOStorage:
    """
    Thin wrapper around boto3 S3 client for MinIO.

    Fixes applied (9 total):
      1  Credential fail-fast       — raises EnvironmentError at startup if env vars absent
      2  Lazy bucket check          — _ensure_bucket() called on first operation, not __init__
      3  list_files exception log   — logs error with bucket+detail, returns partial results
      4  list_files pagination      — ContinuationToken loop, no silent truncation at 1 000
      5  Retry config               — standard mode, 5 attempts, exponential backoff
      6  Connection pool            — max_pool_connections from MINIO_POOL_SIZE (default 25)
      7  ContentType on upload      — ExtraArgs ContentType from extension map
      8  Context manager download   — temp_download() guarantees cleanup; replaces download_to_temp
      9  get_file_size logging      — logs specific ClientError instead of bare except: return 0
    """

    def __init__(self) -> None:
        # ------------------------------------------------------------------
        # Fix 1 — Credential fail-fast
        # Config errors (missing secrets) must crash immediately with a clear
        # message.  Connectivity errors (MinIO slow to start) are handled
        # lazily in _ensure_bucket().  These are different failure modes.
        # ------------------------------------------------------------------
        self.endpoint   = os.getenv("MINIO_ENDPOINT")
        self.access_key = os.getenv("MINIO_ACCESS_KEY")
        self.secret_key = os.getenv("MINIO_SECRET_KEY")
        self.bucket     = os.getenv("MINIO_BUCKET", "documind-uploads")
        self.use_ssl    = os.getenv("MINIO_USE_SSL", "false").lower() == "true"

        missing = [
            name for name, val in {
                "MINIO_ENDPOINT":   self.endpoint,
                "MINIO_ACCESS_KEY": self.access_key,
                "MINIO_SECRET_KEY": self.secret_key,
            }.items()
            if not val
        ]
        if missing:
            raise EnvironmentError(
                f"MinIOStorage: required env vars not set: {', '.join(missing)}"
            )

        protocol = "https" if self.use_ssl else "http"

        # ------------------------------------------------------------------
        # Fix 5 + Fix 6 — Retry config and connection pool in one Config block
        # ------------------------------------------------------------------
        self.client = boto3.client(
            "s3",
            endpoint_url=f"{protocol}://{self.endpoint}",
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            config=Config(
                signature_version    = "s3v4",
                max_pool_connections = int(os.getenv("MINIO_POOL_SIZE", "25")),
                retries = {
                    "mode":         "standard",   # exponential backoff + jitter
                    "max_attempts": 5,            # protects against MinIO rolling restarts
                },
            ),
            region_name="us-east-1",  # MinIO ignores this but boto3 requires it
        )

        # Fix 2 — bucket verification is deferred; see _ensure_bucket()
        self._bucket_verified = False

    # -----------------------------------------------------------------------
    # Fix 2 — Lazy bucket check
    # -----------------------------------------------------------------------
    def _ensure_bucket(self) -> None:
        """
        Verify the bucket exists, creating it if not found.
        Called at the top of every public method that touches the bucket.
        Skipped on subsequent calls once verified.
        """
        if self._bucket_verified:
            return

        try:
            self.client.head_bucket(Bucket=self.bucket)
            self._bucket_verified = True
            logger.info("MinIO bucket '%s' verified.", self.bucket)
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code")
            if code in ("404", "NoSuchBucket"):
                self.client.create_bucket(Bucket=self.bucket)
                self._bucket_verified = True
                logger.info("MinIO bucket '%s' created.", self.bucket)
            else:
                # Auth errors, network errors — re-raise so the caller gets a
                # clear HTTP 503 rather than a confusing downstream failure.
                logger.error(
                    "MinIO bucket check failed",
                    extra={"bucket": self.bucket, "error": str(e)},
                )
                raise

    # -----------------------------------------------------------------------
    # upload_file
    # -----------------------------------------------------------------------
    def upload_file(
        self,
        filename: str,
        file_obj,
        content_type: str | None = None,
    ) -> str:
        """
        Upload a file-like object to MinIO.

        Args:
            filename:     Object key (path) in the bucket.
            file_obj:     Readable file-like object.
            content_type: Override MIME type.  If None, derived from extension.

        Returns:
            The object key (filename).
        """
        self._ensure_bucket()

        # Fix 7 — derive ContentType from extension if not supplied
        if content_type is None:
            ext = os.path.splitext(filename)[1].lower()
            content_type = _CONTENT_TYPES.get(ext, "application/octet-stream")

        self.client.upload_fileobj(
            file_obj,
            self.bucket,
            filename,
            ExtraArgs={"ContentType": content_type},
        )
        return filename

    # -----------------------------------------------------------------------
    # Fix 8 — Context manager download (replaces download_to_temp)
    # -----------------------------------------------------------------------
    @contextmanager
    def temp_download(self, filename: str):
        """
        Context manager: download a file from MinIO to a temp path.

        Guarantees temp file deletion on exit regardless of whether the caller
        raises an exception.  Temp files are written to TEMP_DIR (default /tmp).

        Usage:
            with minio.temp_download(filename) as path:
                chunks = parser.parse_with_metadata(path)
            # file is already deleted here even if parse raised
        """
        self._ensure_bucket()

        ext = os.path.splitext(filename)[1]
        tmp = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=ext,
            dir=_TEMP_DIR,
        )
        try:
            self.client.download_fileobj(self.bucket, filename, tmp)
            tmp.close()
            yield tmp.name
        except Exception:
            tmp.close()
            raise
        finally:
            try:
                os.unlink(tmp.name)
            except FileNotFoundError:
                pass  # already gone, nothing to do

    # -----------------------------------------------------------------------
    # delete_file
    # -----------------------------------------------------------------------
    def delete_file(self, filename: str) -> None:
        """Delete a file from MinIO."""
        self._ensure_bucket()
        self.client.delete_object(Bucket=self.bucket, Key=filename)

    # -----------------------------------------------------------------------
    # file_exists
    # -----------------------------------------------------------------------
    def file_exists(self, filename: str) -> bool:
        """Return True if the object exists in the bucket."""
        self._ensure_bucket()
        try:
            self.client.head_object(Bucket=self.bucket, Key=filename)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise  # re-raise permission errors, network issues, etc.

    # -----------------------------------------------------------------------
    # list_files — Fix 3 (exception logging) + Fix 4 (pagination)
    # -----------------------------------------------------------------------
    def list_files(self) -> list:
        """
        List all files in the bucket.

        Returns a list of dicts:  {filename, size, last_modified}

        Paginates through all result pages (S3/MinIO max 1 000 per page).
        On error after partial collection, logs and returns whatever was
        collected — partial results are better than an empty list.
        """
        self._ensure_bucket()

        result: list[dict] = []
        kwargs: dict = {"Bucket": self.bucket}

        while True:
            try:
                response = self.client.list_objects_v2(**kwargs)
            except Exception as e:
                # Fix 3 — catches both ClientError (S3 errors) and non-S3
                # network failures (socket timeouts, connection resets) that
                # can surface mid-pagination as plain Exception subclasses.
                logger.error(
                    "MinIO list_files error %s (returning %d partial results)",
                    type(e).__name__,
                    len(result),
                    extra={"bucket": self.bucket, "error": str(e)},
                )
                break

            for obj in response.get("Contents", []):
                result.append({
                    "filename":      obj["Key"],
                    "size":          obj["Size"],
                    "last_modified": obj["LastModified"].isoformat(),
                })

            # Fix 4 — follow continuation token until IsTruncated is False
            if response.get("IsTruncated"):
                kwargs["ContinuationToken"] = response["NextContinuationToken"]
            else:
                break

        return result

    # -----------------------------------------------------------------------
    # get_file_size — Fix 9 (specific exception handling)
    # -----------------------------------------------------------------------
    def get_file_size(self, filename: str) -> int:
        """
        Return file size in bytes, or 0 if the object does not exist.
        Logs and re-raises on unexpected errors (auth, network).
        """
        self._ensure_bucket()
        try:
            resp = self.client.head_object(Bucket=self.bucket, Key=filename)
            return resp["ContentLength"]
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code")
            if code == "404":
                return 0   # object simply doesn't exist — not an error
            logger.error(
                "MinIO get_file_size failed for '%s'",
                filename,
                extra={"bucket": self.bucket, "error": str(e)},
            )
            raise