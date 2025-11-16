using System.Collections.Generic;
using MongoDB.Driver;
using Humbugg.Api.Models;

namespace Humbugg.Api.Data
{
    public interface IBaseRepository<T> where T : BaseModel
    {
        List<T> Get();
        T Get(string id);
        void Create(T dataIn);
        void Create(List<T> dataIn);
        void Update(string id, T dataIn);
        void Remove(T dataIn);
        void Remove(string id);
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

        public List<T> Get() => _collection.Find(data => true).ToList();

        public T Get(string id) => _collection.Find<T>(data => data.Id == id).FirstOrDefault();

        public void Create(T dataIn) => _collection.InsertOne(dataIn);

        public void Create(List<T> dataIn) => _collection.InsertMany(dataIn);

        public void Update(string id, T dataIn) =>
            _collection.ReplaceOne(data => data.Id == id, dataIn);

        public void Remove(T dataIn) =>
            _collection.DeleteOne(data => data.Id == dataIn.Id);

        public void Remove(string id) =>
            _collection.DeleteOne(data => data.Id == id);
    }
}
