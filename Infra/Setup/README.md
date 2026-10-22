# Infrastructure Automation (Terraform + Proxmox VE)

## Standard Execution Workflow

```bash
terraform init
terraform validate
source .env
terraform plan -parallelism=1 -out=tfplan
terraform apply -parallelism=1 "tfplan"
terraform destroy -parallelism=1
```

> **Important Notes:**
>
> - Always run with `-parallelism=1` because simultaneous jobs can cause file locks in the underlying storage, resulting in Terraform crashes and corrupt VMs.

> _Info:_
>
> - `vm_protection = true` prevents accidental deletion of critical production VMs.
