# Governance

All access is defined in [governance/policy.yml](../governance/policy.yml) and applied by the `apply_governance` task after every pipeline update ([ADR 0006](adr/0006-governance-as-code.md)).

## Who sees what

| Group | landing, bronze | silver | gold | governance |
| --- | --- | --- | --- | --- |
| `ucleany-data-engineers` | everything | everything, in clear | everything | everything |
| `ucleany-analysts` | no access | read, personal data masked | read, every zone | no access |
| `ucleany-customer-care` | no access | read, contact details in clear | no access | no access |
| `ucleany-leadership` | no access | no access | read, every zone | no access |
| `ucleany-zone-managers` | no access | no access | read, own zones only | no access |
| `ucleany-powerbi` | no access | no access | read, every zone (RLS in the model) | read |

## Personal data

| Table | Column | Class | Masked as |
| --- | --- | --- | --- |
| `silver.customers` | `first_name`, `last_name` | name | `M.` |
| `silver.customers` | `email`, `email_raw` | email | `m***@gmail.com` |
| `silver.customers` | `phone_e164` | phone | `+39 *** *** 21` |
| `silver.customers` | `email_hash` | pseudonymous | not masked: used for identity matching |
| `silver.cleaners` | `first_name`, `last_name`, `email`, `phone_e164` | name, email, phone | as above |
| `silver.reviews` | `comment` | free_text | `[redacted]` |
| `bronze.customers`, `bronze.cleaners`, `bronze.reviews` | raw equivalents | tagged only | schema closed to all but engineers |

Every classified column carries the Unity Catalog tag `pii=<class>`, every table that holds one `contains_pii=true`, and every schema a `layer` tag, so Catalog Explorer search and the system tables answer "where is personal data?" directly.

Gold contains none of these columns. A test fails if any gold table gains one.

## Zone managers

`governance.zone_access` maps each zone manager to their zones. Two things read it:

- the Unity Catalog row filter `governance.zone_filter` on `gold.fct_bookings`, `gold.fct_payments` and `gold.fct_reviews`, for SQL and notebook users;
- the `Zone Manager` role of the Power BI model, for report users.

## Changing access

1. Edit `governance/policy.yml` and open a pull request. The tests check the policy (unknown groups, unmasked personal data, columns that no longer exist).
2. After merge, the next job run applies it. Grants made by hand to a policy group and missing from the file are revoked.
