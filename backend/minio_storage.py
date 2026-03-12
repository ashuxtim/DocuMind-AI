import os
import io
import tempfile
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError


class MinIOStorage:
    """Thin wrapper around boto3 S3 client for MinIO."""

    def __init__(self):
        self.endpoint = os.getenv("MINIO_ENDPOINT", "minio:9000")
        self.access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
        self.secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin123")
        self.bucket = os.getenv("MINIO_BUCKET", "documind-uploads")
        self.use_ssl = os.getenv("MINIO_USE_SSL", "false").lower() == "true"

        protocol = "https" if self.use_ssl else "http"
        self.client = boto3.client(
            "s3",
            endpoint_url=f"{protocol}://{self.endpoint}",
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            config=Config(signature_version="s3v4"),
            region_name="us-east-1",  # MinIO ignores this but boto3 requires it
        )

    def upload_file(self, filename: str, file_obj) -> str:
        """Upload a file-like object to MinIO. Returns the object key."""
        self.client.upload_fileobj(file_obj, self.bucket, filename)
        return filename

    def download_to_temp(self, filename: str) -> str:
        """Download a file from MinIO to a temp path. Caller must delete after use."""
        ext = os.path.splitext(filename)[1]
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
        self.client.download_fileobj(self.bucket, filename, tmp)
        tmp.close()
        return tmp.name

    def delete_file(self, filename: str):
        """Delete a file from MinIO."""
        self.client.delete_object(Bucket=self.bucket, Key=filename)

    def file_exists(self, filename: str) -> bool:
        """Check if a file exists in MinIO."""
        try:
            self.client.head_object(Bucket=self.bucket, Key=filename)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise  # re-raise permission errors, network issues, etc.

    def list_files(self) -> list:
        """List all files in the bucket. Returns list of {filename, size, last_modified}."""
        result = []
        try:
            response = self.client.list_objects_v2(Bucket=self.bucket)
            for obj in response.get("Contents", []):
                result.append({
                    "filename": obj["Key"],
                    "size": obj["Size"],
                    "last_modified": obj["LastModified"].isoformat(),
                })
        except Exception:
            pass
        return result

    def get_file_size(self, filename: str) -> int:
        """Get file size in bytes."""
        try:
            resp = self.client.head_object(Bucket=self.bucket, Key=filename)
            return resp["ContentLength"]
        except Exception:
            return 0
