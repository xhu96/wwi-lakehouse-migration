# Ucleany semantic model and report

A Power BI Project (PBIP): the semantic model in TMDL, the report in the PBIR folder format. Everything here is plain text, reviewed in pull requests and checked in CI.

```
Ucleany.pbip                 open this in Power BI Desktop
Ucleany.SemanticModel/       tables, measures, relationships, roles (TMDL)
Ucleany.Report/              four report pages (PBIR)
```

## Model

- **Source:** the `gold` schema of a Databricks SQL warehouse, import mode, plus `governance.zone_access` for row-level security.
- **Star schema:** `Bookings`, `Payments`, `Reviews`, `Marketing Spend` and `Cleaner Monthly` facts; `Date`, `Zone`, `Service`, `Channel`, `Customer` and `Cleaner` dimensions (the last two SCD type 2); `Cohorts` for the retention matrix.
- **35 measures** in the `Metrics` table, by display folder: Bookings, Revenue, Customers, Marketing, Payments, Quality, Cleaners, Retention. Each has a description that matches [docs/data-model.md](../docs/data-model.md).
- **Time Intelligence** calculation group: Current, MTD, YTD, Previous Month, MoM Change, MoM %, Rolling 3M, for any measure.
- **Roles:** `Leadership` sees everything; `Zone Manager` sees only the zones assigned in `governance.zone_access`, the same table behind the Unity Catalog row filter.
- **Payments by two dates:** active relationship on service date, as the legacy report did; `[Cash Collected (Payment Date)]` uses the inactive one for cash-flow views.

## Report

| Page | Answers |
| --- | --- |
| Overview | How big are we, how fast are we growing, where does GMV come from? |
| Customers | What does a customer cost by channel, and do they come back? |
| Cleaners | Are cleaners busy enough, how much do they earn, how good is the service? |
| Migration checks | What did the legacy reports get wrong, and how much? |

## Open it

1. Run the lakehouse job once so `gold` and `governance` exist ([README](../README.md#on-databricks-free-edition-works)).
2. Open `Ucleany.pbip` in Power BI Desktop (a version that supports PBIR; on older versions enable *Store reports using enhanced metadata format* under Preview features).
3. *Transform data → Edit parameters*: set `DatabricksHost` and `DatabricksHttpPath` from the SQL warehouse's *Connection details* tab, and `DatabricksCatalog`.
4. Sign in with a personal access token or Microsoft Entra ID when prompted, then *Refresh*.
5. *Modeling → View as → Zone Manager* with *Other user* `manager.centro@ucleany.example` shows the four central zones only.

## Checks in CI

`tools/model-check` loads the model with the Analysis Services object model (TOM) and fails the build when:

- the TMDL does not load;
- a measure has no description, format string or display folder, or divides with `/` instead of `DIVIDE`;
- a table has no description, or a visible column has a source-style name;
- a relationship key on the many side is visible, a relationship is bidirectional, or its columns have different types;
- money is not fixed decimal, an identifier is summarised, or there is not exactly one marked date table;
- DAX in a measure, calculation item or role refers to a table, column or measure that does not exist, or uses a qualified measure or unqualified column reference;
- a report visual uses a field that does not exist in the model.

```bash
dotnet run --project tools/model-check -- powerbi/Ucleany.SemanticModel/definition --report powerbi/Ucleany.Report/definition
```
