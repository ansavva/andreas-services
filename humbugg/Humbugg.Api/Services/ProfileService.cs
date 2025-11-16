using System.Collections.Generic;
using Humbugg.Api.Data;
using Humbugg.Api.Models;

namespace Humbugg.Api.Services
{
    public interface IProfileService
    {
        Profile Get(string id);
        void Update(string id, Profile profile);
        void Remove(string id);
        void Create(Profile profile);
    }

    public class ProfileService : IProfileService
    {
        private readonly IProfileRepository _profileRepository;

        public ProfileService(IProfileRepository profileRepository)
        {
            _profileRepository = profileRepository;
        }

        public void Create(Profile profile) => _profileRepository.Create(profile);

        public List<Profile> Get() => _profileRepository.Get();

        public Profile Get(string id) => _profileRepository.Get(id);

        public void Remove(string id) => _profileRepository.Remove(id);

        public void Update(string id, Profile profile) => _profileRepository.Update(id, profile);
    }
}