using Amazon.DynamoDBv2;
using Amazon.DynamoDBv2.Model;
using Humbugg.Api.Models;

namespace Humbugg.Api.Data;

internal interface ITemplateRepository
{
    Task<IReadOnlyList<ExchangeTemplate>> ListAsync(string userId, CancellationToken ct);
    Task<ExchangeTemplate?> GetAsync(string userId, string id, CancellationToken ct);
    Task PutAsync(string userId, ExchangeTemplate value, CancellationToken ct);
    Task DeleteAsync(string userId, string id, CancellationToken ct);
}
internal sealed class TemplateRepository(IAmazonDynamoDB db, HumbuggSettings settings) : ITemplateRepository
{
    public async Task<IReadOnlyList<ExchangeTemplate>> ListAsync(string userId, CancellationToken ct) =>
        (await db.QueryAsync(new QueryRequest { TableName = settings.TemplatesTable, KeyConditionExpression = "user_id = :u", ExpressionAttributeValues = new() { [":u"] = DynamoValues.S(userId) } }, ct)).Items.Select(Read).ToList();
    public async Task<ExchangeTemplate?> GetAsync(string userId, string id, CancellationToken ct) { var r = await db.GetItemAsync(settings.TemplatesTable, Key(userId, id), true, ct); return r.IsItemSet ? Read(r.Item) : null; }
    public Task PutAsync(string userId, ExchangeTemplate v, CancellationToken ct) => db.PutItemAsync(new PutItemRequest { TableName = settings.TemplatesTable, Item = Write(userId, v) }, ct);
    public Task DeleteAsync(string userId, string id, CancellationToken ct) => db.DeleteItemAsync(settings.TemplatesTable, Key(userId, id), ct);
    internal static Dictionary<string, AttributeValue> Key(string u, string id) => new() { ["user_id"] = DynamoValues.S(u), ["template_id"] = DynamoValues.S(id) };
    private static Dictionary<string, AttributeValue> Write(string u, ExchangeTemplate v) => new()
    {
        ["user_id"] = DynamoValues.S(u),
        ["template_id"] = DynamoValues.S(v.TemplateId),
        ["name"] = DynamoValues.S(v.Name),
        ["exchange_name"] = DynamoValues.S(v.ExchangeName),
        ["description"] = DynamoValues.S(v.Description),
        ["deadline_days_before_event"] = DynamoValues.N(v.SignupDeadlineDaysBeforeEvent),
        ["wishlist_prompt"] = DynamoValues.S(v.WishlistPrompt),
        ["exclusions_policy"] = DynamoValues.S(v.ExclusionsPolicy),
        ["reminders"] = DynamoValues.S(System.Text.Json.JsonSerializer.Serialize(v.ReminderPreferences)),
        ["customization"] = DynamoValues.S(System.Text.Json.JsonSerializer.Serialize(v.Customization)),
        ["prior_participants"] = DynamoValues.S(System.Text.Json.JsonSerializer.Serialize(v.PriorParticipants)),
        ["source_group_id"] = DynamoValues.S(v.SourceGroupId ?? ""),
        ["created_at"] = DynamoValues.S(v.CreatedAt),
        ["updated_at"] = DynamoValues.S(v.UpdatedAt)
    };
    private static ExchangeTemplate Read(IReadOnlyDictionary<string, AttributeValue> i) => new(
        i.String("template_id"), i.String("name"), i.String("exchange_name"), i.String("description"),
        (int)(i.Long("deadline_days_before_event") ?? 0), i.String("wishlist_prompt"), i.String("exclusions_policy", "none"),
        System.Text.Json.JsonSerializer.Deserialize<ReminderSettings>(i.String("reminders")) ?? new(ReminderState.Stopped, true, true, 3, 9, 20),
        System.Text.Json.JsonSerializer.Deserialize<ExchangeCustomization>(i.String("customization")) ?? new(),
        System.Text.Json.JsonSerializer.Deserialize<IReadOnlyList<TemplateParticipant>>(i.String("prior_participants")) ?? [],
        string.IsNullOrEmpty(i.String("source_group_id")) ? null : i.String("source_group_id"), i.String("created_at"), i.String("updated_at"));
}
