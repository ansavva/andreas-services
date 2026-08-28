using Amazon.DynamoDBv2;
using Amazon.DynamoDBv2.Model;
using Humbugg.Api.Models;

namespace Humbugg.Api.Data;

internal interface IGroupRepository
{
    Task<GroupRecord?> GetAsync(string groupId, CancellationToken cancellationToken = default);
    Task<GroupRecord> CreateAsync(GroupRecord group, CancellationToken cancellationToken = default);
    Task<GroupRecord> UpdateAsync(string groupId, IReadOnlyDictionary<string, AttributeValue> fields, GroupStatus? expectedStatus = null, CancellationToken cancellationToken = default);
    Task DeleteAsync(string groupId, CancellationToken cancellationToken = default);
    Task CreateDrawAsync(string groupId, IReadOnlyDictionary<string, string> assignments, string actorUserId, CancellationToken cancellationToken = default);
    Task<DrawRecord?> GetDrawAsync(string groupId, CancellationToken cancellationToken = default);
    Task ResetDrawAsync(string groupId, CancellationToken cancellationToken = default);
    Task SaveLateProposalAsync(
        string groupId,
        string expectedDrawId,
        LateParticipantProposalRecord proposal,
        CancellationToken cancellationToken = default) =>
        throw new NotSupportedException("This group repository does not support late-participant proposals.");
    Task<string> ApplyLateProposalAsync(
        string groupId,
        string expectedDrawId,
        LateParticipantProposalRecord proposal,
        CancellationToken cancellationToken = default) =>
        throw new NotSupportedException("This group repository does not support late-participant proposals.");
}

internal sealed class GroupRepository(IAmazonDynamoDB db, HumbuggSettings settings) : IGroupRepository
{
    public async Task<GroupRecord?> GetAsync(string groupId, CancellationToken cancellationToken = default)
    {
        var response = await db.GetItemAsync(new GetItemRequest
        {
            TableName = settings.GroupsTable,
            Key = Key(groupId),
            ConsistentRead = true
        }, cancellationToken);
        return response.IsItemSet ? Read(response.Item) : null;
    }

    public async Task<GroupRecord> CreateAsync(GroupRecord group, CancellationToken cancellationToken = default)
    {
        await db.PutItemAsync(new PutItemRequest
        {
            TableName = settings.GroupsTable,
            Item = Write(group),
            ConditionExpression = "attribute_not_exists(group_id)"
        }, cancellationToken);
        return group;
    }

    public async Task<GroupRecord> UpdateAsync(string groupId, IReadOnlyDictionary<string, AttributeValue> fields, GroupStatus? expectedStatus = null, CancellationToken cancellationToken = default)
    {
        var names = new Dictionary<string, string>();
        var values = new Dictionary<string, AttributeValue>();
        var setters = new List<string>();
        var index = 0;
        foreach (var (name, value) in fields)
        {
            names[$"#n{index}"] = name;
            values[$":v{index}"] = value;
            setters.Add($"#n{index} = :v{index}");
            index++;
        }
        names["#updated"] = "updated_at";
        values[":updated"] = DynamoValues.S(DateTimeOffset.UtcNow.ToString("O"));
        setters.Add("#updated = :updated");

        var request = new UpdateItemRequest
        {
            TableName = settings.GroupsTable,
            Key = new() { ["group_id"] = DynamoValues.S(groupId) },
            UpdateExpression = $"SET {string.Join(", ", setters)}",
            ExpressionAttributeNames = names,
            ExpressionAttributeValues = values,
            ReturnValues = ReturnValue.ALL_NEW,
            ConditionExpression = "attribute_exists(group_id)"
        };
        if (expectedStatus is not null)
        {
            names["#status"] = "status";
            values[":expected"] = DynamoValues.S(Status(expectedStatus.Value));
            request.ConditionExpression += " AND #status = :expected";
        }
        var response = await db.UpdateItemAsync(request, cancellationToken);
        return Read(response.Attributes);
    }

    public async Task DeleteAsync(string groupId, CancellationToken cancellationToken = default)
    {
        await db.TransactWriteItemsAsync(new TransactWriteItemsRequest
        {
            TransactItems =
            [
                new() { Delete = new Delete { TableName = settings.GroupsTable, Key = Key(groupId) } },
                new() { Delete = new Delete { TableName = settings.DrawsTable, Key = Key(groupId) } }
            ]
        }, cancellationToken);
    }

