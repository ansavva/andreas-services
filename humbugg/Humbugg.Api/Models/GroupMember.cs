using MongoDB.Bson.Serialization.Attributes;
using System.Collections.Generic;

namespace Humbugg.Api.Models
{
    public class GroupMember : BaseModel
    {
        public string GroupId { get; set; }
        public string UserId { get; set; }
        public bool IsAdmin { get; set; }
        public bool IsParticipating { get; set; }
        public string RecipientId { get; set; }
        [BsonIgnore]
        public Group Group { get; set; }
        public string FirstName { get; set; }
        public string MiddleName { get; set; }
        public string LastName { get; set; }
        public string Address1 { get; set;}
        public string Address2 { get; set;}
        public string City { get; set; }
        public string State { get; set; }
        public string PostalCode { get; set; }
        public string PictureUrl { get; set; }
        public string GiftSuggestionsDescription { get; set; }
        public string GiftAvoidancesDescription { get; set; }
        public string SecretQuestionAnswer { get; set; }
    }
}
