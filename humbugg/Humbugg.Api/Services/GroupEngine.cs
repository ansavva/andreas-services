using System;
using System.Collections.Generic;
using System.Linq;
using Humbugg.Api.Data;
using Humbugg.Api.Models;

namespace Humbugg.Api.Services
{
    public interface IGroupEngine
    {
        List<Group> Get();
        Group Get(string groupId);
        void Create(Group group);
        void CreateMatches(string groupId);
        void Update(string id, Group group);
        void Remove(string id);
    }

    public class GroupEngine : IGroupEngine
    {
        private readonly IUser _user;
        private readonly IGroupRepository _groupRepository;
        private readonly IGroupMemberEngine _groupMemberEngine;
        private readonly IProfileRepository _profileRepository;

        public GroupEngine(IUser user, IGroupRepository groupRepository, IGroupMemberEngine groupMemberEngine, IProfileRepository profileRepository)
        {
            _user = user;
            _groupRepository = groupRepository;
            _groupMemberEngine = groupMemberEngine;
            _profileRepository = profileRepository;
        }

        public List<Group> Get()
        {
            var myGroupMembers = _groupMemberEngine.GetByUserId();
            List<Group> groups = new List<Group>();
            foreach (var myGroupMember in myGroupMembers)
            {
                var group = _groupRepository.Get(myGroupMember.GroupId);
                group.GroupMembers = _groupMemberEngine.GetByGroupId(myGroupMember.GroupId);
                groups.Add(group);
            }
            return groups;
        }

        public Group Get(string groupId)
        {
            var group = _groupRepository.Get(groupId);
            if (group == null)
            {
                throw new HumbuggException("The group you are looking for has been deleted.");
            }
            group.GroupMembers = _groupMemberEngine.GetByGroupId(groupId);
            return group;
        }
        public void Create(Group group)
        {
            // Create the group
            group.CreatedDate = DateTime.Now;
            _groupRepository.Create(group);
            group.GroupMembers.ForEach(groupMember =>
            {
                groupMember.GroupId = group.Id;
                groupMember.CreatedDate = DateTime.Now;
                groupMember.IsAdmin = true;
            });
            _groupMemberEngine.Create(group.GroupMembers);
        }
        
        public void CreateMatches(string groupId)
        {
            var myGroupMember = _groupMemberEngine.GetByUserIdAndGroupId(groupId);
            if (myGroupMember == null || !myGroupMember.IsAdmin) // only admins can create matches for a group
            {
                throw new HumbuggException("Unauthorized to create matches for this group.");
            }
            var groupMembers = _groupMemberEngine.GetByGroupId(groupId);
            do
            {
                groupMembers.ForEach(gm => gm.RecipientId = null); // clear the recipients
                var hat = groupMembers.ToList();
                // Randomly match everyone
                foreach (var groupMember in groupMembers)
                {
                    hat.Shuffle(); // shuffle the hat
                    var randomGroupMember = hat.FirstOrDefault(hatGroupMember => hatGroupMember.Id != groupMember.Id);
                    if (randomGroupMember != null)
                    {
                        hat.Remove(randomGroupMember);
                        groupMember.RecipientId = randomGroupMember.Id;
                        _groupMemberEngine.Update(groupMember.Id, groupMember); // remember who got assigned the person that was drawn from the hat
                    }
                }
            } while (groupMembers.Any(gm => gm.RecipientId == null));
        }

        public void Update(string id, Group group)
        {
            var myGroupMember = _groupMemberEngine.GetByUserIdAndGroupId(id);
            if (myGroupMember == null)
            {
                throw new HumbuggException("Unauthorized to delete group.");
            }
            if (myGroupMember.IsAdmin)
            {
                _groupRepository.Update(id, group);
                if (group.GroupMembers != null && group.GroupMembers.Any())
                {
                    foreach(var groupMember in group.GroupMembers)
                    {
                        _groupMemberEngine.Update(groupMember.Id, groupMember);
                    }
                }
            }
        }

        public void Remove(string groupId)
        {
            var myGroupMember = _groupMemberEngine.GetByUserIdAndGroupId(groupId);
            if (myGroupMember == null)
            {
                throw new HumbuggException("Unauthorized to delete group.");
            }
            if (myGroupMember.IsAdmin)
            {
                _groupMemberEngine.RemoveByGroupId(groupId);
                _groupRepository.Remove(groupId);
            }
        }
    }
}
