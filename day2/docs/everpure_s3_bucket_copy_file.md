# Upload File to Pure Storage FlashBlade S3 Bucket

## Overview

The `everpure_s3_bucket_copy_file.py` script uploads files to a Pure Storage FlashBlade S3 bucket. It supports custom S3 object naming, subdirectory uploads, and includes comprehensive error handling with user-friendly feedback.

## Prerequisites

- Python 3.12+
- boto3 library: `pip install boto3 botocore`
- Access to Pure Storage FlashBlade S3 endpoint
- Valid S3 access credentials with write permissions

## Environment Variables

The script requires the following environment variables:

| Variable | Description | Example |
|----------|-------------|---------|
| `AWS_S3_ENDPOINT` | FlashBlade S3 endpoint hostname | `flashblade.example.com` |
| `AWS_ACCESS_KEY_ID` | S3 access key ID | `PSFBXXXXX...` |
| `AWS_SECRET_ACCESS_KEY` | S3 secret access key | (sensitive data) |
| `AWS_S3_BUCKET` | S3 bucket name | `hz0tpf-s3` |

### Setting Environment Variables

Set all variables at once:
```bash
export AWS_S3_ENDPOINT=dcmaistpur002-vl1504.edc.nam.gm.com
export AWS_ACCESS_KEY_ID=your-access-key
export AWS_SECRET_ACCESS_KEY=your-secret-key
export AWS_S3_BUCKET=your-bucket-name
```

Or set individually:
```bash
export AWS_S3_ENDPOINT=dcmaistpur002-vl1504.edc.nam.gm.com
export AWS_ACCESS_KEY_ID=your-access-key
export AWS_SECRET_ACCESS_KEY=your-secret-key
export AWS_S3_BUCKET=your-bucket-name
```

## Usage

### Basic Usage

Upload a file using its filename as the S3 object key:
```bash
python day2/scripts/everpure_s3_bucket_copy_file.py /path/to/file.txt
```

Output:
```
INFO:__main__:Uploading file.txt (1024 bytes) to s3://hz0tpf-s3/file.txt
✓ Successfully uploaded to s3://hz0tpf-s3/file.txt
```

### Upload with Custom S3 Key

Upload a file with a different name in S3:
```bash
python day2/scripts/everpure_s3_bucket_copy_file.py /path/to/file.txt -k custom-name.txt
# or
python day2/scripts/everpure_s3_bucket_copy_file.py /path/to/file.txt --key custom-name.txt
```

### Upload to Subdirectory

Upload a file to a specific folder path in S3:
```bash
python day2/scripts/everpure_s3_bucket_copy_file.py /path/to/file.txt -k archive/2026/file.txt
```

### Enable Debug Logging

Show detailed debugging information:
```bash
python day2/scripts/everpure_s3_bucket_copy_file.py /path/to/file.txt -d
# or
python day2/scripts/everpure_s3_bucket_copy_file.py /path/to/file.txt --debug
```

## Command-line Options

```
filename                Positional argument - local file path to upload
-k, --key KEY           S3 object key (defaults to filename)
-d, --debug             Enable debug logging
-h, --help              Show help message and exit
```

## Examples

### Upload a CSV file
```bash
python day2/scripts/everpure_s3_bucket_copy_file.py /tmp/data.csv
```

### Upload and rename
```bash
python day2/scripts/everpure_s3_bucket_copy_file.py /home/user/report.pdf -k reports/2026-07-16-report.pdf
```

### Upload to nested folder
```bash
python day2/scripts/everpure_s3_bucket_copy_file.py /data/backup.tar.gz -k backups/daily/backup.tar.gz
```

### Upload with debug output
```bash
python day2/scripts/everpure_s3_bucket_copy_file.py /tmp/test.txt --debug
```

### Batch upload multiple files
```bash
#!/bin/bash
for file in /data/exports/*.csv; do
  python day2/scripts/everpure_s3_bucket_copy_file.py "$file" -k "exports/$(basename "$file")"
done
```

## Metadata

The script automatically adds metadata to uploaded files:
- `uploaded-by`: `everpure-s3-script` (identifies the upload source)

This metadata can be queried later for audit purposes.

## Troubleshooting

### SSL Certificate Verification Error

**Error:**
```
SSLError: SSL validation failed
```

**Solution:** The script disables SSL verification by default for self-signed certificates. If you still get this error, ensure:
- FlashBlade endpoint is reachable
- Network connectivity is working
- Firewall rules allow HTTPS traffic on port 443

### Missing Environment Variables

**Error:**
```
Missing environment variables: AWS_S3_ENDPOINT, AWS_ACCESS_KEY_ID, ...
```

**Solution:** Set all required environment variables:
```bash
export AWS_S3_ENDPOINT=your-endpoint
export AWS_ACCESS_KEY_ID=your-key
export AWS_SECRET_ACCESS_KEY=your-secret
export AWS_S3_BUCKET=your-bucket
```

### File Not Found

**Error:**
```
File not found: /path/to/file.txt
```

**Solution:** 
- Verify the file path is correct
- Check file exists: `ls -l /path/to/file.txt`
- Use absolute paths for clarity

### Permission Denied

**Error:**
```
File is not readable: /path/to/file.txt
```

**Solution:**
- Check file permissions: `ls -l /path/to/file.txt`
- Ensure current user can read the file: `chmod u+r /path/to/file.txt`

### Authentication Error

**Error:**
```
ClientError: An error occurred (InvalidAccessKeyId) when calling the PutObject operation
```

**Solution:** Verify your access credentials:
- Check AWS_ACCESS_KEY_ID is correct
- Check AWS_SECRET_ACCESS_KEY is correct
- Ensure the user has PutObject permissions

### Connection Timeout

**Error:**
```
Connection timeout or refused
```

**Solution:**
- Verify AWS_S3_ENDPOINT hostname is correct
- Check network connectivity to FlashBlade
- Verify firewall allows outbound HTTPS (port 443)

### Access Denied / NoSuchBucket

**Error:**
```
ClientError: An error occurred (NoSuchBucket)
```

**Solution:**
- Verify AWS_S3_BUCKET name is correct
- Confirm bucket exists on FlashBlade
- Ensure credentials have bucket access

## File Size Limits

- Maximum file size: Depends on FlashBlade configuration
- Typical limits: Terabytes
- For very large files (>5GB), consider:
  - Multipart upload (future enhancement)
  - Splitting into chunks
  - Direct FlashBlade tools for bulk transfer

## Performance Tips

- **Batch uploads**: Use shell loop for multiple files
- **Large files**: Upload during off-peak hours
- **Network**: Use wired connection for large transfers
- **Verify**: List bucket contents after upload to confirm

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error (file not found, auth error, connection error, etc.) |

## Related Documentation

- [List Files Script](everpure_s3_bucket_list_files.md)
- [FlashBlade NFS Setup](../docs/flashblade_nfs_share_setup.md)
