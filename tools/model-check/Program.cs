// Loads the Power BI semantic model from its TMDL folder with the Analysis Services
// object model (TOM) and checks it against the team's modelling rules. Optionally
// checks that every field a report visual uses exists in the model.
//
//   dotnet run --project tools/model-check -- powerbi/Ucleany.SemanticModel/definition \
//       --report powerbi/Ucleany.Report/definition
//
// Exit code 0 when the model loads and every rule passes, 1 otherwise.

using System.Text.Json;
using System.Text.RegularExpressions;
using Microsoft.AnalysisServices.Tabular;

if (args.Length == 0)
{
    Console.Error.WriteLine("usage: model-check <tmdl folder> [--report <report definition folder>]");
    return 2;
}

var tmdlPath = args[0];
var reportIdx = Array.IndexOf(args, "--report");
var reportPath = reportIdx >= 0 && reportIdx + 1 < args.Length ? args[reportIdx + 1] : null;

Database database;
try
{
    database = TmdlSerializer.DeserializeDatabaseFromFolder(tmdlPath);
}
catch (Exception e)
{
    Console.Error.WriteLine($"FAIL  TMDL does not load: {e.Message}");
    return 1;
}

var model = database.Model;
var issues = new List<string>();
void Fail(string rule, string obj, string message) => issues.Add($"[{rule}] {obj}: {message}");

var measures = model.Tables.SelectMany(t => t.Measures).ToDictionary(m => m.Name, StringComparer.OrdinalIgnoreCase);
var tables = model.Tables.ToDictionary(t => t.Name, StringComparer.OrdinalIgnoreCase);

// ---------------------------------------------------------------- model-level rules

if (!model.DiscourageImplicitMeasures)
    Fail("explicit-measures", "Model", "set discourageImplicitMeasures so report authors use the governed measures");

var dateTables = model.Tables.Where(t => t.DataCategory == "Time").ToList();
if (dateTables.Count != 1)
    Fail("date-table", "Model", $"expected exactly one table marked as date table, found {dateTables.Count}");
else if (!dateTables[0].Columns.Any(c => c.IsKey && c.DataType == DataType.DateTime))
    Fail("date-table", dateTables[0].Name, "the date table needs a dateTime column marked isKey");

// ---------------------------------------------------------------- tables and columns

foreach (var table in model.Tables)
{
    var isCalcGroup = table.CalculationGroup != null;
    if (string.IsNullOrWhiteSpace(table.Description))
        Fail("description", $"'{table.Name}'", "table has no description");

    foreach (var column in table.Columns.Where(c => c.Type != ColumnType.RowNumber))
    {
        var name = $"'{table.Name}'[{column.Name}]";
        if (!column.IsHidden && Regex.IsMatch(column.Name, "_|^[a-z]"))
            Fail("business-names", name, "visible columns need business names, not source names");

        var isIdentifier = Regex.IsMatch(column.Name, @"\b(ID|SK|Key)$");
        if (isIdentifier && column.SummarizeBy != AggregateFunction.None)
            Fail("no-summarize-ids", name, "identifier columns must have summarizeBy: none");

        var isMoney = column.Name.EndsWith(" EUR") || (column.FormatString ?? "").Contains('€');
        if (isMoney && column.DataType != DataType.Decimal)
            Fail("money-is-decimal", name, $"money columns must be fixed decimal, found {column.DataType}");

        if (column.DataType == DataType.Double && !isCalcGroup)
            Fail("no-floating-point", name, "use decimal or int64; double causes rounding differences in totals");
    }

    if (!isCalcGroup && table.Partitions.Count == 0)
        Fail("partition", $"'{table.Name}'", "table has no partition");

    foreach (var partition in table.Partitions)
    {
        if (partition.Source is MPartitionSource m && m.Expression.Contains("Table.SelectColumns") is false)
            Fail("select-columns", $"'{table.Name}'", "import partitions must list their columns with Table.SelectColumns");
    }
}

// ---------------------------------------------------------------- relationships

foreach (var rel in model.Relationships.OfType<SingleColumnRelationship>())
{
    var name = $"'{rel.FromTable.Name}'[{rel.FromColumn.Name}] -> '{rel.ToTable.Name}'[{rel.ToColumn.Name}]";
    if (rel.CrossFilteringBehavior == CrossFilteringBehavior.BothDirections)
        Fail("no-bidirectional", name, "bidirectional filters make results depend on model paths; use a measure instead");
    if (!rel.FromColumn.IsHidden)
        Fail("hide-foreign-keys", name, "the many-side column should be hidden so users filter through the dimension");
    if (rel.FromColumn.DataType != rel.ToColumn.DataType)
        Fail("relationship-types", name, $"{rel.FromColumn.DataType} vs {rel.ToColumn.DataType}");
}

// ---------------------------------------------------------------- measures and DAX

foreach (var measure in measures.Values)
{
    var name = $"[{measure.Name}]";
    if (string.IsNullOrWhiteSpace(measure.Description))
        Fail("description", name, "measure has no description");
    if (string.IsNullOrWhiteSpace(measure.FormatString) && measure.FormatStringDefinition == null)
        Fail("format-string", name, "measure has no format string");
    if (string.IsNullOrWhiteSpace(measure.DisplayFolder))
        Fail("display-folder", name, "measure is not in a display folder");
    if (Regex.IsMatch(StripDax(measure.Expression), @"(?<![/*])/(?![/*])"))
        Fail("use-divide", name, "use DIVIDE() instead of the / operator to handle division by zero");
    CheckReferences(name, measure.Expression);
}

