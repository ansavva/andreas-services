using System.Security.Claims;
using Humbugg.Api.Data;
using Humbugg.Api.Models;
using Microsoft.AspNetCore.Http;

namespace Humbugg.Api.Services
{
    public interface IUser
    {
        Claims Claims { get; }
        Profile Profile { get; }
    }
    
    public class User : IUser
    {
        private readonly IProfileRepository _profileRepository;
        private readonly IHttpContextAccessor _httpContextAccessor;

        private Claims _claims = null;
        private Profile _profile = null;
        
        public User(IHttpContextAccessor httpContextAccessor, IProfileRepository profileRepository)
        {
            _profileRepository = profileRepository;
            _httpContextAccessor = httpContextAccessor;
        }

        private ClaimsPrincipal CurrentUser => _httpContextAccessor.HttpContext.User;

        public Claims Claims
        {
            get
            {
                if (CurrentUser == null) return null;
                if (_claims != null) return _claims;
                var claims = new Claims();
                var nameIdentifier = CurrentUser.FindFirst(ClaimTypes.NameIdentifier);
                if (!string.IsNullOrEmpty(nameIdentifier?.Value))
                {
                    claims.ProfileId = nameIdentifier.Value;
                }
                var firstName = CurrentUser.FindFirst(ClaimTypes.Name);
                if (!string.IsNullOrEmpty(firstName?.Value))
                {
                    claims.FirstName = firstName.Value;
                }
                var lastName = CurrentUser.FindFirst(ClaimTypes.Surname);
                if (!string.IsNullOrEmpty(lastName?.Value))
                {
                    claims.LastName = lastName.Value;
                }
                var pictureUrl = CurrentUser.FindFirst(("picture"));
                if (!string.IsNullOrEmpty(pictureUrl?.Value))
                {
                    claims.PictureUrl = pictureUrl.Value;
                }
                _claims = claims;
                return _claims;
            }
        }
        
        public Profile Profile
        {
            get
            {
                if (Claims == null) return null;
                if (_profile != null) return _profile;
                var profileId = Claims.ProfileId;
                _profile = _profileRepository.Get(profileId);
                return _profile;
            }
        }
    }
}