using System;
using System.Collections.Generic;
using MongoDB.Bson.Serialization.Attributes;

namespace Humbugg.Api.Models
{
    public class Group : BaseModel
    {
        public string Name { get; set; }
        public string SecretQuestion { get; set; }
        public string SecretQuestionAnswer { get; set; }
        public List<GroupRule> GroupRules { get; set; }
        [BsonIgnore]
        public List<GroupMember> GroupMembers { get; set; }
        public DateTime SignUpDeadline { get; set; }
        public DateTime EventDate { get; set; }
        public decimal SpendingLimit { get; set; }
        public string Description { get; set; }
    }
}
