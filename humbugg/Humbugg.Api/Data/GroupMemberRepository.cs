using System.Collections.Generic;
using MongoDB.Driver;
using Humbugg.Api.Models;

namespace Humbugg.Api.Data
{
    public interface IGroupMemberRepository : IBaseRepository<GroupMember>
    {
        List<GroupMember> GetByUserId(string userId);
        List<GroupMember> GetByGroupId(string groupId);
        GroupMember GetByUserIdAndGroupId(string groupId, string userId);
        void RemoveByGroupId(string groupId);
    }

    public class GroupMemberRepository : BaseRepository<GroupMember>, IGroupMemberRepository
    {
        public GroupMemberRepository(IDatabaseSettings settings) : base(settings, "GroupMembers")
        {
        }

        public List<GroupMember> GetByUserId(string userId) => _collection.Find(groupMember => groupMember.UserId == userId).ToList();

        public List<GroupMember> GetByGroupId(string groupId) => _collection.Find(groupMember => groupMember.GroupId == groupId).ToList();

        public GroupMember GetByUserIdAndGroupId(string userId, string groupId) => _collection.Find(groupMember => groupMember.GroupId == groupId && groupMember.UserId == userId).FirstOrDefault();

        public void RemoveByGroupId(string groupId) => _collection.DeleteMany(groupMember => groupMember.GroupId == groupId);
    }
}