    public async Task CreateDrawAsync(string groupId, IReadOnlyDictionary<string, string> assignments, string actorUserId, CancellationToken cancellationToken = default)
    {
        var now = DateTimeOffset.UtcNow.ToString("O");
        var item = new Dictionary<string, AttributeValue>
        {
            ["group_id"] = DynamoValues.S(groupId),
            ["draw_id"] = DynamoValues.S(Guid.NewGuid().ToString()),
            ["assignments"] = new() { M = assignments.ToDictionary(pair => pair.Key, pair => DynamoValues.S(pair.Value)) },
            ["created_at"] = DynamoValues.S(now),
            ["created_by"] = DynamoValues.S(actorUserId)
        };
        await db.TransactWriteItemsAsync(new TransactWriteItemsRequest
        {
            TransactItems =
        [
            new() { Put = new Put { TableName = settings.DrawsTable, Item = item, ConditionExpression = "attribute_not_exists(group_id)" } },
            new() { Update = new Update
            {
                TableName = settings.GroupsTable, Key = Key(groupId),
                UpdateExpression = "SET #status = :drawn, updated_at = :now",
                ConditionExpression = "#status = :open",
                ExpressionAttributeNames = new() { ["#status"] = "status" },
                ExpressionAttributeValues = new()
                {
                    [":drawn"] = DynamoValues.S("drawn"), [":open"] = DynamoValues.S("open"), [":now"] = DynamoValues.S(now)
                }
            }}
        ]
        }, cancellationToken);
    }

    public async Task<DrawRecord?> GetDrawAsync(string groupId, CancellationToken cancellationToken = default)
    {
        var response = await db.GetItemAsync(new GetItemRequest
        {
            TableName = settings.DrawsTable,
            Key = Key(groupId),
            ConsistentRead = true
        }, cancellationToken);
        if (!response.IsItemSet) return null;
        var assignments = response.Item.TryGetValue("assignments", out var map) && map.M is not null
            ? map.M.ToDictionary(pair => pair.Key, pair => pair.Value.S ?? "") : [];
        return new DrawRecord(
            groupId,
            response.Item.String("draw_id"),
            assignments,
            response.Item.String("created_at"),
            response.Item.String("created_by"),
            ReadProposal(response.Item),
            EmptyToNull(response.Item.String("last_late_proposal_id")),
            EmptyToNull(response.Item.String("last_late_member_id")),
            ReadStringList(response.Item, "last_affected_member_ids"));
    }

    public Task SaveLateProposalAsync(
        string groupId,
        string expectedDrawId,
        LateParticipantProposalRecord proposal,
        CancellationToken cancellationToken = default) =>
        db.UpdateItemAsync(new UpdateItemRequest
        {
            TableName = settings.DrawsTable,
            Key = Key(groupId),
            UpdateExpression = "SET late_proposal = :proposal",
            ConditionExpression = "draw_id = :draw",
            ExpressionAttributeValues = new()
            {
                [":draw"] = DynamoValues.S(expectedDrawId),
                [":proposal"] = ProposalValue(proposal)
            }
        }, cancellationToken);

    public async Task<string> ApplyLateProposalAsync(
        string groupId,
        string expectedDrawId,
        LateParticipantProposalRecord proposal,
        CancellationToken cancellationToken = default)
    {
        var newDrawId = Guid.NewGuid().ToString();
        var now = DateTimeOffset.UtcNow.ToString("O");
        await db.TransactWriteItemsAsync(
            LateProposalTransaction(groupId, expectedDrawId, proposal, newDrawId, now, settings),
            cancellationToken);
        return newDrawId;
    }

