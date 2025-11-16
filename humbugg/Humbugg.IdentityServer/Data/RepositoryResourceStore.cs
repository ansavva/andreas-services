using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using IdentityServer4.Models;
using IdentityServer4.Stores;

namespace Humbugg.IdentityServer.Data
{
    public class RepositoryResourceStore : IResourceStore
    {
        protected IRepository _repository;

        public RepositoryResourceStore(IRepository repository)
            => _repository = repository;

        public Task<IEnumerable<ApiResource>> FindApiResourcesByNameAsync(IEnumerable<string> apiResourceNames)
            => Task.FromResult(_repository.Where<ApiResource>(e => apiResourceNames.Contains(e.Name)).AsEnumerable());

        public Task<IEnumerable<ApiScope>> FindApiScopesByNameAsync(IEnumerable<string> scopeNames)
            => Task.FromResult(_repository.Where<ApiScope>(e => scopeNames.Contains(e.Name)).AsEnumerable());

        public Task<IEnumerable<ApiResource>> FindApiResourcesByScopeNameAsync(IEnumerable<string> scopeNames)
        {
            var apis = _repository.All<ApiResource>().ToList();
            var list = apis.Where<ApiResource>(a => a.Scopes.Any(s =>  scopeNames.Contains(s))).AsEnumerable();
            return Task.FromResult(list);
        }
        
        public Task<IEnumerable<IdentityResource>> FindIdentityResourcesByScopeNameAsync(IEnumerable<string> scopeNames)
            => Task.FromResult(_repository.Where<IdentityResource>(e => scopeNames.Contains(e.Name)).AsEnumerable());

        public Task<Resources> GetAllResourcesAsync()
            => Task.FromResult(new Resources(_repository.All<IdentityResource>(), _repository.All<ApiResource>(), _repository.All<ApiScope>()));
    }
}