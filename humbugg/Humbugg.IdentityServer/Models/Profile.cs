using MongoDB.Bson;
using MongoDB.Bson.Serialization.Attributes;

namespace Humbugg.IdentityServer.Models
{
    public class Profile : BaseModel
    {
        public string FirstName { get; set; }
        public string MiddleName { get; set; }
        public string LastName { get; set; }
        public string Email { get; set;  }
        public string Password { get; set; }
        public string Salt { get; set; }
        public string Role { get; set; }
        public string PictureUrl { get; set; }
        public string GoogleId { get; set; }
        public string FacebookId { get; set; }
        public bool IsActive { get; set; }
    }
}