    internal static TransactWriteItemsRequest LateProposalTransaction(
        string groupId,
        string expectedDrawId,
        LateParticipantProposalRecord proposal,
        string newDrawId,
        string now,
        HumbuggSettings settings) =>
        new()
        {
            TransactItems =
            [
                new()
                {
                    Update = new Update
                    {
                        TableName = settings.DrawsTable,
                        Key = Key(groupId),
                        UpdateExpression = "SET draw_id = :newDraw, assignments = :assignments, updated_at = :now, last_late_proposal_id = :proposalId, last_late_member_id = :memberId, last_affected_member_ids = :affected REMOVE late_proposal",
                        ConditionExpression = "draw_id = :expectedDraw AND late_proposal.proposal_id = :proposalId AND late_proposal.expires_at > :now",
                        ExpressionAttributeValues = new()
                        {
                            [":newDraw"] = DynamoValues.S(newDrawId),
                            [":assignments"] = AssignmentsValue(proposal.Assignments),
                            [":now"] = DynamoValues.S(now),
                            [":proposalId"] = DynamoValues.S(proposal.ProposalId),
                            [":memberId"] = DynamoValues.S(proposal.MemberId),
                            [":affected"] = new() { L = proposal.AffectedMemberIds.Select(DynamoValues.S).ToList() },
                            [":expectedDraw"] = DynamoValues.S(expectedDrawId)
                        }
                    }
                },
                new()
                {
                    Update = new Update
                    {
                        TableName = settings.GroupMembersTable,
                        Key = new() { ["member_id"] = DynamoValues.S(proposal.MemberId) },
                        UpdateExpression = "SET is_participating = :active, updated_at = :now",
                        ConditionExpression = "group_id = :group AND is_participating = :inactive",
                        ExpressionAttributeValues = new()
                        {
                            [":active"] = DynamoValues.B(true),
                            [":inactive"] = DynamoValues.B(false),
                            [":group"] = DynamoValues.S(groupId),
                            [":now"] = DynamoValues.S(now)
                        }
                    }
                }
            ]
        };

    public Task ResetDrawAsync(string groupId, CancellationToken cancellationToken = default)
    {
        var now = DateTimeOffset.UtcNow.ToString("O");
        return db.TransactWriteItemsAsync(new TransactWriteItemsRequest
        {
            TransactItems =
        [
            new() { Delete = new Delete { TableName = settings.DrawsTable, Key = Key(groupId), ConditionExpression = "attribute_exists(group_id)" } },
            new() { Update = new Update
            {
                TableName = settings.GroupsTable, Key = Key(groupId),
                UpdateExpression = "SET #status = :open, updated_at = :now",
                ConditionExpression = "#status = :drawn",
                ExpressionAttributeNames = new() { ["#status"] = "status" },
                ExpressionAttributeValues = new()
                {
                    [":open"] = DynamoValues.S("open"), [":drawn"] = DynamoValues.S("drawn"), [":now"] = DynamoValues.S(now)
                }
            }}
        ]
        }, cancellationToken);
    }

    private static Dictionary<string, AttributeValue> Key(string groupId) => new() { ["group_id"] = DynamoValues.S(groupId) };
    private static AttributeValue AssignmentsValue(IReadOnlyDictionary<string, string> assignments) =>
        new() { M = assignments.ToDictionary(pair => pair.Key, pair => DynamoValues.S(pair.Value)) };
    private static AttributeValue ProposalValue(LateParticipantProposalRecord proposal) => new()
    {
        M = new()
        {
            ["proposal_id"] = DynamoValues.S(proposal.ProposalId),
            ["member_id"] = DynamoValues.S(proposal.MemberId),
            ["expected_draw_id"] = DynamoValues.S(proposal.ExpectedDrawId),
            ["assignments"] = AssignmentsValue(proposal.Assignments),
            ["affected_member_ids"] = new() { L = proposal.AffectedMemberIds.Select(DynamoValues.S).ToList() },
            ["expires_at"] = DynamoValues.S(proposal.ExpiresAt)
        }
    };
    private static LateParticipantProposalRecord? ReadProposal(IReadOnlyDictionary<string, AttributeValue> item)
    {
        if (!item.TryGetValue("late_proposal", out var value) || value.M is null || value.M.Count == 0)
            return null;
        var proposal = value.M;
        var assignments = proposal.TryGetValue("assignments", out var assignmentValue) && assignmentValue.M is not null
            ? assignmentValue.M.ToDictionary(pair => pair.Key, pair => pair.Value.S ?? "", StringComparer.Ordinal)
            : [];
        return new(
            proposal.String("proposal_id"),
            proposal.String("member_id"),
            proposal.String("expected_draw_id"),
            assignments,
            ReadStringList(proposal, "affected_member_ids") ?? [],
            proposal.String("expires_at"));
    }
    private static IReadOnlyList<string>? ReadStringList(
        IReadOnlyDictionary<string, AttributeValue> item,
        string key) =>
        item.TryGetValue(key, out var value) && value.L is not null
            ? value.L.Select(entry => entry.S ?? "").Where(entry => entry.Length > 0).ToList()
            : null;
    private static string Status(GroupStatus status) => status == GroupStatus.Open ? "open" : "drawn";
    private static GroupStatus ReadStatus(string status) => status == "drawn" ? GroupStatus.Drawn : GroupStatus.Open;

