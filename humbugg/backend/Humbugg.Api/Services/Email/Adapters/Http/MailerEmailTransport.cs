using Humbugg.Api.Services.Email.Core;

namespace Humbugg.Api.Services.Email.Adapters.Http;

// Shared application transport: only the injected request signer varies by runtime.
internal sealed class MailerEmailTransport(IMailerClient mailer) : IEmailTransport
{
    public async Task<string> SendAsync(
        TransactionalEmail email,
        CancellationToken cancellationToken)
    {
        var response = await mailer.SubmitMessageAsync(email, cancellationToken: cancellationToken);
        return response.ApplicationMessageId;
    }
}
