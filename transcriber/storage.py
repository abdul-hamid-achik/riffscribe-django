"""
Custom storage backend for MinIO with signed URL support
"""
import boto3
from django.conf import settings
from storages.backends.s3boto3 import S3Boto3Storage
from botocore.exceptions import ClientError
import logging

logger = logging.getLogger(__name__)


class SignedUrlMixin:
    """Mixin to provide signed URL functionality"""
    
    def generate_signed_url(self, name, expiration=3600, method='GET'):
        """
        Generate a signed URL for secure access to a file
        
        Args:
            name: File name/path in storage
            expiration: URL expiration time in seconds (default: 1 hour)
            method: HTTP method ('GET' for download, 'PUT' for upload)
            
        Returns:
            Signed URL string or None if error
        """
        try:
            # Create S3 client if not exists
            if not hasattr(self, '_signed_client'):
                self._signed_client = boto3.client(
                    's3',
                    endpoint_url=getattr(settings, 'AWS_S3_ENDPOINT_URL'),
                    aws_access_key_id=getattr(settings, 'AWS_ACCESS_KEY_ID'),
                    aws_secret_access_key=getattr(settings, 'AWS_SECRET_ACCESS_KEY'),
                    use_ssl=getattr(settings, 'AWS_S3_USE_SSL', True),
                    verify=getattr(settings, 'AWS_S3_VERIFY', True)
                )
            
            # Generate signed URL
            if method == 'GET':
                response = self._signed_client.generate_presigned_url(
                    'get_object',
                    Params={
                        'Bucket': self.bucket_name,
                        'Key': name
                    },
                    ExpiresIn=expiration
                )
            elif method == 'PUT':
                response = self._signed_client.generate_presigned_url(
                    'put_object',
                    Params={
                        'Bucket': self.bucket_name,
                        'Key': name
                    },
                    ExpiresIn=expiration
                )
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            # Fix localhost URL for development
            if response and hasattr(settings, 'DEBUG') and settings.DEBUG:
                if 'storage:' in response:
                    response = response.replace('storage:', 'localhost:')
                
            return response
            
        except ClientError as e:
            logger.error(f"Failed to generate signed URL for {name}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error generating signed URL for {name}: {e}")
            return None


class SecureMediaStorage(SignedUrlMixin, S3Boto3Storage):
    """
    Secure media storage with signed URL support for audio files
    """
    bucket_name = getattr(settings, 'AWS_STORAGE_BUCKET_NAME', 'riffscribe-media')
    location = 'media'
    default_acl = 'private'  # Make files private by default
    file_overwrite = False
    custom_domain = False
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Override to make files private for signed URL access
        self.default_acl = 'private'
    
    def url(self, name, parameters=None, expire=3600, http_method=None):
        """
        Override to return signed URLs instead of public URLs
        """
        # For development with localhost endpoint, return public URL
        # In production, this would return signed URLs
        if settings.DEBUG and hasattr(settings, 'AWS_S3_ENDPOINT_URL'):
            endpoint = getattr(settings, 'AWS_S3_ENDPOINT_URL', '')
            if 'localhost:' in endpoint or '127.0.0.1:' in endpoint:
                # Return public URL for local development
                return super().url(name)
        
        # Generate signed URL for production or non-localhost endpoints
        signed_url = self.generate_signed_url(name, expiration=expire)
        if signed_url:
            return signed_url
        
        # Fallback to standard URL if signed URL generation fails
        logger.warning(f"Failed to generate signed URL for {name}, falling back to standard URL")
        return super().url(name)


class PublicMediaStorage(S3Boto3Storage):
    """
    Public media storage for files that should be publicly accessible
    """
    bucket_name = getattr(settings, 'AWS_STORAGE_BUCKET_NAME', 'riffscribe-media')
    location = 'public'
    default_acl = 'public-read'
    file_overwrite = False
