using System.Collections.Generic;
using MongoDB.Driver;
using Humbugg.IdentityServer.Models;
using System.Threading.Tasks;

namespace Humbugg.IdentityServer.Data
{
    public interface IBaseRepository<T> where T : BaseModel
    {
        Task InsertAysnc(T data);
        Task<List<T>> GetAsync();
        Task<T> GetAsync(string id);
        void Update(string id, T dataIn);
    }

    public class BaseRepository<T> : IBaseRepository<T> where T : BaseModel
    {
        protected readonly IMongoCollection<T> _collection;

        public BaseRepository(IDatabaseSettings settings, string collectionName)
        {
            var client = new MongoClient(settings.ConnectionString);
            var database = client.GetDatabase(settings.DatabaseName);
            _collection = database.GetCollection<T>(collectionName);
        }

        public async Task InsertAysnc(T data)
        {
            await _collection.InsertOneAsync(data);
        }

        public async Task<List<T>> GetAsync()
        {
            var collection = await _collection.FindAsync(data => true);
            return await collection.ToListAsync();
        }

        public async Task<T> GetAsync(string id)
        {
            var collection = await _collection.FindAsync(data => data.Id == id);
            return await collection.FirstOrDefaultAsync();
        }

        public void Update(string id, T dataIn) =>
            _collection.ReplaceOne(data => data.Id == id, dataIn);
    }
}
