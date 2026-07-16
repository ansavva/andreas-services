using Amazon.SimpleEmailV2;
using Amazon.SimpleEmailV2.Model;
using SesContent = Amazon.SimpleEmailV2.Model.Content;
using SesMessage = Amazon.SimpleEmailV2.Model.Message;

namespace Humbugg.Api.Email;

internal sealed class SesEmailTransport(
    IAmazonSimpleEmailServiceV2 ses,
    HumbuggSettings settings) : IEmailTransport
{
    public async Task<string> SendAsync(TransactionalEmail email, CancellationToken cancellationToken)
    {
        var response = await ses.SendEmailAsync(new SendEmailRequest
        {
            FromEmailAddress = settings.EmailFromAddress,
            Destination = new Destination { ToAddresses = [email.ToAddress] },
            Content = new EmailContent
            {
                Simple = new SesMessage
                {
                    Subject = new SesContent { Data = email.Subject, Charset = "UTF-8" },
                    Body = new Body
                    {
                        Html = new SesContent { Data = email.HtmlBody, Charset = "UTF-8" },
                        Text = new SesContent { Data = email.TextBody, Charset = "UTF-8" }
                    }
                }
            },
            EmailTags =
            [
                new MessageTag { Name = "humbugg-message-id", Value = email.MessageId },
                new MessageTag { Name = "humbugg-category", Value = EmailMessageId.CategoryName(email.Category) }
            ]
        }, cancellationToken);

        return response.MessageId;
    }
}
