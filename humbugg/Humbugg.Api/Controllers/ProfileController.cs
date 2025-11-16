using Humbugg.Api.Models;
using Humbugg.Api.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Humbugg.Api.Controllers
{
    [ApiController]
    [Route("/api/[controller]")]
    [Authorize]
    public class ProfileController : ControllerBase
    {
        private readonly IUser _user;

        private readonly IProfileService _profileService;

        public ProfileController(IUser user, IProfileService profileService)
        {
            _user = user;
            _profileService = profileService;
        }

        [HttpGet("")]
        [Authorize]
        public ActionResult<Profile> Get()
        {
            var profile = _user.Profile;
            if (profile == null)
            {
                return NotFound();
            }
            return profile;
        }

        [HttpGet("{id}")]
        public ActionResult<Profile> Get(string id)
        {
            var profile = _profileService.Get(id);
            if (profile == null)
            {
                return NotFound();
            }
            return profile;
        }

        [HttpPost]
        public ActionResult<Profile> Create([FromBody]Profile profile)
        {
            _profileService.Create(profile);
            return Get(profile.Id);
        }

        [HttpPut("{id}")]
        public IActionResult Update(string id, [FromBody]Profile  profile)
        {
            var profileFound = _profileService.Get(id);
            if (profileFound == null)
            {
                return NotFound();
            }
            _profileService.Update(id, profile);
            return NoContent();
        }

        [HttpDelete("{id}")]
        public IActionResult Delete(string id)
        {
            var profileFound = _profileService.Get(id);
            if (profileFound == null)
            {
                return NotFound();
            }
            _profileService.Remove(id);
            return NoContent();
        }
    }
}
