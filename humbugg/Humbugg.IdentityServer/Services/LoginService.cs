
using System;
using System.Collections.Generic;
using System.Linq;
using System.Security.Claims;
using Humbugg.IdentityServer.Data;
using Humbugg.IdentityServer.Models;

namespace Humbugg.IdentityServer.Services
{
    public interface ILoginService
    {
        bool ValidateCredentials(Profile profile, string password);
        Profile FindByUsername(string username);
        Profile AutoProvisionUser(string provider, string providerUserId, List<Claim> list);
        Profile FindByExternalProvider(string provider, string providerUserId);
        void CreateProfile(Profile profile);
    }

    public class LoginService : ILoginService
    {
        private readonly IProfileRepository _repository;

        public LoginService(IProfileRepository repository)
        {
            _repository = repository;
        }

        public bool ValidateCredentials(Profile user, string password)
        {
            return user.Password == $"{password}{user.Salt}".Sha256Hash();
        }

        public Profile FindByUsername(string username)
        {
            return _repository.GetByEmail(username);
        }

        public Profile AutoProvisionUser(string provider, string providerUserId, List<Claim> list)
        {
            var email = list.FirstOrDefault(claim => claim.Type == ClaimTypes.Email)?.Value;
            var foundProfile = _repository.GetByEmail(email);
            if (foundProfile != null)
            {
                SetProfileExternalUserId(provider, providerUserId, foundProfile);
                _repository.Update(foundProfile.Id, foundProfile);
                return foundProfile;
            }
            var profile = new Profile() { IsActive = true };
            profile.Email = email;
            profile.FirstName = list.FirstOrDefault(claim => claim.Type == ClaimTypes.GivenName)?.Value;
            profile.LastName = list.FirstOrDefault(claim => claim.Type == ClaimTypes.Surname)?.Value;
            SetProfileExternalUserId(provider, providerUserId,profile);
            CreateProfile(profile);
            return profile;
        }

        public Profile FindByExternalProvider(string provider, string providerUserId)
        {
            if (provider == "Google")
            {
                return _repository.GetByGoogleId(providerUserId);
            }
            else if (provider == "Facebook")
            {
                return _repository.GetByFacebookId(providerUserId);
            }
            throw new Exception($"Unable to handle external provider {provider}");
        }

        public void CreateProfile(Profile profile)
        {
            var salt = Guid.NewGuid().ToString();
            if (!string.IsNullOrWhiteSpace(profile.Password))
            {
                profile.Password = $"{profile.Password}{salt}".Sha256Hash();
                profile.Salt = salt;
            }
            _repository.InsertAysnc(profile);
        }

        private void SetProfileExternalUserId(string provider, string providerUserId, Profile profile)
        {
            if (provider == "Google")
            {
                profile.GoogleId = providerUserId;
            }
            else if (provider == "Facebook")
            {
                profile.FacebookId = providerUserId;
            }
            else 
            {
                throw new Exception($"Unable to handle external provider {provider}");
            }
        }
    }
}