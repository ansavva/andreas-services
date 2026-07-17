using Humbugg.Api.Services.Email.Core;

namespace Humbugg.Api.Services.Email.Adapters.Http;

/// <summary>
/// Adapts Humbugg's email transport boundary to the shared Mailer HTTP API.
/// The injected signer selects authenticated AWS or unsigned local operation.
/// </summary>
internal sealed class MailerEmailTransport(IMailerClient mailer) : IEmailTransport
{
    /// <inheritdoc />
    public async Task<string> SendAsync(
        TransactionalEmail email,
        CancellationToken cancellationToken)
    {
        var response = await mailer.SubmitMessageAsync(email, cancellationToken: cancellationToken);
        return response.ApplicationMessageId;
    }
}
