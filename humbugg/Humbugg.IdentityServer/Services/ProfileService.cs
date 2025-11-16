using System.Linq;
using System.Threading.Tasks;
using Humbugg.IdentityServer.Data;
using IdentityServer4.Models;
using IdentityServer4.Services;

namespace Humbugg.IdentityServer.Services
{
    public class ProfileService : IProfileService
    {
        //services
        private readonly IProfileRepository _userRepository;

        public ProfileService(IProfileRepository userRepository)
        {
            _userRepository = userRepository;
        }

        //Get user profile date in terms of claims when calling /connect/userinfo
        public async Task GetProfileDataAsync(ProfileDataRequestContext context)
        {
            try
            {
                //depending on the scope accessing the user data.
                if (!string.IsNullOrEmpty(context.Subject.Identity.Name))
                {
                    //get user from db (in my case this is by email)
                    var user = await _userRepository.GetByEmailAsync(context.Subject.Identity.Name);

                    if (user != null)
                    {
                        var claims = ClaimsService.GetUserClaims(user);

                        //set issued claims to return
                        context.IssuedClaims = claims.Where(x => context.RequestedClaimTypes.Contains(x.Type)).ToList();
                    }
                }
                else
                {
                    //get subject from context (this was set ResourceOwnerPasswordValidator.ValidateAsync),
                    //where and subject was set to my user id.
                    var userId = context.Subject.Claims.FirstOrDefault(x => x.Type == "sub");

                    if (!string.IsNullOrEmpty(userId?.Value))
                    {
                        //get user from db (find user by user id)
                        var user = await _userRepository.GetAsync(userId.Value);

                        // issue the claims for the user
                        if (user != null)
                        {
                            var claims = ClaimsService.GetUserClaims(user);

                            context.IssuedClaims = claims.Where(x => context.RequestedClaimTypes.Contains(x.Type)).ToList();
                        }
                    }
                }
            }
            catch
            {
                //log your error
            }
        }

        //check if user account is active.
        public async Task IsActiveAsync(IsActiveContext context)
        {
            try
            {
                //get subject from context (set in ResourceOwnerPasswordValidator.ValidateAsync),
                var userId = context.Subject.Claims.FirstOrDefault(x => x.Type == "user_id");

                if (!string.IsNullOrEmpty(userId?.Value))
                {
                    var user = await _userRepository.GetAsync(userId.Value);

                    if (user != null)
                    {
                        if (user.IsActive)
                        {
                            context.IsActive = user.IsActive;
                        }
                    }
                }
            }
            catch
            {
                
            }
        }
    }
}