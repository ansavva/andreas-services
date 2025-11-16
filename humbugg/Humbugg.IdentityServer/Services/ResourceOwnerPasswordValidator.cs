using System.Threading.Tasks;
using IdentityServer4.Models;
using IdentityServer4.Validation;
using Humbugg.IdentityServer.Data;

namespace Humbugg.IdentityServer.Services
{
    public class ResourceOwnerPasswordValidator : IResourceOwnerPasswordValidator
    {
        //repository to get user from db
        private readonly IProfileRepository _userRepository;
        private readonly ILoginService _loginService;

        public ResourceOwnerPasswordValidator(IProfileRepository userRepository, ILoginService loginService)
        {
            _userRepository = userRepository;
            _loginService = loginService;
        }

        //this is used to validate your user account with provided grant at /connect/token
        public async Task ValidateAsync(ResourceOwnerPasswordValidationContext context)
        {
            try
            {
                //get your user model from db (by username - in my case its email)
                var user = await _userRepository.GetByEmailAsync(context.UserName);
                if (user != null)
                {
                    if (_loginService.ValidateCredentials(user, context.Password))
                    {
                        //set the result
                        context.Result = new GrantValidationResult(
                            subject: user.Id.ToString(),
                            authenticationMethod: "custom",
                            claims: ClaimsService.GetUserClaims(user));

                        return;
                    }

                    context.Result = new GrantValidationResult(TokenRequestErrors.InvalidGrant, "Incorrect password");
                    return;
                }

                context.Result = new GrantValidationResult(TokenRequestErrors.InvalidGrant, "User does not exist.");
                return;
            }
            catch
            {
                context.Result = new GrantValidationResult(TokenRequestErrors.InvalidGrant, "Invalid username or password");
            }
        }
    }
}
