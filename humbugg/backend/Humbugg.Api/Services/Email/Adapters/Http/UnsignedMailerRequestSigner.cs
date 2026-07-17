namespace Humbugg.Api.Services.Email.Adapters.Http;

/// <summary>
/// Leaves local Mailer requests unsigned while preserving the production request pipeline.
/// </summary>
internal sealed class UnsignedMailerRequestSigner : IMailerRequestSigner
{
    /// <inheritdoc />
    public Task SignAsync(
        HttpRequestMessage request,
        ReadOnlyMemory<byte> body,
        CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        return Task.CompletedTask;
    }
}