    private static Dictionary<string, AttributeValue> Write(GroupRecord group) => new()
    {
        ["group_id"] = DynamoValues.S(group.GroupId),
        ["owner_user_id"] = DynamoValues.S(group.OwnerUserId),
        ["name"] = DynamoValues.S(group.Name),
        ["description"] = DynamoValues.S(group.Description),
        ["event_date"] = DynamoValues.S(group.EventDate ?? ""),
        ["signup_deadline"] = DynamoValues.S(group.SignupDeadline ?? ""),
        ["currency"] = DynamoValues.S(group.Currency),
        ["plan"] = DynamoValues.S(group.Plan.ToString().ToLowerInvariant()),
        ["entitlement_id"] = group.EntitlementId is null ? new AttributeValue { NULL = true } : DynamoValues.S(group.EntitlementId),
        ["status"] = DynamoValues.S(Status(group.Status)),
        ["invite_hash"] = DynamoValues.S(group.InviteHash),
        ["exclusions"] = DynamoValues.ExclusionsValue(group.Exclusions),
        ["created_at"] = DynamoValues.S(group.CreatedAt),
        ["updated_at"] = DynamoValues.S(group.UpdatedAt),
        ["spending_limit_cents"] = group.SpendingLimitCents is null ? new AttributeValue { NULL = true } : DynamoValues.N(group.SpendingLimitCents.Value)
        ,
        ["customization"] = CustomizationValue(group.Customization),
        ["requires_address"] = DynamoValues.B(group.RequiresAddress)
    };

    private static GroupRecord Read(IReadOnlyDictionary<string, AttributeValue> item) => new(
        item.String("group_id"), item.String("owner_user_id"), item.String("name"), item.String("description"),
        EmptyToNull(item.String("event_date")), EmptyToNull(item.String("signup_deadline")), item.Long("spending_limit_cents"),
        item.String("currency", "USD"), ReadPlan(item.String("plan")), EmptyToNull(item.String("entitlement_id")),
        ReadStatus(item.String("status")), item.String("invite_hash"), item.Exclusions(),
        item.String("created_at"), item.String("updated_at"), ReadCustomization(item),
        item.Bool("requires_address"));
    private static AttributeValue CustomizationValue(ExchangeCustomization? value) => value is null
        ? new AttributeValue { NULL = true }
        : new AttributeValue
        {
            M = new()
            {
                ["greeting"] = DynamoValues.S(value.Greeting),
                ["instructions"] = DynamoValues.S(value.Instructions),
                ["primary_color"] = DynamoValues.S(value.PrimaryColor),
                ["accent_color"] = DynamoValues.S(value.AccentColor),
                ["image"] = DynamoValues.S(value.ImageDataUrl ?? "")
            }
        };
    private static ExchangeCustomization? ReadCustomization(IReadOnlyDictionary<string, AttributeValue> item)
    {
        if (!item.TryGetValue("customization", out var value) || value.NULL == true || value.M is null) return null;
        return new(value.M.String("greeting"), value.M.String("instructions"),
            value.M.String("primary_color", "#7C2D12"), value.M.String("accent_color", "#F59E0B"),
            EmptyToNull(value.M.String("image")));
    }
    internal static PlanCode ReadPlan(string value) => string.IsNullOrWhiteSpace(value)
        ? PlanCode.Free
        : Enum.TryParse<PlanCode>(value, true, out var plan)
            ? plan
            : throw new InvalidOperationException($"Group contains unsupported plan '{value}'.");
    private static string? EmptyToNull(string value) => string.IsNullOrEmpty(value) ? null : value;
}
