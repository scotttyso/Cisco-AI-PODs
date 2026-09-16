# Cisco AI PODs - Day 2 Operations

This directory contains Day 2 operational tools, playbooks, and scripts for managing Pure Storage FlashBlade S3 buckets and other post-deployment tasks in the Cisco AI PODs environment.

## Table of Contents

1. [Overview](#overview)
2. [Directory Structure](#directory-structure)
3. [Quick Start](#quick-start)
4. [Documentation](#documentation)
5. [Scripts](#scripts)
6. [Playbooks](#playbooks)
7. [Prerequisites](#prerequisites)

## Overview

Day 2 operations encompass all post-deployment activities including:
- S3 bucket management (list, upload, download files)
- NFS share configuration
- Data migration and backup
- Monitoring and maintenance

## Directory Structure

```
day2/
├── README.md                          # This file
├── docs/                              # Documentation
│   ├── everpure_s3_bucket_list_files.md    # List files in S3 bucket
│   ├── everpure_s3_bucket_copy_file.md     # Upload files to S3 bucket
│   └── flashblade_nfs_share_setup.md       # NFS share setup guide
├── scripts/                           # Python automation scripts
│   ├── everpure_s3_bucket_list_files.py    # List S3 bucket contents
│   └── everpure_s3_bucket_copy_file.py     # Upload files to S3 bucket
└── playbooks/                         # Ansible playbooks
    └── (Day 2 operation playbooks)
```

## Quick Start

### 1. List Files in S3 Bucket

View all files stored in your FlashBlade S3 bucket:

```bash
# Set environment variables
export AWS_S3_ENDPOINT=flashblade.example.com
export AWS_ACCESS_KEY_ID=your-key
export AWS_SECRET_ACCESS_KEY=your-secret
export AWS_S3_BUCKET=your-bucket-name

# List files
python day2/scripts/everpure_s3_bucket_list_files.py -v
```

📖 [Full Documentation →](docs/everpure_s3_bucket_list_files.md)

### 2. Upload Files to S3 Bucket

Upload files to your FlashBlade S3 bucket:

```bash
# Upload with default filename
python day2/scripts/everpure_s3_bucket_copy_file.py /path/to/file.txt

# Upload with custom S3 key
python day2/scripts/everpure_s3_bucket_copy_file.py /path/to/file.txt -k custom-name.txt
```

📖 [Full Documentation →](docs/everpure_s3_bucket_copy_file.md)

### 3. Configure NFS Share

Step-by-step guide to create and configure NFS shares on FlashBlade:

📖 [Full Documentation →](../../docs/flashblade_nfs_share_setup.md)

## Documentation

### S3 Bucket Management

| Document | Purpose |
|----------|---------|
| [List Files in S3 Bucket](docs/everpure_s3_bucket_list_files.md) | List all objects, filter by prefix, view details |
| [Upload Files to S3 Bucket](docs/everpure_s3_bucket_copy_file.md) | Upload files with custom naming, organize by folder |
| [FlashBlade NFS Setup](../../docs/flashblade_nfs_share_setup.md) | Create and configure NFS exports |

Each document includes:
- Prerequisites and setup
- Environment variable configuration
- Usage examples
- Troubleshooting guide
- Advanced options

## Scripts

### List Files Script

**File:** `scripts/everpure_s3_bucket_list_files.py`

List all objects in a Pure Storage FlashBlade S3 bucket with pagination support.

**Quick Usage:**
```bash
python scripts/everpure_s3_bucket_list_files.py          # List all files
python scripts/everpure_s3_bucket_list_files.py -v       # With details
python scripts/everpure_s3_bucket_list_files.py -p data/ # Filter by prefix
```

**Features:**
- ✓ Automatic pagination for large buckets
- ✓ Filter by prefix (subdirectories)
- ✓ Display file sizes and timestamps
- ✓ Debug logging mode
- ✓ User-friendly error messages

📖 [Full Documentation →](docs/everpure_s3_bucket_list_files.md)

### Upload Files Script

**File:** `scripts/everpure_s3_bucket_copy_file.py`

Upload files to a Pure Storage FlashBlade S3 bucket.

**Quick Usage:**
```bash
python scripts/everpure_s3_bucket_copy_file.py file.txt              # Upload with filename
python scripts/everpure_s3_bucket_copy_file.py file.txt -k new.txt  # Custom S3 key
python scripts/everpure_s3_bucket_copy_file.py file.txt -k dir/file # To subdirectory
```

**Features:**
- ✓ Custom S3 object naming
- ✓ Organize files in subdirectories
- ✓ File validation (exists, readable)
- ✓ Automatic metadata tagging
- ✓ Comprehensive error handling

📖 [Full Documentation →](docs/everpure_s3_bucket_copy_file.md)

## Playbooks

Day 2 operational playbooks located in `playbooks/` directory:

- S3 bucket creation
- User provisioning
- Data migration tasks
- Backup and restore procedures

## Prerequisites

### Python Scripts

- Python 3.6 or later
- boto3 library:
  ```bash
  pip install boto3 botocore
  ```

### Environment Setup

Set these environment variables before running scripts:

```bash
export AWS_S3_ENDPOINT=flashblade-hostname.example.com
export AWS_ACCESS_KEY_ID=your-access-key-id
export AWS_SECRET_ACCESS_KEY=your-secret-access-key
export AWS_S3_BUCKET=bucket-name
```

### FlashBlade Access

- Valid S3 credentials created in FlashBlade
- Network access to FlashBlade S3 endpoint
- Appropriate IAM permissions (ListBucket, GetObject, PutObject)

## Common Tasks

### List all files in bucket
```bash
python scripts/everpure_s3_bucket_list_files.py -v
```

### Upload a data file
```bash
python scripts/everpure_s3_bucket_copy_file.py /data/export.csv
```

### Upload to organized folder structure
```bash
python scripts/everpure_s3_bucket_copy_file.py /data/export.csv -k exports/2026/export.csv
```

### Filter and view specific files
```bash
python scripts/everpure_s3_bucket_list_files.py -p backups/ -v
```

## Troubleshooting

### Missing Environment Variables
Scripts will display helpful instructions if environment variables are missing.

### SSL Certificate Errors
The scripts disable SSL verification by default for self-signed FlashBlade certificates.

### Authentication Issues
Verify AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are correct for your FlashBlade account.

**See individual script documentation for detailed troubleshooting:**
- [List Files Troubleshooting](docs/everpure_s3_bucket_list_files.md#troubleshooting)
- [Upload Files Troubleshooting](docs/everpure_s3_bucket_copy_file.md#troubleshooting)

## Support

For issues or questions:
1. Check the script-specific documentation
2. Review the troubleshooting sections
3. Run with debug flag: `-d` or `--debug`
4. Contact your FlashBlade administrator

## Related Documentation

- [Main Documentation](../../docs/README.md)
- [FlashBlade NFS Setup](../../docs/flashblade_nfs_share_setup.md)
- [Playbooks](../playbooks/README.md)
- [Pure Storage FlashBlade Documentation](https://purestorage.com)

---

**Last Updated:** 2026-07-16
