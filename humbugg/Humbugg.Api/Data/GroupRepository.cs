using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using MongoDB.Driver;
using Humbugg.Api.Models;

namespace Humbugg.Api.Data
{
    public interface IGroupRepository : IBaseRepository<Group>
    {
    }

    public class GroupRepository : BaseRepository<Group>, IGroupRepository
    {
        public GroupRepository(IDatabaseSettings settings) : base(settings, "Groups")
        {
        }
    }
}
