# Vault Configuration Guide - Feature 2 (SaaS + CVA)

## Vault File Location
```
~/.config/cisco-ai-pods/vault.yaml
```

## Decrypting and Editing

### Step 1: Decrypt the Vault
```bash
ansible-vault edit ~/.config/cisco-ai-pods/vault.yaml
```

You'll be prompted for the vault password (stored in `~/.config/cisco-ai-pods/vault-password`)

### Step 2: Add CVA Credentials

After decryption, your vault file should have this structure. Add or modify the `intersight` section:

```yaml
# Intersight Configuration (Multi-Environment)
intersight:
  # SaaS Environment (required - you likely already have this)
  saas:
    endpoint: "https://intersight.com"
    apikey: "YOUR_SAAS_API_KEY_ID"
    secretkey: "YOUR_SAAS_API_SECRET_KEY"
  
  # CVA Environment (new - add this section)
  cva:
    endpoint: "https://your-cva-instance.example.com"
    apikey: "YOUR_CVA_API_KEY_ID"
    secretkey: "YOUR_CVA_API_SECRET_KEY"

# ... any other existing vault configurations
```

### Step 3: Save and Exit

When you save and exit (`:wq` in vim), Ansible will automatically re-encrypt the file.

## Configuration Values

### SaaS Credentials (Existing)
- **Endpoint**: `https://intersight.com`
- **API Key ID**: From Intersight portal (System > Settings > API Keys)
- **Secret Key**: Downloaded when API key created (keep safe!)

### CVA Credentials (New)
- **Endpoint**: URL of your CVA instance (e.g., `https://cva.internal.company.com`, `https://10.0.0.100`)
- **API Key ID**: From CVA's local API keys (might be different user/account than SaaS)
- **Secret Key**: Downloaded from CVA when API key created

## Important Notes

✅ **Do NOT commit vault.yaml** - It's encrypted, but keep it secure  
✅ **Keep vault-password safe** - Required to decrypt/edit vault.yaml  
✅ **Test connectivity** - After updating, test with: `--intersight-environment cva --check`  
✅ **API credentials isolated** - SaaS and CVA can have different API keys  
✅ **Different endpoints** - You can have multiple CVA instances by adding more entries (e.g., `cva-prod`, `cva-test`)  

## Example Full Vault Structure

```yaml
---
intersight:
  saas:
    endpoint: "https://intersight.com"
    apikey: "5a1234567890abcdef"
    secretkey: "-----BEGIN PRIVATE KEY-----\nMIIE..."
  cva:
    endpoint: "https://cva-instance.company.com"
    apikey: "5b9876543210fedcba"
    secretkey: "-----BEGIN PRIVATE KEY-----\nABCD..."

# Other vault sections (if any)
other_config:
  key: value
```

## Verification

After updating vault, verify the structure is correct:
```bash
# View just the intersight section (won't display secrets)
ansible-vault view ~/.config/cisco-ai-pods/vault.yaml | grep -A10 "^intersight:"
```

## Troubleshooting

### "Invalid YAML" error
- Check for missing colons or incorrect indentation
- Use online YAML validator: https://www.yamllint.com/

### "Permission denied" when editing
- Check file permissions: `ls -la ~/.config/cisco-ai-pods/vault.yaml`
- Should be readable: `chmod 600 ~/.config/cisco-ai-pods/vault.yaml`

### "Wrong password" error
- Verify vault-password file: `cat ~/.config/cisco-ai-pods/vault-password`
- If lost, create new one and re-encrypt vault (Ansible documentation)

## Next Steps

1. ✅ Decrypt and edit vault.yaml
2. ✅ Add CVA section with endpoint and credentials
3. ✅ Save and exit (Ansible will re-encrypt)
4. 🔄 Wait for Feature 2 implementation code
5. 🔄 Test with: `--intersight-environment cva --check`

---

**Once you've updated the vault**, let me know and I'll start implementing the Python code to:
- Load multi-environment credentials
- Detect target environment
- Query CVA schema
- Filter unsupported attributes