foreach (var table in model.Tables.Where(t => t.CalculationGroup != null))
    foreach (var item in table.CalculationGroup.CalculationItems)
        CheckReferences($"'{table.Name}'[{item.Name}]", item.Expression);

foreach (var role in model.Roles)
{
    if (role.ModelPermission != ModelPermission.Read)
        Fail("roles", $"role '{role.Name}'", "roles must be read-only");
    foreach (var permission in role.TablePermissions)
        CheckReferences($"role '{role.Name}' on '{permission.Table.Name}'", permission.FilterExpression);
}

// ---------------------------------------------------------------- report fields

var visuals = 0;
if (reportPath != null)
{
    foreach (var file in Directory.EnumerateFiles(reportPath, "*.json", SearchOption.AllDirectories))
    {
        using var doc = JsonDocument.Parse(File.ReadAllText(file));
        if (file.EndsWith("visual.json")) visuals++;
        WalkReport(Path.GetRelativePath(reportPath, file), doc.RootElement, null);
    }
}

// ---------------------------------------------------------------- summary

var columns = model.Tables.Sum(t => t.Columns.Count(c => c.Type != ColumnType.RowNumber));
Console.WriteLine($"Model loaded: {model.Tables.Count} tables, {columns} columns, {measures.Count} measures, "
    + $"{model.Relationships.Count} relationships, {model.Roles.Count} roles, "
    + $"{model.Tables.Sum(t => t.CalculationGroup?.CalculationItems.Count ?? 0)} calculation items");
if (reportPath != null)
    Console.WriteLine($"Report checked: {visuals} visuals");

if (issues.Count == 0)
{
    Console.WriteLine("All modelling rules pass.");
    return 0;
}

foreach (var issue in issues)
    Console.WriteLine("FAIL  " + issue);
Console.WriteLine($"{issues.Count} rule violation(s).");
return 1;

// ---------------------------------------------------------------- helpers

// Removes comments and string literals so that references and operators inside them are ignored.
static string StripDax(string dax)
{
    dax = Regex.Replace(dax, @"/\*.*?\*/", " ", RegexOptions.Singleline);
    dax = Regex.Replace(dax, @"(//|--)[^\n]*", " ");
    return Regex.Replace(dax, "\"(?:[^\"]|\"\")*\"", "\"\"");
}

// 'Table'[Name] and Table[Name] must be columns of that table; [Name] alone must be a measure.
void CheckReferences(string owner, string expression)
{
    var dax = StripDax(expression);
    var refs = Regex.Matches(dax, @"(?:'(?<table>(?:[^']|'')+)'|(?<table>[A-Za-z_][A-Za-z0-9_]*))?\[(?<name>[^\]]+)\]");
    foreach (Match r in refs)
    {
        var tableName = r.Groups["table"].Success ? r.Groups["table"].Value.Replace("''", "'") : null;
        var objectName = r.Groups["name"].Value;
        if (tableName == null)
        {
            if (!measures.ContainsKey(objectName))
                Fail("references", owner, $"[{objectName}] is not a measure (qualify column references with their table)");
            continue;
        }
        if (!tables.TryGetValue(tableName, out var table))
        {
            Fail("references", owner, $"table '{tableName}' does not exist");
            continue;
        }
        if (table.Measures.Contains(objectName))
            Fail("references", owner, $"measure [{objectName}] should not be qualified with a table name");
        else if (!table.Columns.Contains(objectName))
            Fail("references", owner, $"'{tableName}'[{objectName}] does not exist");
    }

    foreach (Match quoted in Regex.Matches(dax, @"'((?:[^']|'')+)'"))
    {
        var tableName = quoted.Groups[1].Value.Replace("''", "'");
        if (!tables.ContainsKey(tableName))
            Fail("references", owner, $"table '{tableName}' does not exist");
    }
}

// Visual queries reference fields as { "Column"|"Measure"|"Hierarchy": { "Expression": { "SourceRef": { "Entity": T } }, "Property": P } }.
void WalkReport(string file, JsonElement element, string? kind)
{
    if (element.ValueKind == JsonValueKind.Array)
    {
        foreach (var child in element.EnumerateArray()) WalkReport(file, child, null);
        return;
    }
    if (element.ValueKind != JsonValueKind.Object) return;

    if (kind != null
        && element.TryGetProperty("Property", out var property)
        && element.TryGetProperty("Expression", out var expression)
        && expression.TryGetProperty("SourceRef", out var sourceRef)
        && sourceRef.TryGetProperty("Entity", out var entity))
    {
        var tableName = entity.GetString()!;
        var fieldName = property.GetString()!;
        if (!tables.TryGetValue(tableName, out var table))
            Fail("report-fields", file, $"table '{tableName}' does not exist in the model");
        else if (kind == "Measure" && !table.Measures.Contains(fieldName))
            Fail("report-fields", file, $"measure '{tableName}'[{fieldName}] does not exist");
        else if (kind == "Column" && !table.Columns.Contains(fieldName))
            Fail("report-fields", file, $"column '{tableName}'[{fieldName}] does not exist");
        else if (kind == "Hierarchy" && !table.Hierarchies.Contains(fieldName))
            Fail("report-fields", file, $"hierarchy '{tableName}'.{fieldName} does not exist");
    }

    foreach (var child in element.EnumerateObject())
    {
        var childKind = child.Name is "Column" or "Measure" or "Hierarchy" ? child.Name : null;
        WalkReport(file, child.Value, childKind);
    }
}
