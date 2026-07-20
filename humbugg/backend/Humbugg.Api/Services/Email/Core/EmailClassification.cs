namespace Humbugg.Api.Services.Email.Core;

/// <summary>
/// Whether a message must always reach the recipient or is governed by their opt-out preference.
/// </summary>
public enum EmailImportance
{
    /// <summary>Security/account and join-critical mail. Always sent, never suppressible.</summary>
    Essential,

    /// <summary>Reminders, group-activity notifications, and product news. Honors the opt-out toggle.</summary>
    NonEssential
}

/// <summary>
/// The single source of truth that classifies each transactional email category as essential or
/// non-essential. Essential categories always send; non-essential categories are gated on the
/// recipient's <c>non_essential_emails_enabled</c> preference. See
/// <c>humbugg/docs/email-operations.md</c> for the operator-facing description of this policy.
/// </summary>
public static class EmailClassification
{
    /// <summary>Returns the importance of a category. Update this switch — nowhere else — to reclassify.</summary>
    public static EmailImportance Of(EmailCategory category) => category switch
    {
        // Join-critical: muting these would break the core exchange flow, so they are essential.
        EmailCategory.Invitation => EmailImportance.Essential,          // "you've been invited"
        EmailCategory.DrawCompleted => EmailImportance.Essential,        // "your assignment is ready"
        EmailCategory.AssignmentAvailable => EmailImportance.Essential,  // "your assignment is ready"

        // Governed by the single opt-out toggle.
        EmailCategory.Reminder => EmailImportance.NonEssential,
        EmailCategory.AccountExchangeEvent => EmailImportance.NonEssential, // group-activity / question-and-reply notifications

        _ => throw new ArgumentOutOfRangeException(nameof(category), category, null)
    };

    /// <summary>True when a category always sends regardless of the recipient's preference.</summary>
    public static bool IsEssential(EmailCategory category) => Of(category) == EmailImportance.Essential;
}
