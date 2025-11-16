using MongoDB.Bson;
using MongoDB.Bson.Serialization.Attributes;

namespace Humbugg.Web.Models
{
    public class Profile : BaseModel
    {
        public string FirstName { get; set; }
        public string MiddleName { get; set; }
        public string LastName { get; set; }
        public string Email { get; set;  }
        public string PictureUrl { get; set; }
        public string GoogleId { get; set; }
        public string FacebookId { get; set; }
    }
}