using System;
using System.Collections.Generic;
using System.Linq;
using Humbugg.Api.Data;
using Humbugg.Api.Models;

namespace Humbugg.Api.Services
{
    public interface IGroupMemberEngine
    {
        List<GroupMember> GetByUserId();
        List<GroupMember> GetByGroupId(string groupId);
        GroupMember GetByUserIdAndGroupId(string groupid);
        GroupMember GetById(string groupMemberId); 
        void Update(string id, GroupMember groupMember);
        void Create(GroupMember groupMember);
        void Create(List<GroupMember> groupMembers);
        void Remove(string groupMemberId);
        void RemoveByGroupId(string groupId);
    }

    public class GroupMemberEngine : IGroupMemberEngine
    {
        private readonly IUser _user;
        private readonly IGroupMemberRepository _groupMemberRepository;
        private readonly IGroupRepository _groupRepository;

        public GroupMemberEngine(IUser user, IGroupMemberRepository groupMemberRepository, IGroupRepository groupRepository)
        {
            _user = user;
            _groupMemberRepository = groupMemberRepository;
            _groupRepository = groupRepository;
        }
        
        public List<GroupMember> GetByUserId()
        {
            var groupMembers = _groupMemberRepository.GetByUserId(_user.Profile.Id);
            groupMembers = SanitizeRecipients(groupMembers);
            return groupMembers;
        }

        public GroupMember GetByUserIdAndGroupId(string groupId)
        {
            return _groupMemberRepository.GetByUserIdAndGroupId(_user.Profile.Id, groupId);
        }

        public List<GroupMember> GetByGroupId(string groupId)
        {
            var groupMembers = _groupMemberRepository.GetByGroupId(groupId);
            groupMembers = SanitizeRecipients(groupMembers);
            return groupMembers;
        }

        public GroupMember GetById(string groupMemberId)
        {
            var groupMember = GetByIdNoSanitize(groupMemberId);
            groupMember = SanitizeRecipient(groupMember);
            return groupMember;
        }

        public GroupMember GetByIdNoSanitize(string groupMemberId)
        {
            var groupMember = _groupMemberRepository.Get(groupMemberId);
            groupMember.Group = _groupRepository.Get(groupMember.GroupId);
            return groupMember;
        }

        public void Update(string id, GroupMember groupMember)
        {
            var myGroupMember = GetByUserIdAndGroupId(groupMember.GroupId);
            if (myGroupMember == null) 
            {
                throw new HumbuggException("We were unable to locate your group member for this group.");
            }
            if (groupMember.UserId != _user.Profile.Id && !myGroupMember.IsAdmin)
            {
                throw new HumbuggException("You do not have permission to update this group member.");
            }
            _groupMemberRepository.Update(id, groupMember);
        }

        public void Create(GroupMember groupMember)
        {
            if (groupMember == null)
            {
                throw new HumbuggException("Group Member information was not supplied.");
            }
            if (GetByUserIdAndGroupId(groupMember.GroupId) != null)
            {
                throw new HumbuggException("You already have a group member for this group.");
            }
            groupMember.CreatedDate = DateTime.Now;
            groupMember.UserId = _user.Profile.Id;
            groupMember.IsAdmin = false;
            groupMember.IsParticipating = true;
            _groupMemberRepository.Create(groupMember);
        }

        public void Create(List<GroupMember> groupMembers)
        {
            _groupMemberRepository.Create(groupMembers);
        }

        public void Remove(string groupMemberId)
        {
            var groupMember = GetByIdNoSanitize(groupMemberId);
            if (groupMember == null) 
            {
                throw new HumbuggException("Group member not found.");
            }
            var myGroupMember = GetByUserIdAndGroupId(groupMember.GroupId);
            if (myGroupMember == null)
            {
                throw new HumbuggException("We were unable to locate your group member for this group.");
            }
            if (!myGroupMember.IsAdmin && groupMember.RecipientId != myGroupMember.RecipientId)
            {
                throw new HumbuggException("You cannot delete group members. You are not an admin of this group.");
            }
            if (myGroupMember.IsAdmin && groupMember.RecipientId == myGroupMember.RecipientId)
            {
                throw new HumbuggException("You cannot delete your own group member");
            }
            _groupMemberRepository.Remove(groupMemberId);
            // Clear all the recipients for this group.
            var allGroupMembers = _groupMemberRepository.GetByGroupId(groupMember.GroupId);
            if (allGroupMembers != null && allGroupMembers.Any(allGroupMember => allGroupMember.RecipientId != null))
            {
                allGroupMembers.ForEach(allGroupMember => {
                    allGroupMember.RecipientId = null;
                    _groupMemberRepository.Update(allGroupMember.Id, allGroupMember);
                });
            }
        }

        public void RemoveByGroupId(string groupId)
        {
            _groupMemberRepository.RemoveByGroupId(groupId);
        }

        private GroupMember SanitizeRecipient(GroupMember groupMember)
        {
            if (groupMember.UserId != _user.Profile.Id || !GetByUserIdAndGroupId(groupMember.GroupId).IsAdmin)
            {
                groupMember.RecipientId = null; // we don't want to expose the recipients unless the user is an admin for the group
            }
            return groupMember;
        }

        private GroupMember SanitizeRecipient(GroupMember groupMember, GroupMember myGroupMember)
        {
            if (groupMember.UserId != _user.Profile.Id && myGroupMember != null && !myGroupMember.IsAdmin)
            {
                groupMember.RecipientId = null; // we don't want to expose the recipients unless the user is an admin for the group
            }
            return groupMember;
        }

        private List<GroupMember> SanitizeRecipients(List<GroupMember> groupMembers)
        {
            if (groupMembers == null || !groupMembers.Any())
            {
                return groupMembers;
            }
            var myGroupMember = GetByUserIdAndGroupId(groupMembers.FirstOrDefault().GroupId);
            groupMembers.ForEach(gm => gm = SanitizeRecipient(gm, myGroupMember));
            return groupMembers;
        }
    }
}
