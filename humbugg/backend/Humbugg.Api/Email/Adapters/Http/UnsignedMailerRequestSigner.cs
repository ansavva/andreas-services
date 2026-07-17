namespace Humbugg.Api.Email.Adapters.Http;

// Local development deliberately uses the same Mailer routes without AWS auth.
internal sealed class UnsignedMailerRequestSigner : IMailerRequestSigner
{
    public Task SignAsync(
        HttpRequestMessage request,
        ReadOnlyMemory<byte> body,
        CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        return Task.CompletedTask;
    }
}
