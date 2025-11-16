using Humbugg.Api.Models;
using MongoDB.Driver;

namespace Humbugg.Api.Data
{
    public interface IProfileRepository : IBaseRepository<Profile>
    {
        Profile GetByEmail(string email);
        Profile GetByGoogleId(string id);
        Profile GetByFacebookId(string id);
    }
    
    public class ProfileRepository : BaseRepository<Profile>, IProfileRepository
    {
        public ProfileRepository(IDatabaseSettings settings) : base(settings, "Profiles")
        {
        }

        public Profile GetByEmail(string email) => _collection.Find<Profile>(profile => profile.Email.ToLower() == email.ToLower()).FirstOrDefault();
        public Profile GetByGoogleId(string id) => _collection.Find<Profile>(profile => profile.GoogleId == id).FirstOrDefault();
        public Profile GetByFacebookId(string id) => _collection.Find<Profile>(profile => profile.FacebookId == id).FirstOrDefault();
    }
}