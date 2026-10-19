# List Files in Pure Storage FlashBlade S3 Bucket

## Overview

The `everpure_s3_bucket_list_files.py` script lists all objects stored in a Pure Storage FlashBlade S3 bucket. It supports pagination for large buckets, filtering by prefix, and optional detailed output with file sizes and timestamps.

## Prerequisites

- Python 3.12+
- boto3 library: `pip install boto3 botocore`
- Access to Pure Storage FlashBlade S3 endpoint
- Valid S3 access credentials

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

List all files in the bucket:
```bash
python day2/scripts/everpure_s3_bucket_list_files.py
```

Output:
```
INFO:__main__:Listing objects in bucket: hz0tpf-s3
  file1.txt
  folder/file2.csv
  data/report.pdf
INFO:__main__:Total: 3 objects, 524288 bytes
```

### List with Verbose Output

Show file sizes and modification timestamps:
```bash
python day2/scripts/everpure_s3_bucket_list_files.py -v
# or
python day2/scripts/everpure_s3_bucket_list_files.py --verbose
```

Output:
```
INFO:__main__:Listing objects in bucket: hz0tpf-s3
  file1.txt                                                       | Size:     262144 | Modified: 2026-07-16 10:30:45+00:00
  folder/file2.csv                                                | Size:     262144 | Modified: 2026-07-16 10:32:10+00:00
  data/report.pdf                                                 | Size:           0 | Modified: 2026-07-16 10:33:22+00:00
INFO:__main__:Total: 3 objects, 524288 bytes
```

### Filter by Prefix

List only files in a specific folder/prefix:
```bash
python day2/scripts/everpure_s3_bucket_list_files.py -p folder/
# or
python day2/scripts/everpure_s3_bucket_list_files.py --prefix data/
```

### Combine Options

List files in a folder with verbose output:
```bash
python day2/scripts/everpure_s3_bucket_list_files.py -p folder/ -v
```

### Enable Debug Logging

Show detailed debugging information:
```bash
python day2/scripts/everpure_s3_bucket_list_files.py -d
# or
python day2/scripts/everpure_s3_bucket_list_files.py --debug
```

## Command-line Options

```
-p, --prefix PATTERN    Filter objects by prefix (e.g., subfolder/)
-v, --verbose           Show file sizes and modification times
-d, --debug             Enable debug logging
-h, --help              Show help message and exit
```

## Examples

### List all files with sizes
```bash
python day2/scripts/everpure_s3_bucket_list_files.py --verbose
```

### List files in 'archive' folder
```bash
python day2/scripts/everpure_s3_bucket_list_files.py --prefix archive/
```

### List CSV files (filter manually after script runs)
```bash
python day2/scripts/everpure_s3_bucket_list_files.py | grep "\.csv"
```

### Combine prefix and verbose
```bash
python day2/scripts/everpure_s3_bucket_list_files.py -p backup/ -v
```

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

### Authentication Error

**Error:**
```
ClientError: An error occurred (InvalidAccessKeyId) when calling the ListObjectsV2 operation
```

**Solution:** Verify your access credentials:
- Check AWS_ACCESS_KEY_ID is correct
- Check AWS_SECRET_ACCESS_KEY is correct
- Ensure the user has ListBucket permissions

### Connection Timeout

**Error:**
```
Connection timeout or refused
```

**Solution:**
- Verify AWS_S3_ENDPOINT hostname is correct
- Check network connectivity to FlashBlade
- Verify firewall allows outbound HTTPS (port 443)

## Performance Considerations

- The script uses pagination to handle large buckets efficiently
- Pagination is automatic for buckets with >1000 objects
- Verbose output adds minimal overhead
- For very large buckets (millions of objects), consider filtering by prefix first

## Pagination

The script automatically handles pagination:
- Default max keys per page: 1000
- Automatic next page retrieval
- Total count displayed at end
- No manual pagination required

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error (missing env vars, connection error, etc.) |

## Related Documentation

- [Upload Files Script](everpure_s3_bucket_copy_file.md)
- [FlashBlade NFS Setup](../docs/flashblade_nfs_share_setup.md)
