using MongoDB.Driver;
using Humbugg.IdentityServer.Models;
using System.Threading.Tasks;

namespace Humbugg.IdentityServer.Data
{
    public interface IProfileRepository : IBaseRepository<Profile>
    {
        Profile GetByEmail(string email);
        Task<Profile> GetByEmailAsync(string email);
        Profile GetByGoogleId(string id);
        Profile GetByFacebookId(string id);
    }
    
    public class ProfileRepository : BaseRepository<Profile>, IProfileRepository
    {
        public ProfileRepository(IDatabaseSettings settings) : base(settings, "Profiles")
        {
        }

        public Profile GetByEmail(string email) => _collection.Find(profile => profile.Email.ToLower() == email.ToLower()).FirstOrDefault();

        public async Task<Profile> GetByEmailAsync(string email)
        {
            var collection = await _collection.FindAsync<Profile>(profile => profile.Email.ToLower() == email.ToLower());
            return await collection.FirstOrDefaultAsync();
        }

        public Profile GetByGoogleId(string id) => _collection.Find<Profile>(profile => profile.GoogleId == id).FirstOrDefault();
        public Profile GetByFacebookId(string id) => _collection.Find<Profile>(profile => profile.FacebookId == id).FirstOrDefault();
    }
}